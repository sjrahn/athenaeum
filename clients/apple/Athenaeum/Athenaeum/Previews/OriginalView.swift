import SwiftUI
import AthenaeumKit

/// The `original` tab's content. Shows the `ArtifactSwitcher` at the top,
/// then dispatches to the per-MIME renderer matching the currently-selected
/// artifact. Resets the index to 0 whenever the record changes.
///
/// `[` / `]` advance and retreat the switcher index — handled via
/// `.onKeyPress` on this view's focus region.
struct OriginalView: View {
    @Environment(\.theme) private var theme
    @Environment(BrowseStore.self) private var store

    let detail: RecordDetail
    @State private var index: Int = 0
    @FocusState private var focused: Bool

    private var orderedArtifacts: [ArtifactRef] {
        let refs = detail.record.frontmatter.artifactRefs
        // Primary first, then insertion order; stable sort keeps ties.
        let withIdx = refs.enumerated().map { ($0.offset, $0.element) }
        let sorted = withIdx.sorted { lhs, rhs in
            if lhs.1.primary != rhs.1.primary { return lhs.1.primary }
            return lhs.0 < rhs.0
        }
        return sorted.map(\.1)
    }

    var body: some View {
        let artifacts = orderedArtifacts
        return Group {
            if artifacts.isEmpty {
                empty
            } else {
                VStack(spacing: 0) {
                    ArtifactSwitcher(
                        artifacts: artifacts,
                        index: Binding(
                            get: { min(index, max(0, artifacts.count - 1)) },
                            set: { index = $0 }
                        )
                    )
                    content(for: artifacts[min(index, artifacts.count - 1)])
                }
            }
        }
        .focusable()
        .focused($focused)
        .onAppear { focused = true }
        .onKeyPress("[") {
            index = max(0, index - 1)
            return .handled
        }
        .onKeyPress("]") {
            index = min(artifacts.count - 1, index + 1)
            return .handled
        }
        .onChange(of: detail.record.frontmatter.uuid) { _, _ in
            index = 0
        }
    }

    @ViewBuilder
    private func content(for artifact: ArtifactRef) -> some View {
        if let summary = currentSummary,
           let url = store.fileURL(for: artifact, in: summary)
        {
            dispatch(artifact: artifact, url: url)
        } else {
            RendererErrorView(message: "couldn't build artifact url")
        }
    }

    @ViewBuilder
    private func dispatch(artifact: ArtifactRef, url: URL) -> some View {
        let mime = artifact.mimetype ?? detail.record.frontmatter.contentType
        switch RendererKind.dispatch(mime: mime) {
        case .pdf:
            PDFRender(artifact: artifact, url: url)
        case .video:
            VideoRender(artifact: artifact, url: url)
        case .audio:
            AudioRender(artifact: artifact, url: url)
        case .html:
            HtmlRender(artifact: artifact, url: url, detail: detail)
        case .image:
            ImageRender(artifact: artifact, url: url)
        case .email:
            EmailRender(artifact: artifact, url: url)
        case .text:
            TextRender(artifact: artifact, url: url)
        case .json:
            JsonRender(artifact: artifact, url: url)
        case .generic:
            GenericBinaryRender(artifact: artifact, url: url)
        }
    }

    private var currentSummary: RecordSummary? {
        // Prefer the live summary from the current list (cheapest path); fall
        // back to building one from the record detail itself for windows that
        // aren't bound to the browse store's list.
        if let live = store.selectedRecord, live.uuid == detail.record.frontmatter.uuid {
            return live
        }
        let fm = detail.record.frontmatter
        return RecordSummary(
            uuid: fm.uuid,
            title: fm.title,
            status: fm.status.rawValue,
            contentType: fm.contentType,
            recordType: fm.recordType.rawValue,
            tags: fm.tags,
            visibility: fm.visibility
        )
    }

    private var empty: some View {
        VStack(spacing: 6) {
            Text("no artifacts")
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.dim)
            Text("this record carries only a normalized body; see the `normalized` tab")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.tokens.bg)
    }
}
