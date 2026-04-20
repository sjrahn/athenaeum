import SwiftUI
import AthenaeumKit

/// 22pt, bottom, `surface2` bg, 1pt top border, mono 10pt muted. Fields:
/// `● api` health dot, current path, record count + breakdown, active filter
/// count, queue running count, last sync time.
struct StatusBar: View {
    @Environment(\.theme) private var theme
    @Environment(BrowseStore.self) private var store

    var body: some View {
        HStack(spacing: 12) {
            healthDot
            Text("/v1/\(store.selectedCorpus)/records")
                .foregroundStyle(theme.tokens.muted)
            recordCountSegment
            filterSegment
            queueSegment
            Spacer(minLength: 0)
            syncSegment
        }
        .font(.athenaeum(.mono, size: 10))
        .padding(.horizontal, 10)
        .frame(height: 22)
        .frame(maxWidth: .infinity)
        .background(theme.tokens.surface2)
        .overlay(alignment: .top) { Hairline() }
    }

    private var healthDot: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(dotColor)
                .frame(width: 6, height: 6)
            Text("api")
                .foregroundStyle(theme.tokens.muted)
        }
    }

    private var dotColor: Color {
        switch store.health {
        case .ok: theme.tokens.ok
        case .down: theme.tokens.err
        case .unknown: theme.tokens.dim
        }
    }

    @ViewBuilder
    private var recordCountSegment: some View {
        if let total = store.records.value?.total {
            Text("· \(total) records")
                .foregroundStyle(theme.tokens.muted)
        }
    }

    @ViewBuilder
    private var filterSegment: some View {
        if !store.activeFilters.isEmpty {
            Text("· \(store.activeFilters.count) filters active")
                .foregroundStyle(theme.tokens.muted)
        }
    }

    @ViewBuilder
    private var queueSegment: some View {
        if let queue = store.submissions.value {
            Text("· queue: \(queue.submissions.count)")
                .foregroundStyle(theme.tokens.muted)
        }
    }

    @ViewBuilder
    private var syncSegment: some View {
        if let last = store.lastSync {
            Text("last sync \(Self.formatter.string(from: last))")
                .foregroundStyle(theme.tokens.dim)
        }
    }

    static let formatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()
}
