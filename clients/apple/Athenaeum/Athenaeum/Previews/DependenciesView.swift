import SwiftUI
import AthenaeumKit

/// `dependencies` tab (document records only). Top section lists the record's
/// constituents as tappable rows (open child in new window). Reverse section
/// shows the count of records using this one (from `RecordDetail.parents`).
struct DependenciesView: View {
    @Environment(\.theme) private var theme
    @Environment(\.openWindow) private var openWindow
    let detail: RecordDetail

    var body: some View {
        let constituents = detail.record.frontmatter.constituents ?? []
        return ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("\(constituents.count) constituents")
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)

                if detail.children.isEmpty && constituents.isEmpty {
                    Text("(no dependencies)")
                        .font(.athenaeum(.mono, size: 11))
                        .foregroundStyle(theme.tokens.dim)
                } else {
                    VStack(spacing: 6) {
                        ForEach(detail.children) { row(child: $0) }
                    }
                }

                if !detail.parents.isEmpty {
                    Text("reverse — records using this")
                        .font(.athenaeum(.mono, size: 10))
                        .foregroundStyle(theme.tokens.dim)
                        .padding(.top, 16)
                    VStack(spacing: 6) {
                        ForEach(detail.parents) { row(child: $0) }
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(theme.tokens.bg)
    }

    private func row(child: RecordSummary) -> some View {
        Button {
            openWindow(id: "detail", value: child.uuid)
        } label: {
            HStack(spacing: 10) {
                KindChip(recordType: RecordType(rawValue: child.recordType) ?? .source)
                MimeChip(mime: child.contentType)
                Text(child.title.isEmpty ? "(untitled)" : child.title)
                    .font(.athenaeum(.sans, size: 12, weight: .medium))
                    .foregroundStyle(theme.tokens.text)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text(child.uuid.uuidString.prefix(8))
                    .font(.athenaeum(.mono, size: 9))
                    .foregroundStyle(theme.tokens.dim)
                Image(systemName: "arrow.up.forward")
                    .font(.system(size: 9))
                    .foregroundStyle(theme.tokens.dim)
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .background(theme.tokens.surface)
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(theme.tokens.border, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
