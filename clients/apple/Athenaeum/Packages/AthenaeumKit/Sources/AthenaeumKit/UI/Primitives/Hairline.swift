import SwiftUI

/// 1pt horizontal line in the `border` token. Expands to fill its width.
public struct Hairline: View {
    @Environment(\.theme) private var theme
    public init() {}
    public var body: some View {
        Rectangle()
            .fill(theme.tokens.border)
            .frame(height: 1)
    }
}

/// 1pt vertical rule in the `border` token. Expands to fill its height.
public struct VHairline: View {
    @Environment(\.theme) private var theme
    public init() {}
    public var body: some View {
        Rectangle()
            .fill(theme.tokens.border)
            .frame(width: 1)
    }
}
