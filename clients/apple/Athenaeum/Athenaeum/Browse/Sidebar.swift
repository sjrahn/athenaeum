import SwiftUI
import AthenaeumKit

/// 200pt wide, `surface2` bg. Groups in order:
/// corpus (public/private counts) / kind (all/src/doc) / views (placeholders) /
/// primary mime facet / submissions (queue count). Sticky footer showing
/// `● api · /v1/{corpus}` in mono 10pt.
struct Sidebar: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density
    @Environment(BrowseStore.self) private var store

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    corpusGroup
                    Hairline()
                    kindGroup
                    Hairline()
                    viewsGroup
                    Hairline()
                    mimeGroup
                    Hairline()
                    submissionsGroup
                }
                .padding(.vertical, 10)
            }
            Hairline()
            footer
        }
        .frame(width: 200)
        .background(theme.tokens.surface2)
    }

    // MARK: - Groups

    private var corpusGroup: some View {
        groupBox(title: "corpus") {
            if let list = store.corpora.value {
                ForEach(list) { info in
                    sidebarRow(
                        label: info.name.replacingOccurrences(of: "corpus-", with: ""),
                        count: info.recordCount,
                        isSelected: info.name == store.selectedCorpus
                    ) {
                        store.switchCorpus(info.name)
                    }
                }
            } else if store.corpora.isLoading {
                loadingRow
            }
        }
    }

    private var kindGroup: some View {
        groupBox(title: "kind") {
            ForEach(KindFilter.allCases, id: \.self) { kind in
                sidebarRow(
                    label: kind.label,
                    count: nil,
                    isSelected: store.kindFilter == kind
                ) {
                    store.applyKind(kind)
                }
            }
        }
    }

    private var viewsGroup: some View {
        groupBox(title: "views") {
            ForEach(["recents", "pinned", "untagged", "orphans"], id: \.self) { name in
                sidebarRow(label: name, count: nil, isSelected: false) { }
                    .disabled(true)
                    .opacity(0.5)
            }
        }
    }

    private var mimeGroup: some View {
        groupBox(title: "primary mime") {
            if let facets = store.facets.value {
                let counts = mimeCounts(from: facets)
                if counts.isEmpty {
                    emptyRow("no mime facets")
                }
                ForEach(counts, id: \.mime) { entry in
                    mimeRow(
                        mime: entry.mime,
                        count: entry.count,
                        isSelected: store.query.contentType == entry.mime
                    )
                }
            } else if store.facets.isLoading {
                loadingRow
            }
        }
    }

    private var submissionsGroup: some View {
        groupBox(title: "submissions") {
            if let subs = store.submissions.value {
                sidebarRow(
                    label: "queue",
                    count: UInt64(subs.submissions.count),
                    isSelected: false
                ) { }
                sidebarRow(label: "history", count: nil, isSelected: false) { }
                    .disabled(true)
                    .opacity(0.5)
            } else if store.submissions.isLoading {
                loadingRow
            }
        }
    }

    private var footer: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(store.health.isOK ? theme.tokens.ok : theme.tokens.err)
                .frame(width: 6, height: 6)
            Text("api · /v1/\(store.selectedCorpus)")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.muted)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .padding(.horizontal, density.padX)
        .frame(maxWidth: .infinity, alignment: .leading)
        .frame(height: 24)
        .background(theme.tokens.surface2)
    }

    // MARK: - Building blocks

    private func groupBox<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title.uppercased())
                .font(.athenaeum(.mono, size: 9, weight: .semibold))
                .tracking(0.8)
                .foregroundStyle(theme.tokens.dim)
                .padding(.horizontal, density.padX)
                .padding(.bottom, 2)
            content()
        }
    }

    private func sidebarRow(
        label: String,
        count: UInt64?,
        isSelected: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(label)
                    .font(.athenaeum(.mono, size: 11, weight: isSelected ? .semibold : .regular))
                    .foregroundStyle(isSelected ? theme.tokens.accent : theme.tokens.text)
                Spacer(minLength: 4)
                if let count {
                    Text(String(count))
                        .font(.athenaeum(.mono, size: 10))
                        .foregroundStyle(theme.tokens.muted)
                }
            }
            .padding(.horizontal, density.padX)
            .frame(height: density.rowH)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? theme.tokens.accentSoft.opacity(0.4) : .clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func mimeRow(mime: String, count: UInt64, isSelected: Bool) -> some View {
        Button {
            if isSelected {
                store.clearFilter(.contentType)
            } else {
                store.applyFilter(contentType: mime)
            }
        } label: {
            HStack(spacing: 6) {
                MimeChip(mime: mime)
                Text(mime)
                    .font(.athenaeum(.mono, size: 10, weight: isSelected ? .semibold : .regular))
                    .foregroundStyle(isSelected ? theme.tokens.accent : theme.tokens.text)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, density.padX)
            .frame(height: density.rowH)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? theme.tokens.accentSoft.opacity(0.4) : .clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var loadingRow: some View {
        Text("loading…")
            .font(.athenaeum(.mono, size: 10))
            .foregroundStyle(theme.tokens.dim)
            .padding(.horizontal, density.padX)
            .frame(height: density.rowH, alignment: .leading)
    }

    private func emptyRow(_ text: String) -> some View {
        Text(text)
            .font(.athenaeum(.mono, size: 10))
            .foregroundStyle(theme.tokens.dim)
            .padding(.horizontal, density.padX)
            .frame(height: density.rowH, alignment: .leading)
    }

    // MARK: - Helpers

    private struct MimeCount { let mime: String; let count: UInt64 }

    /// Facets endpoint returns distinct content_type values without counts.
    /// For phase 2 we show the mime name with a neutral "—" count. When the
    /// server adds counts we'll switch to the real number.
    private func mimeCounts(from facets: FacetsResponse) -> [MimeCount] {
        facets.contentTypes
            .filter { !$0.isEmpty }
            .sorted()
            .map { MimeCount(mime: $0, count: 0) }
    }
}
