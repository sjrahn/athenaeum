import SwiftUI
import AthenaeumKit

/// Email (message/rfc822) renderer. Downloads the raw EML text, parses out
/// the basic headers (From / To / Subject / Date), then renders the body
/// below a hairline in IBM Plex Sans. Only the plaintext part is shown; the
/// rare MIME-multipart capture falls back to the raw text.
struct EmailRender: View {
    @Environment(\.theme) private var theme
    let artifact: ArtifactRef
    let url: URL

    @State private var loader = TextArtifactLoader()

    var body: some View {
        VStack(spacing: 0) {
            content
            RendererFooter(
                filename: ArtifactRefHelpers.filename(from: artifact.ref),
                detail: artifact.mimetype ?? "message/rfc822",
                fileURL: url
            )
        }
        .task(id: url) {
            await loader.load(url)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch loader.state {
        case .idle, .loading:
            RendererLoadingView()
        case .failed(let msg):
            RendererErrorView(message: msg)
        case .loaded(let text):
            email(text)
        }
    }

    private func email(_ text: String) -> some View {
        let parsed = EmailParser.parse(text)
        return ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                headers(parsed)
                Hairline()
                Text(parsed.body.isEmpty ? "(no body)" : parsed.body)
                    .font(.athenaeum(.sans, size: 12))
                    .foregroundStyle(theme.tokens.text)
                    .textSelection(.enabled)
                    .lineSpacing(4)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(20)
            .frame(maxWidth: 720, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(theme.tokens.surface)
    }

    private func headers(_ parsed: ParsedEmail) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let from = parsed.from { row("From", from) }
            if let to = parsed.to { row("To", to) }
            if let subject = parsed.subject { row("Subject", subject) }
            if let date = parsed.date { row("Date", date) }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label)
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.dim)
                .frame(width: 72, alignment: .leading)
            Text(value)
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.text)
                .textSelection(.enabled)
        }
    }
}

private struct ParsedEmail {
    let from: String?
    let to: String?
    let subject: String?
    let date: String?
    let body: String
}

private enum EmailParser {
    /// Hand-rolled MIME header / body separator — good enough for the EML
    /// captures we ship (single-part text/plain). Splits on the first blank
    /// line, then picks out a few headers by name. Anything beyond that
    /// (nested multipart, attachments, quoted-printable decoding) falls
    /// through to the raw body on purpose.
    static func parse(_ text: String) -> ParsedEmail {
        // Normalise CRLF → LF so the blank-line split is reliable.
        let normalised = text.replacingOccurrences(of: "\r\n", with: "\n")
        let parts = normalised.components(separatedBy: "\n\n")
        let (rawHeaders, body): (String, String)
        if parts.count >= 2 {
            rawHeaders = parts[0]
            body = parts.dropFirst().joined(separator: "\n\n")
        } else {
            rawHeaders = ""
            body = normalised
        }

        // Unfold continuation lines: a leading space or tab means the line
        // continues the previous header.
        var headers: [(String, String)] = []
        for line in rawHeaders.split(separator: "\n", omittingEmptySubsequences: false) {
            let s = String(line)
            if let first = s.first, first == " " || first == "\t" {
                if var last = headers.last {
                    let cont = s.trimmingCharacters(in: .whitespaces)
                    last.1.append(" ")
                    last.1.append(cont)
                    headers[headers.count - 1] = last
                }
            } else if let colon = s.firstIndex(of: ":") {
                let name = String(s[..<colon]).trimmingCharacters(in: .whitespaces)
                let value = String(s[s.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
                headers.append((name, value))
            }
        }

        func lookup(_ key: String) -> String? {
            headers.first { $0.0.caseInsensitiveCompare(key) == .orderedSame }?.1
        }

        return ParsedEmail(
            from: lookup("From"),
            to: lookup("To"),
            subject: lookup("Subject"),
            date: lookup("Date"),
            body: body.trimmingCharacters(in: .whitespacesAndNewlines)
        )
    }
}
