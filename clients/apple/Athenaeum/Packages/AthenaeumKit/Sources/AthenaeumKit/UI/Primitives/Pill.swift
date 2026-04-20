import SwiftUI

/// 18pt tall, 2pt radius, mono 10pt uppercase with 1pt border. Default variant
/// uses `surface2` bg + `muted` fg.
public struct Pill: View {
    @Environment(\.theme) private var theme
    private let text: String

    public init(_ text: String) { self.text = text }

    public var body: some View {
        Text(text.uppercased())
            .font(.athenaeum(.mono, size: 10, weight: .medium))
            .tracking(0.4)
            .foregroundStyle(theme.tokens.muted)
            .padding(.horizontal, 6)
            .frame(height: 18)
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

/// Accent variant: `accentSoft` bg, `accent` fg, no border.
public struct PillAccent: View {
    @Environment(\.theme) private var theme
    private let text: String

    public init(_ text: String) { self.text = text }

    public var body: some View {
        Text(text.uppercased())
            .font(.athenaeum(.mono, size: 10, weight: .semibold))
            .tracking(0.4)
            .foregroundStyle(theme.tokens.accent)
            .padding(.horizontal, 6)
            .frame(height: 18)
            .background(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(theme.tokens.accentSoft)
            )
    }
}
