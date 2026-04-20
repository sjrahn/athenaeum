import Foundation
import Observation
import os
import SwiftUI
import AthenaeumKit

/// Central state for the browse window. Owns the `APIClient`, the current
/// query + its results, selected record, facets, and health status. Views
/// read this through `@Environment(BrowseStore.self)` and call methods to
/// drive state transitions; no direct `APIClient` calls live in views.
@Observable
@MainActor
final class BrowseStore {
    // MARK: - Published state

    var corpora: LoadState<[CorpusInfo]> = .idle
    var selectedCorpus: String = ""

    var facets: LoadState<FacetsResponse> = .idle
    var records: LoadState<QueryResult> = .idle
    var submissions: LoadState<SubmissionsResponse> = .idle

    var selectedRecordID: UUID?
    var selectedDetail: LoadState<RecordDetail> = .idle

    /// Current query — everything the toolbar / sidebar binds to. Changes
    /// trigger a debounced reload via `applyFilters()` / `reloadRecords()`.
    var query: QueryParams

    var searchText: String = ""
    var kindFilter: KindFilter = .all
    var listVariant: ListVariant = .columns
    var detailMode: DetailMode = .tabbed

    var health: HealthState = .unknown
    var lastSync: Date?

    /// True while `loadMore()` is fetching the next page; used to gate
    /// re-entry from scroll-triggered infinite-scroll sentinels.
    var isLoadingMore: Bool = false

    /// Chronological list of recently-selected record IDs, driven by
    /// `select()`. `historyIndex` points at the "current" selection so
    /// `goBack()` / `goForward()` can walk without disturbing the list.
    private(set) var selectionHistory: [UUID] = []
    private(set) var historyIndex: Int = -1

    // MARK: - Dependencies

    private let client: APIClient
    private let log = Logger(subsystem: "dev.rahn.athenaeum", category: "browse")
    private let preferences: PreferencesStore

    private var healthTask: Task<Void, Never>?
    private var currentRecordsTask: Task<Void, Never>?
    private var currentDetailTask: Task<Void, Never>?

    /// Set transiently while `goBack()` / `goForward()` drive `select()` so
    /// those selections don't themselves push new entries onto the stack.
    private var navigatingViaHistory: Bool = false

    // MARK: - Init

    init(preferences: PreferencesStore) {
        let corpus = preferences.lastUsedCorpus ?? "corpus-public"
        self.preferences = preferences
        self.client = APIClient(baseURL: preferences.serverURL)
        self.selectedCorpus = corpus
        self.query = QueryParams(corpus: corpus, sort: "normalized_desc")
    }

    // MARK: - Lifecycle

    /// Kick off the initial fetches. Safe to call multiple times.
    func start() {
        loadCorpora()
        startHealthPolling()
        reloadAll()
    }

    func stop() {
        healthTask?.cancel()
        currentRecordsTask?.cancel()
        currentDetailTask?.cancel()
    }

    // MARK: - Corpus

    func loadCorpora() {
        corpora = .loading
        Task {
            do {
                let result = try await client.listCorpora()
                corpora = .loaded(result)
                // If we don't have a selection or the stored selection isn't
                // in the list, fall back to the first corpus.
                if !result.contains(where: { $0.name == selectedCorpus }),
                   let first = result.first?.name
                {
                    selectedCorpus = first
                    preferences.lastUsedCorpus = first
                    query.corpus = first
                    reloadAll()
                }
            } catch let error as APIError {
                corpora = .error(error)
            } catch {
                corpora = .error(.invalidResponse(String(describing: error)))
            }
        }
    }

    func switchCorpus(_ name: String) {
        guard name != selectedCorpus else { return }
        selectedCorpus = name
        preferences.lastUsedCorpus = name
        query.corpus = name
        query.contentType = nil
        query.tag = nil
        query.status = nil
        query.originName = nil
        facets = .idle
        records = .idle
        selectedRecordID = nil
        selectedDetail = .idle
        reloadAll()
    }

    // MARK: - Query mutation

    func applySearch(_ text: String) {
        query.q = text
        query.offset = 0
        reloadRecords()
    }

    func applyKind(_ kind: KindFilter) {
        kindFilter = kind
        query.recordType = kind.recordTypeParam
        query.offset = 0
        reloadRecords()
    }

    func applyFilter(contentType: String? = nil, tag: String? = nil, status: String? = nil, originName: String? = nil) {
        if let contentType { query.contentType = contentType }
        if let tag { query.tag = tag }
        if let status { query.status = status }
        if let originName { query.originName = originName }
        query.offset = 0
        reloadRecords()
    }

    func clearFilter(_ kind: FilterKind) {
        switch kind {
        case .contentType: query.contentType = nil
        case .tag: query.tag = nil
        case .status: query.status = nil
        case .originName: query.originName = nil
        }
        query.offset = 0
        reloadRecords()
    }

    enum FilterKind { case contentType, tag, status, originName }

    /// Active filter chips for the second toolbar row.
    var activeFilters: [(FilterKind, String)] {
        var out: [(FilterKind, String)] = []
        if let v = query.contentType { out.append((.contentType, v)) }
        if let v = query.tag { out.append((.tag, "#\(v)")) }
        if let v = query.status { out.append((.status, v)) }
        if let v = query.originName { out.append((.originName, v)) }
        return out
    }

    // MARK: - Fetches

    func reloadAll() {
        reloadFacets()
        reloadRecords()
        reloadSubmissions()
    }

    func reloadFacets() {
        facets = .loading
        Task {
            do {
                let result = try await client.facets(corpus: query.corpus)
                facets = .loaded(result)
            } catch let error as APIError {
                facets = .error(error)
            } catch {
                facets = .error(.invalidResponse(String(describing: error)))
            }
        }
    }

    func reloadRecords() {
        currentRecordsTask?.cancel()
        records = .loading
        isLoadingMore = false
        var snapshot = query
        snapshot.offset = 0
        query.offset = 0
        currentRecordsTask = Task {
            do {
                let result = try await client.records(query: snapshot)
                try Task.checkCancellation()
                records = .loaded(result)
                lastSync = Date()
                // If the selected record is not in the new page, drop it.
                if let id = selectedRecordID,
                   !result.records.contains(where: { $0.uuid == id })
                {
                    selectedRecordID = nil
                    selectedDetail = .idle
                }
            } catch is CancellationError {
                // ignore
            } catch let error as APIError {
                records = .error(error)
            } catch {
                records = .error(.invalidResponse(String(describing: error)))
            }
        }
    }

    /// True when the loaded page is a strict prefix of the total result set.
    /// Drives the infinite-scroll sentinel and the toolbar "loading more" row.
    var hasMoreRecords: Bool {
        guard case .loaded(let result) = records else { return false }
        return result.records.count < Int(result.total)
    }

    /// Fetch and append the next page of records to the current result.
    /// Noop when there's no more data, when a page is already in-flight, or
    /// when the list is in a non-loaded state. Errors leave the existing
    /// records visible — failing infinite-scroll shouldn't blow the list away.
    func loadMore() {
        guard case .loaded(let current) = records else { return }
        guard !isLoadingMore else { return }
        guard current.records.count < Int(current.total) else { return }

        isLoadingMore = true
        var snapshot = query
        snapshot.offset = UInt64(current.records.count)
        Task {
            do {
                let page = try await client.records(query: snapshot)
                // Merge even if a concurrent filter change landed — only
                // append when the total + query shape still match.
                if case .loaded(let latest) = records,
                   latest.total == page.total
                {
                    let merged = QueryResult(
                        total: page.total,
                        records: latest.records + page.records
                    )
                    records = .loaded(merged)
                }
                isLoadingMore = false
            } catch {
                log.warning("loadMore failed: \(String(describing: error), privacy: .public)")
                isLoadingMore = false
            }
        }
    }

    func reloadSubmissions() {
        submissions = .loading
        Task {
            do {
                let result = try await client.submissions(corpus: query.corpus)
                submissions = .loaded(result)
            } catch let error as APIError {
                submissions = .error(error)
            } catch {
                submissions = .error(.invalidResponse(String(describing: error)))
            }
        }
    }

    // MARK: - Selection

    func select(_ uuid: UUID?) {
        selectedRecordID = uuid
        currentDetailTask?.cancel()

        // Push into selection history unless the caller is the history
        // itself (back/forward). Selecting the same record twice in a row
        // doesn't push.
        if let uuid, !navigatingViaHistory {
            let current = historyIndex >= 0 && historyIndex < selectionHistory.count
                ? selectionHistory[historyIndex] : nil
            if current != uuid {
                // Drop any forward-history past the cursor before pushing.
                if historyIndex < selectionHistory.count - 1 {
                    selectionHistory.removeSubrange((historyIndex + 1)...)
                }
                selectionHistory.append(uuid)
                historyIndex = selectionHistory.count - 1
            }
        }
        navigatingViaHistory = false

        guard let uuid else {
            selectedDetail = .idle
            return
        }
        selectedDetail = .loading
        currentDetailTask = Task {
            do {
                let detail = try await client.record(uuid: uuid)
                try Task.checkCancellation()
                // Guard against a stale response for a later selection.
                guard selectedRecordID == uuid else { return }
                selectedDetail = .loaded(detail)
            } catch is CancellationError {
                // ignore
            } catch let error as APIError {
                selectedDetail = .error(error)
            } catch {
                selectedDetail = .error(.invalidResponse(String(describing: error)))
            }
        }
    }

    // MARK: - Selection history

    var canGoBack: Bool { historyIndex > 0 }
    var canGoForward: Bool {
        historyIndex >= 0 && historyIndex < selectionHistory.count - 1
    }

    func goBack() {
        guard canGoBack else { return }
        historyIndex -= 1
        navigatingViaHistory = true
        select(selectionHistory[historyIndex])
    }

    func goForward() {
        guard canGoForward else { return }
        historyIndex += 1
        navigatingViaHistory = true
        select(selectionHistory[historyIndex])
    }

    var selectedRecord: RecordSummary? {
        guard let id = selectedRecordID,
              let list = records.value?.records
        else { return nil }
        return list.first(where: { $0.uuid == id })
    }

    // MARK: - Health

    private func startHealthPolling() {
        healthTask?.cancel()
        healthTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pingHealth()
                try? await Task.sleep(for: .seconds(10))
            }
        }
    }

    private func pingHealth() async {
        do {
            _ = try await client.health()
            health = .ok
        } catch let error as APIError {
            health = .down(error.localizedDescription)
        } catch {
            health = .down(String(describing: error))
        }
    }

    // MARK: - Access for phase 3 renderers

    func fileURL(for artifact: ArtifactRef, in record: RecordSummary) -> URL? {
        // artifact.ref looks like `artifacts://filename.ext` — strip the scheme.
        guard let filename = artifactFilename(from: artifact.ref) else { return nil }
        return client.fileURL(
            corpus: query.corpus,
            kind: "artifacts",
            uuid: record.uuid,
            filename: filename
        )
    }

    /// Build a file URL for the list/gallery thumbnail of a record, using the
    /// primary-artifact fields carried by `RecordSummary`. Returns `nil` when
    /// the record has no artifact (e.g. document records).
    func thumbnailURL(for record: RecordSummary) -> URL? {
        guard let ref = record.primaryArtifactRef,
              let filename = artifactFilename(from: ref)
        else { return nil }
        return client.fileURL(
            corpus: query.corpus,
            kind: "artifacts",
            uuid: record.uuid,
            filename: filename
        )
    }

    private func artifactFilename(from ref: String) -> String? {
        guard let range = ref.range(of: "://") else { return ref }
        return String(ref[range.upperBound...])
    }
}
