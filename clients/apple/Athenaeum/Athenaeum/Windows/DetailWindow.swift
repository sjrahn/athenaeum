import SwiftUI
import AthenaeumKit

/// Standalone detail window opened by `openWindow(id: "detail", value: uuid)`.
/// Owns its own `APIClient` fetch for the given UUID and renders the full
/// tabbed layout shared with the embedded `DocPreview`. Survives
/// independently of the main browse window so the user can keep multiple
/// records open side by side.
///
/// The BrowseStore is injected from the app scene — we use it for corpus
/// context (for building artifact file URLs) but don't depend on its
/// selection state.
struct DetailWindow: View {
    @Environment(\.theme) private var theme
    @Environment(\.openWindow) private var openWindow
    @Environment(PreferencesStore.self) private var preferences
    let uuid: UUID

    @State private var detail: LoadState<RecordDetail> = .idle
    @State private var selectedTab: DetailTab = .original
    @State private var pendingArtifactRef: String?

    var body: some View {
        VStack(spacing: 0) {
            switch detail {
            case .loaded(let d):
                loaded(d)
            case .loading:
                ProgressView().controlSize(.small).frame(maxWidth: .infinity, maxHeight: .infinity)
            case .idle:
                Color.clear
            case .error(let err):
                errorView(err)
            }
        }
        .frame(minWidth: 640, idealWidth: 840, minHeight: 520, idealHeight: 640)
        .background(theme.tokens.bg)
        .task(id: uuid) { load() }
    }

    private func load() {
        detail = .loading
        Task {
            do {
                let client = APIClient(baseURL: preferences.serverURL)
                let result = try await client.record(uuid: uuid)
                detail = .loaded(result)
            } catch let error as APIError {
                detail = .error(error)
            } catch {
                detail = .error(.invalidResponse(String(describing: error)))
            }
        }
    }

    @ViewBuilder
    private func loaded(_ d: RecordDetail) -> some View {
        let fm = d.record.frontmatter
        let tabs = availableTabs(for: fm.recordType)
        let active = tabs.contains(selectedTab) ? selectedTab : tabs.first ?? .metadata

        VStack(spacing: 0) {
            header(detail: d)
            Hairline()
            tabBar(tabs: tabs, active: active)
            Hairline()
            content(detail: d, tab: active)
        }
        .onChange(of: d.record.frontmatter.uuid) { _, _ in
            if !tabs.contains(selectedTab) { selectedTab = tabs.first ?? .metadata }
        }
    }

    private func header(detail: RecordDetail) -> some View {
        let fm = detail.record.frontmatter
        return HStack(spacing: 8) {
            KindChip(recordType: fm.recordType)
            MimeChip(mime: fm.contentType)
            VStack(alignment: .leading, spacing: 2) {
                Text(fm.title.isEmpty ? "(untitled)" : fm.title)
                    .font(.athenaeum(.sans, size: 14, weight: .semibold))
                    .foregroundStyle(theme.tokens.text)
                    .lineLimit(1)
                Text(metaLine(detail: detail))
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.muted)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Btn(.ghost, action: { openWindow(id: "quicklook") }) {
                HStack(spacing: 4) { Text("quick look"); Kbd("⇧⌘Y") }
            }
        }
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(theme.tokens.surface)
    }

    private func metaLine(detail: RecordDetail) -> String {
        let fm = detail.record.frontmatter
        switch fm.recordType {
        case .source:
            var parts: [String] = []
            if let origin = fm.originName ?? fm.originUrl { parts.append(origin) }
            parts.append("\(fm.artifactRefs.count) artifacts")
            if let cap = fm.captureDate { parts.append("captured \(cap)") }
            return parts.joined(separator: " · ")
        case .document:
            var parts: [String] = []
            parts.append("↳ \(fm.constituents?.count ?? 0) records")
            if let norm = fm.normalizationDate { parts.append("normalized \(norm)") }
            return parts.joined(separator: " · ")
        }
    }

    private func availableTabs(for type: RecordType) -> [DetailTab] {
        switch type {
        case .source: [.original, .normalized, .artifacts, .metadata]
        case .document: [.normalized, .dependencies, .metadata]
        }
    }

    private func tabBar(tabs: [DetailTab], active: DetailTab) -> some View {
        HStack(spacing: 0) {
            ForEach(tabs, id: \.self) { tab in
                Button { selectedTab = tab } label: {
                    Text(tab.label)
                        .font(.athenaeum(.mono, size: 10, weight: tab == active ? .semibold : .regular))
                        .foregroundStyle(tab == active ? theme.tokens.accent : theme.tokens.muted)
                        .padding(.horizontal, 10)
                        .frame(height: 28)
                        .overlay(alignment: .bottom) {
                            Rectangle()
                                .fill(tab == active ? theme.tokens.accent : Color.clear)
                                .frame(height: 2)
                        }
                }
                .buttonStyle(.plain)
                .contentShape(Rectangle())
            }
            Spacer()
        }
        .padding(.horizontal, 8)
        .frame(height: 28)
        .background(theme.tokens.surface2)
    }

    @ViewBuilder
    private func content(detail: RecordDetail, tab: DetailTab) -> some View {
        switch tab {
        case .original:
            OriginalView(
                detail: detail,
                targetArtifactRef: pendingArtifactRef,
                onTargetConsumed: { pendingArtifactRef = nil }
            )
        case .normalized:
            NormalizedView(detail: detail)
        case .artifacts:
            ArtifactsView(detail: detail) { ref in
                pendingArtifactRef = ref.ref
                selectedTab = .original
            }
        case .dependencies:
            DependenciesView(detail: detail)
        case .metadata:
            MetadataView(detail: detail)
        }
    }

    private func errorView(_ err: APIError) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(theme.tokens.err)
            Text(err.localizedDescription)
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.muted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
