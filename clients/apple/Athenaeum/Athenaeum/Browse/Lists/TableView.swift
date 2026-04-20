import SwiftUI
import AthenaeumKit

/// Full-width records table. Shows the four columns we can cheaply populate
/// from `RecordSummary`: kind / mime / title / tags.
///
/// The design calls for origin / artfcts / size / normalized too, but those
/// need detail-level data the summary endpoint doesn't include yet. Rather
/// than render four always-blank `—` columns (user feedback: "I have to pull
/// the preview panel smaller to see the first columns"), we drop them until
/// the server grows a fatter summary shape or a bulk-detail endpoint.
struct RecordsTableView: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density
    @Environment(BrowseStore.self) private var store

    var body: some View {
        VStack(spacing: 0) {
            header
            Hairline()
            body_
        }
        .background(theme.tokens.bg)
    }

    private var header: some View {
        HStack(spacing: 0) {
            cell("kind", width: 46)
            cell("mime", width: 60)
            cell("title", width: nil)
            cell("tags", width: 220)
        }
        .frame(height: 24)
        .background(theme.tokens.surface2)
    }

    private func cell(
        _ text: String,
        width: CGFloat?,
        mono: Bool = false,
        align: Alignment = .leading
    ) -> some View {
        Text(text.uppercased())
            .font(.athenaeum(.mono, size: 9, weight: .semibold))
            .tracking(0.8)
            .foregroundStyle(theme.tokens.dim)
            .padding(.horizontal, 8)
            .frame(width: width, alignment: align)
            .frame(maxWidth: width == nil ? .infinity : width, alignment: align)
    }

    @ViewBuilder
    private var body_: some View {
        if let result = store.records.value {
            if result.records.isEmpty {
                empty
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(result.records) { row(record: $0) }
                    }
                }
            }
        } else if store.records.isLoading {
            ProgressView().controlSize(.small).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            Spacer()
        }
    }

    private func row(record: RecordSummary) -> some View {
        let selected = store.selectedRecordID == record.uuid
        return Button {
            store.select(record.uuid)
        } label: {
            HStack(spacing: 0) {
                HStack { KindChip(recordType: RecordType(rawValue: record.recordType) ?? .source) }
                    .frame(width: 46, alignment: .leading)
                    .padding(.horizontal, 8)
                HStack { MimeChip(mime: record.contentType) }
                    .frame(width: 60, alignment: .leading)
                    .padding(.horizontal, 8)
                Text(record.title.isEmpty ? "(untitled)" : record.title)
                    .font(.athenaeum(.sans, size: density.fs, weight: selected ? .semibold : .regular))
                    .foregroundStyle(selected ? theme.tokens.accent : theme.tokens.text)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(record.tags.prefix(4).joined(separator: ", "))
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.muted)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(width: 220, alignment: .leading)
                    .padding(.horizontal, 8)
            }
            .frame(height: density.rowH + 2)
            .background(selected ? theme.tokens.accentSoft.opacity(0.5) : .clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var empty: some View {
        VStack {
            Spacer()
            Text("no records match the current filters")
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.muted)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }
}
