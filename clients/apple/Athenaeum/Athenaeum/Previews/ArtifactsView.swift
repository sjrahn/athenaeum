import SwiftUI
import AthenaeumKit

/// `artifacts` tab (source records only). Lists every artifact ref with
/// filename, MIME chip, primary flag, size placeholder, and short sha. A
/// footer note reminds that every artifact collapses to the single
/// normalized representation in the `normalized` tab.
struct ArtifactsView: View {
    @Environment(\.theme) private var theme
    let detail: RecordDetail
    /// Called when the user clicks an artifact row. Typical wiring: switch
    /// to the `original` tab and seed the ArtifactSwitcher's index to this
    /// artifact. Noop by default so call sites that don't care still compile.
    var onSelect: (ArtifactRef) -> Void = { _ in }

    var body: some View {
        let refs = orderedRefs
        return ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                header(count: refs.count)
                if refs.isEmpty {
                    Text("(no artifacts)")
                        .font(.athenaeum(.mono, size: 11))
                        .foregroundStyle(theme.tokens.dim)
                } else {
                    VStack(spacing: 6) {
                        ForEach(refs) { row(for: $0) }
                    }
                }
                footerNote
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(theme.tokens.bg)
    }

    private var orderedRefs: [ArtifactRef] {
        let refs = detail.record.frontmatter.artifactRefs
        let withIdx = refs.enumerated().map { ($0.offset, $0.element) }
        let sorted = withIdx.sorted { lhs, rhs in
            if lhs.1.primary != rhs.1.primary { return lhs.1.primary }
            return lhs.0 < rhs.0
        }
        return sorted.map(\.1)
    }

    private func header(count: Int) -> some View {
        Text("\(count) artifacts · primary marked")
            .font(.athenaeum(.mono, size: 10))
            .foregroundStyle(theme.tokens.dim)
    }

    private func row(for ref: ArtifactRef) -> some View {
        Button {
            onSelect(ref)
        } label: {
            HStack(spacing: 10) {
                MimeChip(mime: ref.mimetype ?? "application/octet-stream")
                Text(ArtifactRefHelpers.filename(from: ref.ref))
                    .font(.athenaeum(.mono, size: 11, weight: ref.primary ? .semibold : .regular))
                    .foregroundStyle(ref.primary ? theme.tokens.accent : theme.tokens.text)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if ref.primary { Pill("primary") }
                Spacer(minLength: 4)
                Text(String(ref.sha256.prefix(8)))
                    .font(.athenaeum(.mono, size: 9))
                    .foregroundStyle(theme.tokens.dim)
                Image(systemName: "chevron.right")
                    .font(.system(size: 9))
                    .foregroundStyle(theme.tokens.dim)
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .background(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(ref.primary ? theme.tokens.accentSoft.opacity(0.3) : theme.tokens.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(theme.tokens.border, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var footerNote: some View {
        Text("all artifacts normalize to a single representation in the `normalized` tab.")
            .font(.athenaeum(.mono, size: 10))
            .foregroundStyle(theme.tokens.muted)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(theme.tokens.surface2)
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(theme.tokens.border, lineWidth: 1)
            )
            .padding(.top, 8)
    }
}
