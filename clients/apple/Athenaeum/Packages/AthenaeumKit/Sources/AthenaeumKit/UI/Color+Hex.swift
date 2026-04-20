import SwiftUI

extension Color {
    /// Hex literal initializer for design-token colors. Accepts `"#rrggbb"`,
    /// `"rrggbb"`, `"#rrggbbaa"`, or `"rrggbbaa"`. Invalid strings trap — these
    /// are compile-time constants from `tokens.css`, not user input.
    public init(hex: String) {
        var s = hex
        if s.hasPrefix("#") { s.removeFirst() }
        guard s.count == 6 || s.count == 8, let value = UInt64(s, radix: 16) else {
            preconditionFailure("Color(hex:): invalid literal '\(hex)'")
        }
        let hasAlpha = s.count == 8
        let r = Double((value >> (hasAlpha ? 24 : 16)) & 0xff) / 255.0
        let g = Double((value >> (hasAlpha ? 16 : 8)) & 0xff) / 255.0
        let b = Double((value >> (hasAlpha ? 8 : 0)) & 0xff) / 255.0
        let a = hasAlpha ? Double(value & 0xff) / 255.0 : 1.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: a)
    }
}
