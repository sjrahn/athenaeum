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

    // MARK: - Dependencies

    private let client: APIClient
    private let log = Logger(subsystem: "dev.rahn.athenaeum", category: "browse")
    private let preferences: PreferencesStore

    private var healthTask: Task<Void, Never>?
    private var currentRecordsTask: Task<Void, Never>?
    private var currentDetailTask: Task<Void, Never>?

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
        let snapshot = query
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

    private func artifactFilename(from ref: String) -> String? {
        guard let range = ref.range(of: "://") else { return ref }
        return String(ref[range.upperBound...])
    }
}
