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

    /// Sort artifacts with the most-primary one first. Preference order:
    /// 1. Any artifact flagged `primary: true`.
    /// 2. If none flagged (legacy / partially-migrated records), an
    ///    artifact whose `mimetype` matches the record's `content_type`
    ///    (i.e. what the corpus author considered the canonical form).
    /// 3. Insertion order otherwise.
    ///
    /// This keeps list views and switchers consistent with the user's
    /// expectation that "primary MIME" content is the first thing they see.
    static func orderPrimaryFirst(
        _ refs: [ArtifactRef],
        recordContentType: String
    ) -> [ArtifactRef] {
        if refs.isEmpty { return refs }
        // Fast path: someone is flagged.
        if refs.contains(where: \.primary) {
            let withIdx = refs.enumerated().map { ($0.offset, $0.element) }
            let sorted = withIdx.sorted { lhs, rhs in
                if lhs.1.primary != rhs.1.primary { return lhs.1.primary }
                return lhs.0 < rhs.0
            }
            return sorted.map(\.1)
        }
        // Fallback: promote the artifact whose MIME matches the record's
        // declared primary content-type.
        let target = recordContentType.lowercased()
        guard !target.isEmpty,
              let matchIdx = refs.firstIndex(where: {
                  ($0.mimetype?.lowercased() ?? "") == target
              })
        else {
            return refs
        }
        var reordered = refs
        let promoted = reordered.remove(at: matchIdx)
        reordered.insert(promoted, at: 0)
        return reordered
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

/// Process-wide cache of UTF-8 artifact bodies, keyed by URL. Lives for the
/// lifetime of the app — revisiting the same artifact after navigating away
/// is instant. No byte budget yet; add an LRU if we start loading large
/// text artifacts (see APPLE-UX-NOTES.md).
@MainActor
final class TextArtifactCache {
    static let shared = TextArtifactCache()
    private var entries: [URL: String] = [:]

    func get(_ url: URL) -> String? { entries[url] }
    func set(_ url: URL, _ value: String) { entries[url] = value }
}

/// Thin model for `@State` text loaders used by text / json / email renderers.
/// Fetches UTF-8 text once per URL, short-circuits through `TextArtifactCache`
/// on revisits, and is resilient to rapid URL churn (the `[`/`]` nav in the
/// artifact switcher cancels in-flight loads; we avoid clobbering state for
/// a cancelled task).
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
        // Already showing this URL — nothing to do.
        if case .loaded = state, loadedURL == url { return }
        // Cache hit: skip the spinner entirely so rapid `[`/`]` doesn't
        // flash loading states on content we already have.
        if let cached = TextArtifactCache.shared.get(url) {
            state = .loaded(cached)
            loadedURL = url
            return
        }
        state = .loading
        loadedURL = url
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            // If the task was cancelled mid-flight (user advanced past this
            // artifact before it finished), don't write back to `state` —
            // the successor task will have already set its own state.
            if Task.isCancelled { return }
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                state = .failed("HTTP \(http.statusCode)")
                return
            }
            let text = String(data: data, encoding: .utf8)
                ?? String(data: data, encoding: .isoLatin1)
                ?? ""
            TextArtifactCache.shared.set(url, text)
            state = .loaded(text)
        } catch is CancellationError {
            // Successor task is live; leave state alone.
            return
        } catch {
            if Task.isCancelled { return }
            state = .failed(error.localizedDescription)
        }
    }
}
