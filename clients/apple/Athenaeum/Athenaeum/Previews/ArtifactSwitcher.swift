import SwiftUI
import AthenaeumKit

/// Horizontal switcher pinned above the Original tab's content. Renders an
/// `ARTIFACT` label on the left, a scrollable row of per-artifact tabs in the
/// middle, and an `idx/n` counter with `[` / `]` kbd hints on the right.
///
/// Driven by a `Binding<Int>` into the owning view's selection state so
/// keyboard shortcuts and mouse clicks stay consistent. The caller is
/// responsible for ordering the artifacts (primary first).
struct ArtifactSwitcher: View {
    @Environment(\.theme) private var theme
    let artifacts: [ArtifactRef]
    @Binding var index: Int

    var body: some View {
        HStack(spacing: 0) {
            label
            VHairline()
            tabs
            VHairline()
            counter
        }
        .frame(height: 36)
        .background(theme.tokens.surface2)
        .overlay(alignment: .bottom) { Hairline() }
    }

    private var label: some View {
        Text("ARTIFACT")
            .font(.athenaeum(.mono, size: 10, weight: .semibold))
            .tracking(1.2)
            .foregroundStyle(theme.tokens.dim)
            .padding(.horizontal, 12)
    }

    private var tabs: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(Array(artifacts.enumerated()), id: \.offset) { idx, ref in
                    tab(for: ref, at: idx)
                }
            }
            .padding(.horizontal, 8)
        }
    }

    private func tab(for ref: ArtifactRef, at idx: Int) -> some View {
        let selected = idx == index
        let filename = ArtifactRefHelpers.filename(from: ref.ref)
        return Button {
            index = idx
        } label: {
            HStack(spacing: 6) {
                MimeChip(mime: ref.mimetype ?? "application/octet-stream")
                Text(filename)
                    .font(.athenaeum(.mono, size: 10, weight: selected ? .semibold : .regular))
                    .foregroundStyle(selected ? theme.tokens.accent : theme.tokens.text)
                    .lineLimit(1)
                if ref.primary {
                    Text("PRIMARY")
                        .font(.athenaeum(.mono, size: 8, weight: .semibold))
                        .tracking(0.8)
                        .foregroundStyle(theme.tokens.accent)
                        .padding(.horizontal, 4)
                        .frame(height: 12)
                        .background(
                            RoundedRectangle(cornerRadius: 2, style: .continuous)
                                .fill(theme.tokens.accentSoft)
                        )
                }
            }
            .padding(.horizontal, 8)
            .frame(height: 24)
            .background(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(selected ? theme.tokens.accentSoft.opacity(0.5) : theme.tokens.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(selected ? theme.tokens.accent : theme.tokens.border, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var counter: some View {
        HStack(spacing: 6) {
            Text("\(min(index + 1, artifacts.count))/\(artifacts.count)")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.muted)
            Kbd("[")
            Kbd("]")
        }
        .padding(.horizontal, 12)
    }
}
