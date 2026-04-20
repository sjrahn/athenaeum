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
            HStack(alignment: .top, spacing: 8) {
                Rectangle()
                    .fill(selected ? theme.tokens.accent : Color.clear)
                    .frame(width: 3)
                VStack(alignment: .leading, spacing: 6) {
                    // Row 1: chips + uuid fragment (right-aligned)
                    HStack(spacing: 6) {
                        KindChip(recordType: RecordType(rawValue: record.recordType) ?? .source)
                        MimeChip(mime: record.contentType)
                        Text(record.status.lowercased())
                            .font(.athenaeum(.mono, size: 10))
                            .foregroundStyle(theme.tokens.muted)
                        Spacer(minLength: 4)
                        Text(record.uuid.uuidString.prefix(8))
                            .font(.athenaeum(.mono, size: 9))
                            .foregroundStyle(theme.tokens.dim)
                    }
                    // Row 2: title (up to 2 lines so long titles don't get
                    // clipped in the narrow card pane)
                    Text(record.title.isEmpty ? "(untitled)" : record.title)
                        .font(.athenaeum(.sans, size: 13, weight: .semibold))
                        .foregroundStyle(selected ? theme.tokens.accent : theme.tokens.text)
                        .lineLimit(2)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    // Row 3: tag list + visibility pill (when non-visible)
                    if !record.tags.isEmpty || (record.visibility != nil && record.visibility != "visible") {
                        HStack(spacing: 6) {
                            if !record.tags.isEmpty {
                                Text(record.tags.prefix(6).map { "#\($0)" }.joined(separator: "  "))
                                    .font(.athenaeum(.mono, size: 10))
                                    .foregroundStyle(theme.tokens.muted)
                                    .lineLimit(1)
                            }
                            Spacer(minLength: 0)
                            if let v = record.visibility, v != "visible" {
                                Text(v.uppercased())
                                    .font(.athenaeum(.mono, size: 9, weight: .semibold))
                                    .tracking(0.6)
                                    .foregroundStyle(theme.tokens.warn)
                                    .padding(.horizontal, 4)
                                    .frame(height: 14)
                                    .background(
                                        RoundedRectangle(cornerRadius: 2, style: .continuous)
                                            .strokeBorder(theme.tokens.warn, lineWidth: 1)
                                    )
                            }
                        }
                    }
                }
                .padding(.vertical, 10)
                .padding(.trailing, 12)
                Spacer(minLength: 0)
            }
            .frame(minHeight: 72)
            .background(selected ? theme.tokens.accentSoft.opacity(0.3) : theme.tokens.surface)
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(selected ? theme.tokens.accent : theme.tokens.border, lineWidth: 1)
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
