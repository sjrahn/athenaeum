import SwiftUI
import AthenaeumKit
#if canImport(PDFKit)
import PDFKit
#endif

/// Renders PDF artifacts via PDFKit. PDFKit opens URLs directly and issues
/// Range requests against the server automatically — no need to download the
/// whole file up-front. Display mode is single-page continuous for natural
/// vertical scroll.
struct PDFRender: View {
    @Environment(\.theme) private var theme
    let artifact: ArtifactRef
    let url: URL

    var body: some View {
        VStack(spacing: 0) {
            #if canImport(PDFKit)
            PDFViewRepresentable(url: url)
                .background(theme.tokens.surface2)
            #else
            RendererErrorView(message: "PDFKit not available on this platform")
            #endif
            RendererFooter(
                filename: ArtifactRefHelpers.filename(from: artifact.ref),
                detail: "application/pdf",
                fileURL: url
            )
        }
    }
}

#if canImport(PDFKit)

#if os(macOS)
import AppKit

private struct PDFViewRepresentable: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical
        view.backgroundColor = .clear
        if let doc = PDFDocument(url: url) {
            view.document = doc
        }
        return view
    }

    func updateNSView(_ view: PDFView, context: Context) {
        if view.document?.documentURL != url {
            view.document = PDFDocument(url: url)
        }
    }
}
#else
import UIKit

private struct PDFViewRepresentable: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical
        view.backgroundColor = .clear
        if let doc = PDFDocument(url: url) {
            view.document = doc
        }
        return view
    }

    func updateUIView(_ view: PDFView, context: Context) {
        if view.document?.documentURL != url {
            view.document = PDFDocument(url: url)
        }
    }
}
#endif // os(macOS)

#endif // canImport(PDFKit)
