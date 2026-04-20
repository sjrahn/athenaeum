import SwiftUI

/// 8×8pt color swatch — used in sidebar facet rows and kind filters.
public struct SmallSq: View {
    private let color: Color
    public init(_ color: Color) { self.color = color }
    public var body: some View {
        Rectangle()
            .fill(color)
            .frame(width: 8, height: 8)
    }
}
