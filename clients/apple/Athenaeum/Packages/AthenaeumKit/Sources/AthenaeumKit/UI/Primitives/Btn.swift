import SwiftUI

/// 22pt tall, mono 11pt medium, 2pt radius, 1pt border. Default variant is
/// `surface` bg with a subtle `surface2` hover. Primary swaps to `accent` bg /
/// white fg; ghost is transparent.
public struct Btn<Label: View>: View {
    public enum Variant { case regular, primary, ghost }

    @Environment(\.theme) private var theme
    @State private var isHovered = false
    private let variant: Variant
    private let action: () -> Void
    private let label: () -> Label

    public init(
        _ variant: Variant = .regular,
        action: @escaping () -> Void,
        @ViewBuilder label: @escaping () -> Label
    ) {
        self.variant = variant
        self.action = action
        self.label = label
    }

    public var body: some View {
        Button(action: action) {
            label()
                .font(.athenaeum(.mono, size: 11, weight: .medium))
                .foregroundStyle(foreground)
                .padding(.horizontal, 8)
                .frame(height: 22)
                .background(
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .fill(background)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .strokeBorder(border, lineWidth: variant == .ghost ? 0 : 1)
                )
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { isHovered = $0 }
    }

    private var foreground: Color {
        switch variant {
        case .regular: theme.tokens.text
        case .primary: .white
        case .ghost: theme.tokens.muted
        }
    }
    private var background: Color {
        switch variant {
        case .regular: isHovered ? theme.tokens.surface2 : theme.tokens.surface
        case .primary: theme.tokens.accent
        case .ghost: .clear
        }
    }
    private var border: Color {
        switch variant {
        case .regular: theme.tokens.border
        case .primary: .clear
        case .ghost: .clear
        }
    }
}

extension Btn where Label == Text {
    public init(_ title: String, variant: Variant = .regular, action: @escaping () -> Void) {
        self.init(variant, action: action) { Text(title) }
    }
}
