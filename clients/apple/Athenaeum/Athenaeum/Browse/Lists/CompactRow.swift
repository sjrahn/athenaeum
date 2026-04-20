import SwiftUI
import AthenaeumKit

/// Single-row renderer for `ColumnView` and `TableView`. Dense mode shows a
/// KindChip + MimeChip + title only. Comfy / spacious add origin + tags lines.
struct CompactRow: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density

    let record: RecordSummary
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .center, spacing: 6) {
                KindChip(recordType: RecordType(rawValue: record.recordType) ?? .source)
                MimeChip(mime: record.contentType)
                VStack(alignment: .leading, spacing: 1) {
                    Text(record.title.isEmpty ? "(untitled)" : record.title)
                        .font(.athenaeum(.sans, size: density.fs, weight: isSelected ? .semibold : .medium))
                        .foregroundStyle(isSelected ? theme.tokens.accent : theme.tokens.text)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    if density != .dense, !record.tags.isEmpty {
                        Text(record.tags.prefix(4).joined(separator: " · "))
                            .font(.athenaeum(.mono, size: 9))
                            .foregroundStyle(theme.tokens.dim)
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 4)
                if isSelected {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 9))
                        .foregroundStyle(theme.tokens.accent)
                }
            }
            .padding(.horizontal, density.padX)
            .frame(height: density.rowH)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? theme.tokens.accentSoft.opacity(0.5) : .clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
