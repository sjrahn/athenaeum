import SwiftUI
import AthenaeumKit

/// Standalone detail window opened by `openWindow(id: "detail", value: uuid)`.
/// Owns its own `APIClient` fetch for the given UUID and renders the full
/// `DocPreview`-style tabbed layout. Survives independently of the main
/// browse window so the user can keep multiple records open side by side.
struct DetailWindow: View {
    @Environment(\.theme) private var theme
    @Environment(PreferencesStore.self) private var preferences
    let uuid: UUID

    @State private var detail: LoadState<RecordDetail> = .idle
    @State private var selectedTab: DetailTab = .original

    var body: some View {
        VStack(spacing: 0) {
            switch detail {
            case .loaded(let d):
                loaded(d)
            case .loading:
                ProgressView().controlSize(.small).frame(maxWidth: .infinity, maxHeight: .infinity)
            case .idle:
                Color.clear.onAppear { load() }
            case .error(let err):
                errorView(err)
            }
        }
        .frame(minWidth: 560, minHeight: 480)
        .background(theme.tokens.bg)
        .task(id: uuid) { load() }
    }

    private func load() {
        detail = .loading
        Task {
            do {
                let client = APIClient(baseURL: preferences.serverURL)
                let result = try await client.record(uuid: uuid)
                detail = .loaded(result)
            } catch let error as APIError {
                detail = .error(error)
            } catch {
                detail = .error(.invalidResponse(String(describing: error)))
            }
        }
    }

    @ViewBuilder
    private func loaded(_ d: RecordDetail) -> some View {
        let fm = d.record.frontmatter
        let tabs = availableTabs(for: fm.recordType)
        let active = tabs.contains(selectedTab) ? selectedTab : tabs.first ?? .metadata

        VStack(spacing: 0) {
            HStack(spacing: 8) {
                KindChip(recordType: fm.recordType)
                MimeChip(mime: fm.contentType)
                Text(fm.title.isEmpty ? "(untitled)" : fm.title)
                    .font(.athenaeum(.sans, size: 14, weight: .semibold))
                    .foregroundStyle(theme.tokens.text)
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(theme.tokens.surface)
            Hairline()
            tabBar(tabs: tabs, active: active)
            Hairline()
            content(detail: d, tab: active)
        }
    }

    private func availableTabs(for type: RecordType) -> [DetailTab] {
        switch type {
        case .source: [.original, .normalized, .artifacts, .metadata]
        case .document: [.normalized, .dependencies, .metadata]
        }
    }

    private func tabBar(tabs: [DetailTab], active: DetailTab) -> some View {
        HStack(spacing: 0) {
            ForEach(tabs, id: \.self) { tab in
                Button { selectedTab = tab } label: {
                    Text(tab.label)
                        .font(.athenaeum(.mono, size: 10, weight: tab == active ? .semibold : .regular))
                        .foregroundStyle(tab == active ? theme.tokens.accent : theme.tokens.muted)
                        .padding(.horizontal, 10)
                        .frame(height: 28)
                        .overlay(alignment: .bottom) {
                            Rectangle()
                                .fill(tab == active ? theme.tokens.accent : Color.clear)
                                .frame(height: 2)
                        }
                }
                .buttonStyle(.plain)
                .contentShape(Rectangle())
            }
            Spacer()
        }
        .padding(.horizontal, 8)
        .frame(height: 28)
        .background(theme.tokens.surface2)
    }

    @ViewBuilder
    private func content(detail: RecordDetail, tab: DetailTab) -> some View {
        // Phase 2 shares the same stubs as the embedded DocPreview by
        // re-using its pane factory indirectly: we render a minimal mirror
        // here to avoid importing private internals.
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("tab: \(tab.label)")
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)
                Text(detail.record.body.isEmpty ? "(empty body)" : detail.record.body)
                    .font(.athenaeum(.sans, size: 13))
                    .foregroundStyle(theme.tokens.text)
                    .textSelection(.enabled)
            }
            .padding(16)
        }
    }

    private func errorView(_ err: APIError) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(theme.tokens.err)
            Text(err.localizedDescription)
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.muted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
