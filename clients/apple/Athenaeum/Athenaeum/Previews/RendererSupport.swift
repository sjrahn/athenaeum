import SwiftUI
import AthenaeumKit

/// Stable kind label for per-MIME renderer dispatch. Keeps `OriginalView`
/// single-site for picking which view to show; each renderer is then a thin
/// wrapper over a system component (PDFKit, AVKit, WKWebView, etc.).
enum RendererKind {
    case pdf, video, audio, html, image, email, text, json, generic

    /// Dispatch on the artifact's advertised MIME first, then fall back to the
    /// record's primary `content_type` if the artifact has none. Both fields
    /// are tolerant on v9 corpora so we defensively double-check.
    static func dispatch(mime: String?) -> RendererKind {
        let key = MimeChip.shortKey(for: mime ?? "")
        switch key {
        case "pdf": return .pdf
        case "mp4": return .video
        case "mp3": return .audio
        case "html": return .html
        case "png", "jpg": return .image
        case "eml": return .email
        case "md", "vtt": return .text
        case "json": return .json
        default:
            // Tolerant fallbacks for mimes that `shortKey` doesn't recognise
            // but whose prefix is enough to pick a bucket.
            let lower = (mime ?? "").lowercased()
            if lower.hasPrefix("video/") { return .video }
            if lower.hasPrefix("audio/") { return .audio }
            if lower.hasPrefix("image/") { return .image }
            if lower.hasPrefix("text/") { return .text }
            if lower.hasPrefix("application/json") { return .json }
            return .generic
        }
    }
}

/// Utilities shared across the Original tab. Keep them centralised so the
/// various renderers agree on filename derivation and byte formatting.
enum ArtifactRefHelpers {
    /// Strip the `artifacts://` / `assets://` prefix from a ref to get the
    /// on-disk filename used by the `/api/files/{corpus}/{kind}/{uuid}/{name}`
    /// endpoint. Falls back to the whole string if the scheme isn't present.
    static func filename(from ref: String) -> String {
        guard let range = ref.range(of: "://") else { return ref }
        return String(ref[range.upperBound...])
    }

    /// File extension in lowercase, no dot. Empty string when none.
    static func fileExtension(for ref: String) -> String {
        let name = filename(from: ref)
        if let dot = name.lastIndex(of: ".") {
            return String(name[name.index(after: dot)...]).lowercased()
        }
        return ""
    }
}

/// 40pt footer strip used by most renderers — filename on the left, action
/// buttons on the right (Open externally, Quick Look). Keeps the chrome
/// identical across renderers so the eye doesn't have to re-learn layout.
struct RendererFooter: View {
    @Environment(\.theme) private var theme
    let filename: String
    let detail: String?
    let fileURL: URL?

    var body: some View {
        HStack(spacing: 8) {
            Text(filename)
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.muted)
                .lineLimit(1)
                .truncationMode(.middle)
            if let detail, !detail.isEmpty {
                Text("·")
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)
                Text(detail)
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            if let fileURL {
                #if os(macOS)
                Btn(.ghost, action: {
                    NSWorkspace.shared.open(fileURL)
                }) {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.forward.square")
                        Text("open externally")
                    }
                }
                #else
                OpenExternallyButton(fileURL: fileURL)
                #endif
            }
        }
        .padding(.horizontal, 14)
        .frame(height: 40)
        .background(theme.tokens.surface2)
        .overlay(alignment: .top) { Hairline() }
    }
}

#if !os(macOS)
/// iOS button wrapper so we can reach the `openURL` environment.
private struct OpenExternallyButton: View {
    @Environment(\.openURL) private var openURL
    let fileURL: URL
    var body: some View {
        Btn(.ghost, action: { openURL(fileURL) }) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.up.forward.square")
                Text("open externally")
            }
        }
    }
}
#endif

/// Centered error banner used by renderers that couldn't load content.
struct RendererErrorView: View {
    @Environment(\.theme) private var theme
    let message: String

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .foregroundStyle(theme.tokens.warn)
                .font(.system(size: 18))
            Text(message)
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.muted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.tokens.surface)
    }
}

/// Spinner used while a renderer is fetching text content.
struct RendererLoadingView: View {
    @Environment(\.theme) private var theme
    var body: some View {
        VStack(spacing: 6) {
            ProgressView().controlSize(.small)
            Text("loading…")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.tokens.surface)
    }
}

/// Thin model for `@State` text loaders used by text / json / email renderers.
/// Fetches UTF-8 text once per URL and caches the result.
@Observable
@MainActor
final class TextArtifactLoader {
    enum State {
        case idle, loading
        case loaded(String)
        case failed(String)
    }

    private(set) var state: State = .idle
    private var loadedURL: URL?

    func load(_ url: URL) async {
        if case .loaded = state, loadedURL == url { return }
        state = .loading
        loadedURL = url
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                state = .failed("HTTP \(http.statusCode)")
                return
            }
            let text = String(data: data, encoding: .utf8)
                ?? String(data: data, encoding: .isoLatin1)
                ?? ""
            state = .loaded(text)
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}
