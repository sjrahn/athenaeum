import SwiftUI
import AthenaeumKit

/// Finder-style column layout. Phase 2 ships a simplified two-column form:
/// facet column (170pt) + record column (320pt, flex-grow). Detail is supplied
/// by the outer `DocPreview` split. Phase 6 polish can expand facets into the
/// full two-column facet cascade (mime → tag) the design specifies.
struct ColumnView: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density
    @Environment(BrowseStore.self) private var store

    var body: some View {
        HStack(spacing: 0) {
            facetColumn
            VHairline()
            recordColumn
        }
    }

    private var facetColumn: some View {
        VStack(alignment: .leading, spacing: 0) {
            columnHeader("facet: mime")
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if let facets = store.facets.value {
                        ForEach(facets.contentTypes.filter { !$0.isEmpty }.sorted(), id: \.self) { mime in
                            facetRow(mime: mime)
                        }
                    } else if store.facets.isLoading {
                        loadingRow
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .frame(width: 170)
        .background(theme.tokens.surface)
    }

    private func facetRow(mime: String) -> some View {
        let selected = store.query.contentType == mime
        return Button {
            if selected { store.clearFilter(.contentType) } else { store.applyFilter(contentType: mime) }
        } label: {
            HStack(spacing: 6) {
                MimeChip(mime: mime)
                Text(mime)
                    .font(.athenaeum(.mono, size: 10, weight: selected ? .semibold : .regular))
                    .foregroundStyle(selected ? theme.tokens.accent : theme.tokens.text)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, density.padX)
            .frame(height: density.rowH)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? theme.tokens.accentSoft.opacity(0.5) : .clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var recordColumn: some View {
        VStack(alignment: .leading, spacing: 0) {
            columnHeader("records")
            recordList
        }
        .background(theme.tokens.bg)
    }

    @ViewBuilder
    private var recordList: some View {
        if let result = store.records.value {
            if result.records.isEmpty {
                emptyState
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(result.records) { record in
                            CompactRow(
                                record: record,
                                isSelected: store.selectedRecordID == record.uuid
                            ) {
                                store.select(record.uuid)
                            }
                        }
                        LoadMoreSentinel()
                    }
                }
            }
        } else if store.records.isLoading {
            ProgressView().controlSize(.small).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            Spacer()
        }
    }

    private func columnHeader(_ text: String) -> some View {
        VStack(spacing: 0) {
            Text(text.uppercased())
                .font(.athenaeum(.mono, size: 9, weight: .semibold))
                .tracking(0.8)
                .foregroundStyle(theme.tokens.dim)
                .padding(.horizontal, density.padX)
                .frame(height: 22, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(theme.tokens.surface2)
            Hairline()
        }
    }

    private var loadingRow: some View {
        Text("loading…")
            .font(.athenaeum(.mono, size: 10))
            .foregroundStyle(theme.tokens.dim)
            .padding(.horizontal, density.padX)
            .frame(height: density.rowH, alignment: .leading)
    }

    private var emptyState: some View {
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
