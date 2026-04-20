import SwiftUI
import AthenaeumKit

/// Lazy-list tail view that triggers `BrowseStore.loadMore()` when it scrolls
/// into view. Rendering only when more data is available keeps the list
/// short-circuited at the true end.
///
/// Drop into the bottom of any `LazyVStack` / `LazyVGrid` inside the list
/// variants; each view still owns its own ScrollView so the trigger fires
/// whenever the user nears the bottom.
struct LoadMoreSentinel: View {
    @Environment(\.theme) private var theme
    @Environment(BrowseStore.self) private var store

    var body: some View {
        if store.hasMoreRecords {
            HStack(spacing: 6) {
                ProgressView().controlSize(.small)
                Text("loading more…")
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 36)
            .onAppear { store.loadMore() }
        }
    }
}
