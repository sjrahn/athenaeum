import SwiftUI
import AthenaeumKit

/// Secondary 360×320 floating window. Triggered by ⇧⌘Y. Content = current
/// selection's normalized / original preview. Phase 3 wires real artifact
/// renderers; Phase 2 renders a mono card with title + meta + first lines of
/// the body.
struct QuickLookWindow: View {
    @Environment(\.theme) private var theme
    @Environment(BrowseStore.self) private var store

    var body: some View {
        VStack(spacing: 0) {
            switch store.selectedDetail {
            case .loaded(let detail): loaded(detail)
            case .loading:
                ProgressView().controlSize(.small).frame(maxWidth: .infinity, maxHeight: .infinity)
            case .idle:
                placeholder("no record selected")
            case .error(let err):
                placeholder(err.localizedDescription)
            }
        }
        .frame(minWidth: 360, idealWidth: 360, minHeight: 320, idealHeight: 320)
        .background(theme.tokens.surface2)
    }

    private func loaded(_ detail: RecordDetail) -> some View {
        let fm = detail.record.frontmatter
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                KindChip(recordType: fm.recordType)
                MimeChip(mime: fm.contentType)
            }
            Text(fm.title.isEmpty ? "(untitled)" : fm.title)
                .font(.athenaeum(.sans, size: 14, weight: .semibold))
                .foregroundStyle(theme.tokens.text)
                .lineLimit(2)
            if !fm.description.isEmpty {
                Text(fm.description)
                    .font(.athenaeum(.sans, size: 12))
                    .foregroundStyle(theme.tokens.muted)
                    .lineLimit(3)
            }
            Hairline()
            ScrollView {
                Text(detail.record.body.isEmpty ? "(empty body)" : detail.record.body)
                    .font(.athenaeum(.mono, size: 11))
                    .foregroundStyle(theme.tokens.text)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(12)
    }

    private func placeholder(_ text: String) -> some View {
        Text(text)
            .font(.athenaeum(.mono, size: 11))
            .foregroundStyle(theme.tokens.dim)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
