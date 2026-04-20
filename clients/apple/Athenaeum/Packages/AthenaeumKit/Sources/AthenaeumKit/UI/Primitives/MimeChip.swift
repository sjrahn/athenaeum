import SwiftUI

/// 34×14pt solid-color chip with white 9pt SemiBold mono uppercase text. Color
/// per primary MIME; unknown mimes fall back to `#555`.
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

    public static func shortKey(for mime: String) -> String {
        let lower = mime.lowercased()
        if lower.hasPrefix("application/pdf") { return "pdf" }
        if lower.hasPrefix("video/mp4") { return "mp4" }
        if lower.hasPrefix("audio/mpeg") { return "mp3" }
        if lower.hasPrefix("text/html") { return "html" }
        if lower.hasPrefix("image/png") { return "png" }
        if lower.hasPrefix("image/jpeg") { return "jpg" }
        if lower.hasPrefix("message/rfc822") { return "eml" }
        if lower.hasPrefix("text/markdown") { return "md" }
        if lower.hasPrefix("application/json") { return "json" }
        if lower.hasPrefix("text/vtt") { return "vtt" }
        // Fallback: last path component after `/` or `+`, uppercased
        if let slash = lower.lastIndex(of: "/") {
            let tail = lower[lower.index(after: slash)...]
            if let plus = tail.firstIndex(of: "+") {
                return String(tail[..<plus])
            }
            return String(tail)
        }
        return lower
    }

    static func label(for mime: String) -> String {
        shortKey(for: mime).uppercased()
    }

    static func color(for mime: String) -> Color {
        switch shortKey(for: mime) {
        case "pdf": Color(hex: "#b00020")
        case "mp4": Color(hex: "#7a4a8a")
        case "html": Color(hex: "#4a6b8a")
        case "mp3": Color(hex: "#8a6a3a")
        case "png", "jpg": Color(hex: "#3a6a7a")
        case "eml": Color(hex: "#6a5a3a")
        case "md": Color(hex: "#4a4a4a")
        case "json": Color(hex: "#4a7a4a")
        case "vtt": Color(hex: "#7a6a4a")
        default: Color(hex: "#555555")
        }
    }
}
