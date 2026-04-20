import SwiftUI

/// 34×14pt solid-color chip with white 9pt SemiBold mono uppercase text. Color
/// reflects the **logical MIME group** (audio / video / image / document /
/// web / structured / message / text / unknown), so records in the same
/// family share a chip colour and the eye learns one palette, not N.
public struct MimeChip: View {
    private let mime: String

    /// Short label derived from the MIME string. Full MIME recommended.
    public init(mime: String) { self.mime = mime }

    public var body: some View {
        Text(Self.label(for: mime))
            .font(.athenaeum(.mono, size: 9, weight: .semibold))
            .tracking(0.6)
            .foregroundStyle(.white)
            .frame(width: 34, height: 14)
            .background(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(Self.color(for: mime))
            )
    }

    /// Short key used for both the chip label (uppercased) and group-colour
    /// dispatch. Public because app-side thumbnails and renderer dispatch
    /// reuse the same MIME buckets.
    public static func shortKey(for mime: String) -> String {
        let lower = mime.lowercased()
        if lower.isEmpty { return "unkn" }
        if lower == "unknown" { return "unkn" }
        if lower.hasPrefix("application/pdf") { return "pdf" }
        if lower.hasPrefix("application/epub") { return "epub" }
        if lower.hasPrefix("video/mp4") { return "mp4" }
        if lower.hasPrefix("video/quicktime") { return "mov" }
        if lower.hasPrefix("video/webm") { return "webm" }
        if lower.hasPrefix("audio/mpeg") { return "mp3" }
        if lower.hasPrefix("audio/x-m4a") || lower.hasPrefix("audio/mp4") { return "m4a" }
        if lower.hasPrefix("audio/x-m4b") { return "m4b" }
        if lower.hasPrefix("audio/wav") || lower.hasPrefix("audio/x-wav") { return "wav" }
        if lower.hasPrefix("audio/ogg") { return "ogg" }
        if lower.hasPrefix("text/html") { return "html" }
        if lower.hasPrefix("image/png") { return "png" }
        if lower.hasPrefix("image/jpeg") { return "jpg" }
        if lower.hasPrefix("image/gif") { return "gif" }
        if lower.hasPrefix("image/webp") { return "webp" }
        if lower.hasPrefix("message/rfc822") { return "eml" }
        if lower.hasPrefix("text/markdown") { return "md" }
        if lower.hasPrefix("application/json") { return "json" }
        if lower.hasPrefix("application/xml") || lower.hasPrefix("text/xml") { return "xml" }
        if lower.hasPrefix("application/yaml") || lower.hasPrefix("text/yaml") { return "yaml" }
        if lower.hasPrefix("text/vtt") { return "vtt" }
        if lower.hasPrefix("text/plain") { return "txt" }
        // Fallback: last path component after `/`, strip `x-` vendor prefix
        // and trailing `+suffix` (e.g. `image/svg+xml` → `svg`).
        if let slash = lower.lastIndex(of: "/") {
            var tail = String(lower[lower.index(after: slash)...])
            if tail.hasPrefix("x-") { tail.removeFirst(2) }
            if let plus = tail.firstIndex(of: "+") { tail = String(tail[..<plus]) }
            // Cap display length — the chip is 34pt so more than ~5 chars
            // overflows. Prefer the first segment of a hyphenated tail.
            if let dash = tail.firstIndex(of: "-") { tail = String(tail[..<dash]) }
            return tail.isEmpty ? "unkn" : tail
        }
        return "unkn"
    }

    /// Logical group the MIME falls into — drives the chip colour.
    public enum MimeGroup: Sendable {
        case audio, video, image, document, web, structured, message, text, unknown
    }

    public static func group(for mime: String) -> MimeGroup {
        let lower = mime.lowercased()
        if lower == "unknown" || lower.isEmpty { return .unknown }
        if lower.hasPrefix("audio/") { return .audio }
        if lower.hasPrefix("video/") { return .video }
        if lower.hasPrefix("image/") { return .image }
        if lower.hasPrefix("application/pdf") || lower.hasPrefix("application/epub") {
            return .document
        }
        if lower.hasPrefix("text/html") { return .web }
        if lower.hasPrefix("application/json")
            || lower.hasPrefix("application/xml")
            || lower.hasPrefix("text/xml")
            || lower.hasPrefix("application/yaml")
            || lower.hasPrefix("text/yaml")
        {
            return .structured
        }
        if lower.hasPrefix("message/") { return .message }
        if lower.hasPrefix("text/") { return .text }
        return .unknown
    }

    static func label(for mime: String) -> String {
        shortKey(for: mime).uppercased()
    }

    static func color(for mime: String) -> Color {
        switch group(for: mime) {
        case .audio: Color(hex: "#8a6a3a") // warm brown
        case .video: Color(hex: "#7a4a8a") // purple
        case .image: Color(hex: "#3a7a7a") // teal
        case .document: Color(hex: "#b24040") // red (pdf, epub)
        case .web: Color(hex: "#4a6b8a") // steel blue
        case .structured: Color(hex: "#4a7a4a") // green (json/xml/yaml)
        case .message: Color(hex: "#8a7a3a") // olive (eml)
        case .text: Color(hex: "#5a5a5a") // neutral gray
        case .unknown: Color(hex: "#555555") // dim gray
        }
    }
}
