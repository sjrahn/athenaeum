import SwiftUI
import WebKit
import AthenaeumKit

/// WKWebView-backed HTML artifact renderer. Shows a small origin / filename
/// strip above the web view so the chrome stays visible even when the page
/// itself has its own top styling.
struct HtmlRender: View {
    @Environment(\.theme) private var theme
    let artifact: ArtifactRef
    let url: URL
    let detail: RecordDetail

    var body: some View {
        VStack(spacing: 0) {
            header
            Hairline()
            WebViewRepresentable(url: url)
            RendererFooter(
                filename: ArtifactRefHelpers.filename(from: artifact.ref),
                detail: artifact.mimetype ?? "text/html",
                fileURL: url
            )
        }
    }

    private var header: some View {
        let fm = detail.record.frontmatter
        let origin = fm.originName ?? fm.originUrl ?? "(no origin)"
        return HStack(spacing: 8) {
            Text(origin)
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.muted)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer(minLength: 4)
            Text(ArtifactRefHelpers.filename(from: artifact.ref))
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
                .lineLimit(1)
        }
        .padding(.horizontal, 14)
        .frame(height: 24)
        .background(theme.tokens.surface2)
    }
}

#if os(macOS)
import AppKit

private struct WebViewRepresentable: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let view = WKWebView(frame: .zero, configuration: config)
        view.load(URLRequest(url: url))
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        if view.url != url {
            view.load(URLRequest(url: url))
        }
    }
}
#else
import UIKit

private struct WebViewRepresentable: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let view = WKWebView(frame: .zero, configuration: config)
        view.load(URLRequest(url: url))
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        if view.url != url {
            view.load(URLRequest(url: url))
        }
    }
}
#endif
