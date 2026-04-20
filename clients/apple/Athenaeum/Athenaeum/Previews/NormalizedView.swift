import SwiftUI
import AthenaeumKit

/// Renders the normalized markdown body in IBM Plex Sans. Uses SwiftUI's
/// built-in `AttributedString(markdown:)` which handles inline formatting
/// (bold/italic/code/links) for free; headings and paragraph styling are
/// applied after the fact.
///
/// Max content width is clamped to 720pt per the design — wider windows get
/// margin, not line length.
struct NormalizedView: View {
    @Environment(\.theme) private var theme
    let detail: RecordDetail

    private let maxContentWidth: CGFloat = 720

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                metaLine
                if detail.record.body.isEmpty {
                    empty
                } else {
                    body(for: detail.record.body)
                }
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 20)
            .frame(maxWidth: maxContentWidth, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(theme.tokens.bg)
    }

    private var metaLine: some View {
        let fm = detail.record.frontmatter
        var parts: [String] = ["normalized", "markdown"]
        if let ts = fm.normalizationDate { parts.append(ts) }
        if fm.recordType == .source, !fm.artifactRefs.isEmpty {
            parts.append("synthesis of \(fm.artifactRefs.count) artifacts")
        } else if fm.recordType == .document, let c = fm.constituents {
            parts.append("merged from \(c.count) sources")
        }
        return Text(parts.joined(separator: " · "))
            .font(.athenaeum(.mono, size: 10))
            .foregroundStyle(theme.tokens.dim)
    }

    private var empty: some View {
        Text("(empty body)")
            .font(.athenaeum(.mono, size: 11))
            .foregroundStyle(theme.tokens.dim)
    }

    /// Lightweight markdown renderer. We split on blank lines into "blocks"
    /// and style each block based on its prefix. Inline emphasis / links /
    /// inline code are handled by `AttributedString(markdown:)`.
    private func body(for markdown: String) -> some View {
        let blocks = splitBlocks(markdown)
        return VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                block.view(theme: theme)
            }
        }
    }

    private func splitBlocks(_ text: String) -> [MarkdownBlock] {
        var out: [MarkdownBlock] = []
        var buffer: [String] = []
        func flush() {
            guard !buffer.isEmpty else { return }
            let joined = buffer.joined(separator: "\n")
            out.append(MarkdownBlock.from(joined))
            buffer.removeAll(keepingCapacity: true)
        }
        for raw in text.split(separator: "\n", omittingEmptySubsequences: false) {
            let line = String(raw)
            if line.trimmingCharacters(in: .whitespaces).isEmpty {
                flush()
            } else {
                buffer.append(line)
            }
        }
        flush()
        return out
    }
}

private enum MarkdownBlock {
    case h1(String)
    case h2(String)
    case h3(String)
    case quote(String)
    case code(String)
    case bullet([String])
    case paragraph(String)

    static func from(_ raw: String) -> MarkdownBlock {
        let lines = raw.split(separator: "\n").map(String.init)
        guard let first = lines.first else { return .paragraph(raw) }
        if first.hasPrefix("### ") {
            return .h3(String(first.dropFirst(4)))
        }
        if first.hasPrefix("## ") {
            return .h2(String(first.dropFirst(3)))
        }
        if first.hasPrefix("# ") {
            return .h1(String(first.dropFirst(2)))
        }
        if first.hasPrefix("> ") {
            let stripped = lines.map { $0.hasPrefix("> ") ? String($0.dropFirst(2)) : $0 }
            return .quote(stripped.joined(separator: "\n"))
        }
        if first.hasPrefix("```") {
            // Treat the whole block as code — strip opening / closing fences.
            let trimmed = lines.dropFirst().filter { !$0.hasPrefix("```") }
            return .code(trimmed.joined(separator: "\n"))
        }
        if first.hasPrefix("- ") || first.hasPrefix("* ") {
            let items = lines.compactMap { line -> String? in
                if line.hasPrefix("- ") { return String(line.dropFirst(2)) }
                if line.hasPrefix("* ") { return String(line.dropFirst(2)) }
                return nil
            }
            return .bullet(items)
        }
        return .paragraph(raw)
    }

    @ViewBuilder
    func view(theme: Theme) -> some View {
        switch self {
        case .h1(let text):
            Text(text)
                .font(.athenaeum(.sans, size: 18, weight: .bold))
                .foregroundStyle(theme.tokens.text)
                .padding(.top, 4)
        case .h2(let text):
            Text(text)
                .font(.athenaeum(.sans, size: 14, weight: .semibold))
                .foregroundStyle(theme.tokens.accent)
                .padding(.top, 2)
        case .h3(let text):
            Text(text)
                .font(.athenaeum(.sans, size: 12, weight: .semibold))
                .foregroundStyle(theme.tokens.text)
        case .quote(let text):
            Text(attributed(text))
                .font(.athenaeum(.sans, size: 12))
                .italic()
                .foregroundStyle(theme.tokens.muted)
                .padding(.leading, 12)
                .overlay(alignment: .leading) {
                    Rectangle()
                        .fill(theme.tokens.border)
                        .frame(width: 2)
                }
                .textSelection(.enabled)
        case .code(let text):
            Text(text)
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.text)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(theme.tokens.surface2)
                .textSelection(.enabled)
        case .bullet(let items):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("•")
                            .font(.athenaeum(.sans, size: 12))
                            .foregroundStyle(theme.tokens.dim)
                        Text(attributed(item))
                            .font(.athenaeum(.sans, size: 12))
                            .foregroundStyle(theme.tokens.text)
                            .textSelection(.enabled)
                    }
                }
            }
        case .paragraph(let text):
            Text(attributed(text))
                .font(.athenaeum(.sans, size: 12))
                .foregroundStyle(theme.tokens.text)
                .textSelection(.enabled)
                .lineSpacing(4)
        }
    }

    private func attributed(_ raw: String) -> AttributedString {
        if let parsed = try? AttributedString(
            markdown: raw,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        ) {
            return parsed
        }
        return AttributedString(raw)
    }
}
