import SwiftUI
import AthenaeumKit

/// Two-row top chrome matching `MacToolbar2` in the design.
/// Row 1 (34pt): back/forward, corpus pill + record count, search (300pt), `+ submit`.
/// Row 2 (30pt): kind segmented, vertical hairline, active filter chips, `+ filter`, view switcher.
struct MacToolbar: View {
    @Environment(\.theme) private var theme
    @Environment(BrowseStore.self) private var store

    @FocusState private var searchFocused: Bool
    @State private var searchDraft: String = ""

    var body: some View {
        VStack(spacing: 0) {
            row1
            Hairline()
            row2
        }
        .background(theme.tokens.surface)
    }

    // MARK: - Row 1

    private var row1: some View {
        HStack(spacing: 8) {
            navButtons
            Spacer().frame(width: 4)
            corpusPillArea
            Spacer(minLength: 8)
            searchField
            submitButton
        }
        .padding(.horizontal, 10)
        .frame(height: 34)
    }

    private var navButtons: some View {
        HStack(spacing: 2) {
            Btn(.ghost, action: { store.goBack() }) { Text("‹") }
                .disabled(!store.canGoBack)
            Btn(.ghost, action: { store.goForward() }) { Text("›") }
                .disabled(!store.canGoForward)
        }
    }

    private var corpusPillArea: some View {
        HStack(spacing: 6) {
            Text("corpus")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
            PillAccent(store.selectedCorpus.replacingOccurrences(of: "corpus-", with: ""))
            if let total = store.records.value?.total {
                Text("\(total) records")
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.muted)
            }
        }
    }

    private var searchField: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(theme.tokens.dim)
            TextField("search…", text: $searchDraft)
                .textFieldStyle(.plain)
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.text)
                .focused($searchFocused)
                .onSubmit { store.applySearch(searchDraft) }
            if !searchDraft.isEmpty {
                Button {
                    searchDraft = ""
                    store.applySearch("")
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 10))
                        .foregroundStyle(theme.tokens.dim)
                }
                .buttonStyle(.plain)
            }
            Kbd("⌘F")
        }
        .padding(.horizontal, 8)
        .frame(width: 300, height: 22)
        .background(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(theme.tokens.surface2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .strokeBorder(searchFocused ? theme.tokens.accent : theme.tokens.border, lineWidth: 1)
        )
        .onAppear { searchDraft = store.query.q }
    }

    private var submitButton: some View {
        Btn("+ submit", variant: .primary) {
            OpenSubmitWindow.open()
        }
    }

    // MARK: - Row 2

    private var row2: some View {
        HStack(spacing: 10) {
            kindSegmented
            VHairline().frame(height: 16)
            filterChipRow
            Spacer(minLength: 8)
            Btn(.ghost, action: {}) { Text("+ filter") }
                .disabled(true)
            VHairline().frame(height: 16)
            viewSwitcher
        }
        .padding(.horizontal, 10)
        .frame(height: 30)
    }

    private var kindSegmented: some View {
        HStack(spacing: 0) {
            ForEach(KindFilter.allCases, id: \.self) { kind in
                let selected = store.kindFilter == kind
                Button {
                    store.applyKind(kind)
                } label: {
                    Text(kind.label)
                        .font(.athenaeum(.mono, size: 10, weight: selected ? .semibold : .medium))
                        .foregroundStyle(selected ? theme.tokens.accent : theme.tokens.muted)
                        .padding(.horizontal, 8)
                        .frame(height: 20)
                        .background(selected ? theme.tokens.accentSoft : .clear)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(theme.tokens.surface2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .strokeBorder(theme.tokens.border, lineWidth: 1)
        )
    }

    private var filterChipRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(Array(store.activeFilters.enumerated()), id: \.offset) { _, entry in
                    filterChip(kind: entry.0, label: entry.1)
                }
            }
        }
        .frame(maxWidth: 320)
    }

    private func filterChip(kind: BrowseStore.FilterKind, label: String) -> some View {
        Button {
            store.clearFilter(kind)
        } label: {
            HStack(spacing: 4) {
                Text(label)
                    .font(.athenaeum(.mono, size: 10, weight: .medium))
                    .foregroundStyle(theme.tokens.accent)
                Text("×")
                    .font(.athenaeum(.mono, size: 10, weight: .bold))
                    .foregroundStyle(theme.tokens.accent)
            }
            .padding(.horizontal, 6)
            .frame(height: 18)
            .background(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(theme.tokens.accentSoft)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var viewSwitcher: some View {
        HStack(spacing: 0) {
            ForEach(ListVariant.allCases, id: \.self) { variant in
                let selected = store.listVariant == variant
                Button {
                    store.listVariant = variant
                } label: {
                    Text(variant.label)
                        .font(.athenaeum(.mono, size: 10, weight: selected ? .semibold : .regular))
                        .foregroundStyle(selected ? theme.tokens.accent : theme.tokens.muted)
                        .padding(.horizontal, 8)
                        .frame(height: 20)
                        .background(selected ? theme.tokens.accentSoft : .clear)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(theme.tokens.surface2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .strokeBorder(theme.tokens.border, lineWidth: 1)
        )
    }
}

/// Cross-window helper to open the Submit window from wherever the toolbar
/// lives. Wired up in `AthenaeumApp` via `openWindow`.
enum OpenSubmitWindow {
    @MainActor static var handler: () -> Void = {}
    @MainActor static func open() { handler() }
}
