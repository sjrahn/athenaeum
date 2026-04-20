import SwiftUI
import AthenaeumKit

/// JSON artifact renderer. Downloads the text, pretty-prints if it parses
/// cleanly, otherwise falls back to the raw bytes. Renders in mono with
/// `pre` whitespace so structural indentation survives.
struct JsonRender: View {
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
                detail: artifact.mimetype ?? "application/json",
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
            Text("application/json")
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
            let pretty = prettyPrint(text) ?? text
            ScrollView([.vertical, .horizontal]) {
                Text(pretty.isEmpty ? "(empty)" : pretty)
                    .font(.athenaeum(.mono, size: 11))
                    .foregroundStyle(theme.tokens.text)
                    .textSelection(.enabled)
                    .lineSpacing(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            }
            .background(theme.tokens.surface)
        }
    }

    private func prettyPrint(_ text: String) -> String? {
        guard let data = text.data(using: .utf8),
              let parsed = try? JSONSerialization.jsonObject(with: data, options: .fragmentsAllowed),
              let out = try? JSONSerialization.data(
                withJSONObject: parsed,
                options: [.prettyPrinted, .sortedKeys]
              ),
              let prettyString = String(data: out, encoding: .utf8)
        else { return nil }
        return prettyString
    }
}
