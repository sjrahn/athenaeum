import SwiftUI
import AthenaeumKit

/// Plain-text / markdown / vtt / subtitles renderer. Downloads UTF-8, shows
/// in mono with `pre-wrap` line breaks. No parsing — the text is the text.
/// Sibling `JsonRender` covers application/json with the same plumbing.
struct TextRender: View {
    @Environment(\.theme) private var theme
    let artifact: ArtifactRef
    let url: URL

    @State private var loader = TextArtifactLoader()

    var body: some View {
        VStack(spacing: 0) {
            metaStrip
            content
            RendererFooter(
                filename: ArtifactRefHelpers.filename(from: artifact.ref),
                detail: artifact.mimetype ?? "text/plain",
                fileURL: url
            )
        }
        .task(id: url) { await loader.load(url) }
    }

    private var metaStrip: some View {
        HStack(spacing: 6) {
            Text(ArtifactRefHelpers.filename(from: artifact.ref))
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.muted)
            Text("·")
                .foregroundStyle(theme.tokens.dim)
            Text(artifact.mimetype ?? "text/plain")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
            Spacer()
        }
        .padding(.horizontal, 14)
        .frame(height: 24)
        .background(theme.tokens.surface2)
        .overlay(alignment: .bottom) { Hairline() }
    }

    @ViewBuilder
    private var content: some View {
        switch loader.state {
        case .idle, .loading:
            RendererLoadingView()
        case .failed(let msg):
            RendererErrorView(message: msg)
        case .loaded(let text):
            ScrollView([.vertical, .horizontal]) {
                Text(text.isEmpty ? "(empty)" : text)
                    .font(.athenaeum(.mono, size: 11))
                    .foregroundStyle(theme.tokens.text)
                    .textSelection(.enabled)
                    .lineSpacing(4)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            }
            .background(theme.tokens.surface)
        }
    }
}
