import SwiftUI
import AthenaeumKit

/// Tabbed detail shell. For source records: `original | normalized |
/// artifacts | metadata`. For document records: `normalized | dependencies |
/// metadata`. Phase 2 ships the tab bar + metadata/artifacts/dependencies
/// tabs; Original + Normalized panes are stubs that Phase 3 fills in.
struct DocPreview: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density
    @Environment(BrowseStore.self) private var store
    @Environment(\.openWindow) private var openWindow

    @State private var selectedTab: DetailTab = .original

    var body: some View {
        VStack(spacing: 0) {
            switch store.selectedDetail {
            case .idle:
                placeholder("select a record to preview")
            case .loading:
                loading
            case .loaded(let detail):
                loaded(detail)
            case .error(let err):
                errorView(err)
            }
        }
        .background(theme.tokens.bg)
    }

    @ViewBuilder
    private func loaded(_ detail: RecordDetail) -> some View {
        let tabs = availableTabs(for: detail.record.frontmatter.recordType)
        let active = tabs.contains(selectedTab) ? selectedTab : tabs.first ?? .metadata

        VStack(spacing: 0) {
            header(detail: detail)
            Hairline()
            tabBar(tabs: tabs, active: active)
            Hairline()
            tabContent(detail: detail, tab: active)
        }
        .onChange(of: detail.record.frontmatter.uuid) { _, _ in
            if !tabs.contains(selectedTab) { selectedTab = tabs.first ?? .metadata }
        }
    }

    // MARK: - Header

    private func header(detail: RecordDetail) -> some View {
        let fm = detail.record.frontmatter
        return HStack(alignment: .center, spacing: 8) {
            KindChip(recordType: fm.recordType)
            MimeChip(mime: fm.contentType)
            VStack(alignment: .leading, spacing: 2) {
                Text(fm.title.isEmpty ? "(untitled)" : fm.title)
                    .font(.athenaeum(.sans, size: 13, weight: .semibold))
                    .foregroundStyle(theme.tokens.text)
                    .lineLimit(1)
                Text(metaLine(detail: detail))
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.muted)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Btn(.ghost, action: { openDetailWindow(uuid: fm.uuid) }) {
                Text("new window")
            }
            Btn(.ghost, action: { openQuickLook() }) {
                HStack(spacing: 4) { Text("quick look"); Kbd("⇧⌘Y") }
            }
        }
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(theme.tokens.surface)
    }

    private func metaLine(detail: RecordDetail) -> String {
        let fm = detail.record.frontmatter
        switch fm.recordType {
        case .source:
            var parts: [String] = []
            if let origin = fm.originName ?? fm.originUrl { parts.append(origin) }
            parts.append("\(fm.artifactRefs.count) artifacts")
            if let cap = fm.captureDate { parts.append("captured \(cap)") }
            return parts.joined(separator: " · ")
        case .document:
            var parts: [String] = []
            parts.append("↳ \(fm.constituents?.count ?? 0) records")
            if let norm = fm.normalizationDate { parts.append("normalized \(norm)") }
            return parts.joined(separator: " · ")
        }
    }

    // MARK: - Tab bar

    private func tabBar(tabs: [DetailTab], active: DetailTab) -> some View {
        HStack(spacing: 0) {
            ForEach(tabs, id: \.self) { tab in
                tabChip(tab: tab, selected: tab == active)
            }
            Spacer(minLength: 8)
            HStack(spacing: 4) {
                ForEach(Array(tabs.prefix(4).enumerated()), id: \.offset) { idx, _ in
                    Kbd("⌘\(idx + 1)")
                }
            }
            .padding(.trailing, 8)
        }
        .padding(.horizontal, 8)
        .frame(height: 28)
        .background(theme.tokens.surface2)
    }

    private func tabChip(tab: DetailTab, selected: Bool) -> some View {
        Button {
            selectedTab = tab
        } label: {
            Text(tab.label)
                .font(.athenaeum(.mono, size: 10, weight: selected ? .semibold : .regular))
                .foregroundStyle(selected ? theme.tokens.accent : theme.tokens.muted)
                .padding(.horizontal, 10)
                .frame(height: 28)
                .overlay(alignment: .bottom) {
                    Rectangle()
                        .fill(selected ? theme.tokens.accent : Color.clear)
                        .frame(height: 2)
                }
        }
        .buttonStyle(.plain)
        .contentShape(Rectangle())
    }

    // MARK: - Tab content

    @ViewBuilder
    private func tabContent(detail: RecordDetail, tab: DetailTab) -> some View {
        switch tab {
        case .original:
            OriginalStub(detail: detail)
        case .normalized:
            NormalizedStub(detail: detail)
        case .artifacts:
            ArtifactsTab(detail: detail, store: store)
        case .dependencies:
            DependenciesTab(detail: detail)
        case .metadata:
            MetadataTab(detail: detail)
        }
    }

    // MARK: - States

    private var loading: some View {
        VStack {
            Spacer()
            ProgressView().controlSize(.small)
            Spacer()
        }
        .frame(maxWidth: .infinity)
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

    private func placeholder(_ text: String) -> some View {
        Text(text)
            .font(.athenaeum(.mono, size: 11))
            .foregroundStyle(theme.tokens.dim)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Tabs

    private func availableTabs(for type: RecordType) -> [DetailTab] {
        switch type {
        case .source: [.original, .normalized, .artifacts, .metadata]
        case .document: [.normalized, .dependencies, .metadata]
        }
    }

    private func openDetailWindow(uuid: UUID) {
        openWindow(id: "detail", value: uuid)
    }

    private func openQuickLook() {
        openWindow(id: "quicklook")
    }
}

enum DetailTab: Hashable {
    case original, normalized, artifacts, dependencies, metadata

    var label: String {
        switch self {
        case .original: "original"
        case .normalized: "normalized"
        case .artifacts: "artifacts"
        case .dependencies: "dependencies"
        case .metadata: "metadata"
        }
    }
}

// MARK: - Pane stubs (Phase 3 fills these in)

private struct OriginalStub: View {
    @Environment(\.theme) private var theme
    let detail: RecordDetail
    var body: some View {
        let fm = detail.record.frontmatter
        return VStack(spacing: 12) {
            Text("Original artifact preview")
                .font(.athenaeum(.sans, size: 13, weight: .semibold))
                .foregroundStyle(theme.tokens.text)
            if let primary = fm.primaryArtifact {
                HStack(spacing: 6) {
                    MimeChip(mime: primary.mimetype ?? fm.contentType)
                    Text(primary.ref)
                        .font(.athenaeum(.mono, size: 10))
                        .foregroundStyle(theme.tokens.muted)
                }
            }
            Text("Per-MIME renderer (pdf / video / image / html / …) ships in Phase 3.")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct NormalizedStub: View {
    @Environment(\.theme) private var theme
    let detail: RecordDetail
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("normalized · markdown")
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)
                if detail.record.body.isEmpty {
                    Text("(empty body)")
                        .font(.athenaeum(.mono, size: 11))
                        .foregroundStyle(theme.tokens.dim)
                } else {
                    Text(detail.record.body)
                        .font(.athenaeum(.sans, size: 13))
                        .foregroundStyle(theme.tokens.text)
                        .textSelection(.enabled)
                        .frame(maxWidth: 720, alignment: .leading)
                }
            }
            .padding(16)
        }
    }
}

private struct ArtifactsTab: View {
    @Environment(\.theme) private var theme
    let detail: RecordDetail
    let store: BrowseStore

    var body: some View {
        let refs = detail.record.frontmatter.artifactRefs
        return ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text("\(refs.count) artifacts · primary marked")
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)
                    .padding(.bottom, 4)
                ForEach(refs) { ref in
                    row(for: ref)
                }
                if refs.isEmpty {
                    Text("(no artifacts)")
                        .font(.athenaeum(.mono, size: 11))
                        .foregroundStyle(theme.tokens.dim)
                }
            }
            .padding(16)
        }
    }

    private func row(for ref: ArtifactRef) -> some View {
        HStack(spacing: 8) {
            MimeChip(mime: ref.mimetype ?? "application/octet-stream")
            Text(ref.ref)
                .font(.athenaeum(.mono, size: 11, weight: ref.primary ? .semibold : .regular))
                .foregroundStyle(ref.primary ? theme.tokens.accent : theme.tokens.text)
            if ref.primary {
                Pill("primary")
            }
            Spacer(minLength: 4)
            Text(String(ref.sha256.prefix(8)))
                .font(.athenaeum(.mono, size: 9))
                .foregroundStyle(theme.tokens.dim)
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 8)
        .background(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(ref.primary ? theme.tokens.accentSoft.opacity(0.3) : theme.tokens.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .strokeBorder(theme.tokens.border, lineWidth: 1)
        )
    }
}

private struct DependenciesTab: View {
    @Environment(\.theme) private var theme
    @Environment(\.openWindow) private var openWindow
    let detail: RecordDetail

    var body: some View {
        let constituents = detail.record.frontmatter.constituents ?? []
        return ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text("\(constituents.count) constituents")
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.dim)
                    .padding(.bottom, 4)
                ForEach(detail.children) { child in
                    row(for: child)
                }
                if constituents.isEmpty && detail.children.isEmpty {
                    Text("(no dependencies)")
                        .font(.athenaeum(.mono, size: 11))
                        .foregroundStyle(theme.tokens.dim)
                }
                if !detail.parents.isEmpty {
                    Text("reverse — records using this")
                        .font(.athenaeum(.mono, size: 10))
                        .foregroundStyle(theme.tokens.dim)
                        .padding(.top, 16)
                    Text("\(detail.parents.count) records")
                        .font(.athenaeum(.mono, size: 11))
                        .foregroundStyle(theme.tokens.muted)
                }
            }
            .padding(16)
        }
    }

    private func row(for child: RecordSummary) -> some View {
        Button {
            openWindow(id: "detail", value: child.uuid)
        } label: {
            HStack(spacing: 8) {
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
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 8)
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

private struct MetadataTab: View {
    @Environment(\.theme) private var theme
    let detail: RecordDetail

    var body: some View {
        let fm = detail.record.frontmatter
        let rows = rows(for: fm)
        return ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    HStack(alignment: .top, spacing: 12) {
                        Text(row.key)
                            .font(.athenaeum(.mono, size: 11))
                            .foregroundStyle(theme.tokens.dim)
                            .frame(width: 170, alignment: .leading)
                        Text(row.value)
                            .font(.athenaeum(.mono, size: 11))
                            .foregroundStyle(theme.tokens.text)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                apiEchoBox(uuid: fm.uuid)
            }
            .padding(16)
        }
    }

    private struct Row { let key: String; let value: String }

    private func rows(for fm: Frontmatter) -> [Row] {
        var out: [Row] = []
        out.append(Row(key: "id", value: fm.uuid.uuidString))
        out.append(Row(key: "kind", value: fm.recordType.rawValue))
        out.append(Row(key: "title", value: fm.title))
        if !fm.description.isEmpty {
            out.append(Row(key: "description", value: fm.description))
        }
        if let origin = fm.originUrl ?? fm.originName {
            out.append(Row(key: "origin", value: origin))
        }
        if let c = fm.constituents, !c.isEmpty {
            out.append(Row(key: "depends_on", value: "\(c.count) records"))
        }
        out.append(Row(key: "primary_mime", value: fm.contentType))
        if !fm.artifactRefs.isEmpty {
            let mimes = fm.artifactRefs.compactMap { $0.mimetype }.joined(separator: ", ")
            out.append(Row(key: "artifacts", value: "\(fm.artifactRefs.count) (\(mimes))"))
        }
        if let cap = fm.captureDate { out.append(Row(key: "captured", value: cap)) }
        if let norm = fm.normalizationDate { out.append(Row(key: "normalized", value: norm)) }
        if !fm.tags.isEmpty { out.append(Row(key: "tags", value: fm.tags.joined(separator: ", "))) }
        out.append(Row(key: "status", value: fm.status.rawValue))
        if let tier = fm.credibilityTier {
            out.append(Row(key: "credibility_tier", value: tier))
        }
        if let v = fm.visibility {
            out.append(Row(key: "visibility", value: v))
        }
        return out
    }

    private func apiEchoBox(uuid: UUID) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("GET /api/records/\(uuid.uuidString.lowercased())")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
            Text("→ returns this record's detail as JSON")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.tokens.surface2)
        .overlay(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .strokeBorder(theme.tokens.border, lineWidth: 1)
        )
        .padding(.top, 16)
    }
}
