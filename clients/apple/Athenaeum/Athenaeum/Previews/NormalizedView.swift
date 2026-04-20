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
        // First, lift out any Obsidian-style `%%…%%` comment blocks so they
        // render as distinct "legacy note" cards rather than mixing in with
        // the real content. Supports both block (delimiters on their own
        // lines) and inline (`%% … %%` within a paragraph) forms; inline
        // ones collapse to a small muted marker.
        let (stripped, comments) = extractComments(text)

        var out: [MarkdownBlock] = []
        var buffer: [String] = []
        func flush() {
            guard !buffer.isEmpty else { return }
            let joined = buffer.joined(separator: "\n")
            out.append(MarkdownBlock.from(joined))
            buffer.removeAll(keepingCapacity: true)
        }
        for raw in stripped.split(separator: "\n", omittingEmptySubsequences: false) {
            let line = String(raw)
            if line.hasPrefix("\u{FEFF}COMMENT:") {
                flush()
                let idx = Int(line.dropFirst("\u{FEFF}COMMENT:".count)) ?? 0
                if idx < comments.count {
                    out.append(.comment(comments[idx]))
                }
            } else if line.trimmingCharacters(in: .whitespaces).isEmpty {
                flush()
            } else {
                buffer.append(line)
            }
        }
        flush()
        return out
    }

    /// Parse `%%…%%` Obsidian comment blocks out of the body and replace each
    /// with a `\u{FEFF}COMMENT:<idx>` marker line. Returns the rewritten body
    /// and the extracted comment bodies in order. Robust to:
    /// - Block form: delimiters on their own lines, possibly multi-line body.
    /// - Inline form: `%%…%%` entirely within a paragraph (replaced by the
    ///   same marker, rendered as a small chip).
    private func extractComments(_ text: String) -> (String, [String]) {
        var comments: [String] = []
        var result = text
        // Greedy multi-line regex — Swift `Regex` with `(?s)` dotall.
        guard let regex = try? NSRegularExpression(
            pattern: "%%([\\s\\S]*?)%%",
            options: []
        ) else {
            return (text, [])
        }
        var work = text as NSString
        var matches = regex.matches(in: result, range: NSRange(location: 0, length: work.length))
        while let match = matches.first {
            let bodyRange = match.range(at: 1)
            let body = work.substring(with: bodyRange)
            comments.append(body.trimmingCharacters(in: .whitespacesAndNewlines))
            let full = work.substring(with: match.range)
            let marker = "\n\u{FEFF}COMMENT:\(comments.count - 1)\n"
            // Replace the first occurrence manually so we don't recompute the
            // whole string at each step.
            if let range = result.range(of: full) {
                result.replaceSubrange(range, with: marker)
            }
            work = result as NSString
            matches = regex.matches(
                in: result, range: NSRange(location: 0, length: work.length)
            )
        }
        return (result, comments)
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
    /// Obsidian-style `%%…%%` comment block — content that the author
    /// flagged as editorial scaffolding rather than real normalized body.
    /// Rendered collapsed by default with a header chip; user can click
    /// to expand.
    case comment(String)

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
        case .comment(let body):
            CommentBlockView(body: body)
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

/// Collapsed Obsidian-style comment card. Header chip announces it's a
/// legacy note and indicates expand state; body renders in dim mono so the
/// eye never confuses it with real content. Short comments (< 120 chars)
/// start expanded; longer ones stay collapsed until the user clicks.
private struct CommentBlockView: View {
    @Environment(\.theme) private var theme
    let body_: String

    @State private var expanded: Bool

    init(body: String) {
        self.body_ = body
        _expanded = State(initialValue: body.count < 120)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            header
            if expanded {
                Text(body_)
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.tokens.surface2)
        .overlay(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .strokeBorder(theme.tokens.border, lineWidth: 1)
        )
    }

    private var header: some View {
        Button {
            expanded.toggle()
        } label: {
            HStack(spacing: 6) {
                Image(systemName: expanded ? "chevron.down" : "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(theme.tokens.dim)
                Text("editorial note")
                    .font(.athenaeum(.mono, size: 9, weight: .semibold))
                    .tracking(0.8)
                    .foregroundStyle(theme.tokens.dim)
                Text("%%…%%")
                    .font(.athenaeum(.mono, size: 9))
                    .foregroundStyle(theme.tokens.dim.opacity(0.7))
                Spacer(minLength: 0)
                if !expanded {
                    Text(firstLine)
                        .font(.athenaeum(.mono, size: 9))
                        .foregroundStyle(theme.tokens.muted)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var firstLine: String {
        body_.split(separator: "\n", omittingEmptySubsequences: true).first.map(String.init) ?? ""
    }
}
