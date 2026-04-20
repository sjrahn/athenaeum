import SwiftUI
import AthenaeumKit

/// Tabbed detail shell. For source records: `original | normalized |
/// artifacts | metadata`. For document records: `normalized | dependencies |
/// metadata`.
///
/// All five tab panes (`OriginalView`, `NormalizedView`, `ArtifactsView`,
/// `DependenciesView`, `MetadataView`) live under `Athenaeum/Previews/` and
/// are shared with `QuickLookWindow` / `DetailWindow`.
struct DocPreview: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density
    @Environment(BrowseStore.self) private var store
    @Environment(\.openWindow) private var openWindow

    @State private var selectedTab: DetailTab = .original
    /// When the user clicks an artifact row on the Artifacts tab, we stash
    /// its ref here and switch to the Original tab; `OriginalView` consumes
    /// the value on appear / change and resets it to nil.
    @State private var pendingArtifactRef: String?

    var body: some View {
        VStack(spacing: 0) {
            switch store.selectedDetail {
            case .idle:
                placeholder("select a record to preview")
            case .loading:
                loading
            case .loaded(let detail):
                loaded(detail)
            case .error(let err):
                errorView(err)
            }
        }
        .background(theme.tokens.bg)
    }

    @ViewBuilder
    private func loaded(_ detail: RecordDetail) -> some View {
        let tabs = availableTabs(for: detail.record.frontmatter.recordType)
        let active = tabs.contains(selectedTab) ? selectedTab : tabs.first ?? .metadata

        VStack(spacing: 0) {
            header(detail: detail)
            Hairline()
            tabBar(tabs: tabs, active: active)
            Hairline()
            tabContent(detail: detail, tab: active)
        }
        .onChange(of: detail.record.frontmatter.uuid) { _, _ in
            if !tabs.contains(selectedTab) { selectedTab = tabs.first ?? .metadata }
        }
    }

    // MARK: - Header

    private func header(detail: RecordDetail) -> some View {
        let fm = detail.record.frontmatter
        return HStack(alignment: .center, spacing: 8) {
            KindChip(recordType: fm.recordType)
            MimeChip(mime: fm.contentType)
            VStack(alignment: .leading, spacing: 2) {
                Text(fm.title.isEmpty ? "(untitled)" : fm.title)
                    .font(.athenaeum(.sans, size: 13, weight: .semibold))
                    .foregroundStyle(theme.tokens.text)
                    .lineLimit(1)
                Text(metaLine(detail: detail))
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.muted)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Btn(.ghost, action: { openDetailWindow(uuid: fm.uuid) }) {
                Text("new window")
            }
            Btn(.ghost, action: { openQuickLook() }) {
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

    // MARK: - Tab bar

    private func tabBar(tabs: [DetailTab], active: DetailTab) -> some View {
        HStack(spacing: 0) {
            ForEach(tabs, id: \.self) { tab in
                tabChip(tab: tab, selected: tab == active)
            }
            Spacer(minLength: 8)
            HStack(spacing: 4) {
                ForEach(Array(tabs.prefix(4).enumerated()), id: \.offset) { idx, _ in
                    Kbd("⌘\(idx + 1)")
                }
            }
            .padding(.trailing, 8)
        }
        .padding(.horizontal, 8)
        .frame(height: 28)
        .background(theme.tokens.surface2)
    }

    private func tabChip(tab: DetailTab, selected: Bool) -> some View {
        Button {
            selectedTab = tab
        } label: {
            Text(tab.label)
                .font(.athenaeum(.mono, size: 10, weight: selected ? .semibold : .regular))
                .foregroundStyle(selected ? theme.tokens.accent : theme.tokens.muted)
                .padding(.horizontal, 10)
                .frame(height: 28)
                .overlay(alignment: .bottom) {
                    Rectangle()
                        .fill(selected ? theme.tokens.accent : Color.clear)
                        .frame(height: 2)
                }
                // `.contentShape` must live *inside* the Button's label so
                // the entire padded rect is hit-tested, not just the text.
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - Tab content

    @ViewBuilder
    private func tabContent(detail: RecordDetail, tab: DetailTab) -> some View {
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

    // MARK: - States

    private var loading: some View {
        VStack {
            Spacer()
            ProgressView().controlSize(.small)
            Spacer()
        }
        .frame(maxWidth: .infinity)
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

    private func placeholder(_ text: String) -> some View {
        Text(text)
            .font(.athenaeum(.mono, size: 11))
            .foregroundStyle(theme.tokens.dim)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Tabs

    private func availableTabs(for type: RecordType) -> [DetailTab] {
        switch type {
        case .source: [.original, .normalized, .artifacts, .metadata]
        case .document: [.normalized, .dependencies, .metadata]
        }
    }

    private func openDetailWindow(uuid: UUID) {
        openWindow(id: "detail", value: uuid)
    }

    private func openQuickLook() {
        openWindow(id: "quicklook")
    }
}

enum DetailTab: Hashable {
    case original, normalized, artifacts, dependencies, metadata

    var label: String {
        switch self {
        case .original: "original"
        case .normalized: "normalized"
        case .artifacts: "artifacts"
        case .dependencies: "dependencies"
        case .metadata: "metadata"
        }
    }
}
