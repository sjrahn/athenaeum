import SwiftUI
import AthenaeumKit

/// Vertical feed of 80-96pt cards. Accent left border on selection. Left side:
/// compact thumb (placeholder Phase 3). Right side: title + meta row + tags.
struct CardFeed: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density
    @Environment(BrowseStore.self) private var store

    var body: some View {
        ZStack {
            theme.tokens.bg.ignoresSafeArea()
            content
        }
    }

    @ViewBuilder
    private var content: some View {
        if let result = store.records.value {
            if result.records.isEmpty {
                empty
            } else {
                ScrollView {
                    LazyVStack(spacing: 6) {
                        ForEach(result.records) { card(for: $0) }
                    }
                    .padding(10)
                }
            }
        } else if store.records.isLoading {
            ProgressView().controlSize(.small)
        }
    }

    private func card(for record: RecordSummary) -> some View {
        let selected = store.selectedRecordID == record.uuid
        return Button {
            store.select(record.uuid)
        } label: {
            HStack(spacing: 8) {
                Rectangle()
                    .fill(selected ? theme.tokens.accent : Color.clear)
                    .frame(width: 3)
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 4) {
                        KindChip(recordType: RecordType(rawValue: record.recordType) ?? .source)
                        MimeChip(mime: record.contentType)
                        Text(record.status.uppercased())
                            .font(.athenaeum(.mono, size: 9, weight: .semibold))
                            .tracking(0.4)
                            .foregroundStyle(theme.tokens.dim)
                        Spacer(minLength: 0)
                    }
                    Text(record.title.isEmpty ? "(untitled)" : record.title)
                        .font(.athenaeum(.sans, size: 13, weight: .semibold))
                        .foregroundStyle(theme.tokens.text)
                        .lineLimit(1)
                    if !record.tags.isEmpty {
                        Text(record.tags.prefix(6).joined(separator: " · "))
                            .font(.athenaeum(.mono, size: 10))
                            .foregroundStyle(theme.tokens.muted)
                            .lineLimit(1)
                    }
                }
                .padding(.vertical, 8)
                .padding(.trailing, 10)
                Spacer(minLength: 0)
            }
            .frame(minHeight: 80)
            .background(theme.tokens.surface)
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(theme.tokens.border, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var empty: some View {
        Text("no records match the current filters")
            .font(.athenaeum(.mono, size: 11))
            .foregroundStyle(theme.tokens.muted)
    }
}
