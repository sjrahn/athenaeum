import SwiftUI
import AthenaeumKit

/// Secondary floating window triggered by ⇧⌘Y. Renders the current
/// selection's Original (source) or Normalized (document) content at a
/// compact size — it's a glance view, not a full detail window. The user
/// reaches for a proper detail window when they want room to work.
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
        .frame(minWidth: 360, idealWidth: 480, minHeight: 320, idealHeight: 420)
        .background(theme.tokens.bg)
    }

    @ViewBuilder
    private func loaded(_ detail: RecordDetail) -> some View {
        let fm = detail.record.frontmatter
        VStack(spacing: 0) {
            header(fm: fm)
            Hairline()
            switch fm.recordType {
            case .source:
                OriginalView(detail: detail)
            case .document:
                NormalizedView(detail: detail)
            }
        }
    }

    private func header(fm: Frontmatter) -> some View {
        HStack(spacing: 6) {
            KindChip(recordType: fm.recordType)
            MimeChip(mime: fm.contentType)
            Text(fm.title.isEmpty ? "(untitled)" : fm.title)
                .font(.athenaeum(.sans, size: 12, weight: .semibold))
                .foregroundStyle(theme.tokens.text)
                .lineLimit(1)
            Spacer()
        }
        .padding(.horizontal, 12)
        .frame(height: 32)
        .background(theme.tokens.surface)
    }

    private func placeholder(_ text: String) -> some View {
        Text(text)
            .font(.athenaeum(.mono, size: 11))
            .foregroundStyle(theme.tokens.dim)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
