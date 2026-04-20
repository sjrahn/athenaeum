import SwiftUI

/// Keyboard-hint pill. Mono 10pt text, `surface` bg, 1pt border with a 2pt
/// bottom border to suggest key depth. 2pt radius, `muted` fg.
public struct Kbd: View {
    @Environment(\.theme) private var theme
    private let text: String

    public init(_ text: String) { self.text = text }

    public var body: some View {
        Text(text)
            .font(.athenaeum(.mono, size: 10))
            .foregroundStyle(theme.tokens.muted)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .background(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(theme.tokens.surface)
            )
            .overlay(alignment: .bottom) {
                // 2pt bottom border — suggests key depth
                Rectangle()
                    .fill(theme.tokens.border)
                    .frame(height: 2)
            }
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(theme.tokens.border, lineWidth: 1)
            )
    }
}
