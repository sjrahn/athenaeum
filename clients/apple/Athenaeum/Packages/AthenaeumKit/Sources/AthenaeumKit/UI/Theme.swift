import SwiftUI

/// Named color tokens mirroring `tokens.css` from the Claude Design handoff.
/// Semantic — never reach for a raw `Color.red` / `.systemBackground` in views.
public struct ThemeTokens: Sendable {
    public let bg: Color
    public let surface: Color
    public let surface2: Color
    public let surface3: Color
    public let border: Color
    public let borderStrong: Color
    public let text: Color
    public let muted: Color
    public let dim: Color
    public let accent: Color
    public let accentSoft: Color
    public let ok: Color
    public let warn: Color
    public let err: Color

    public static let light = ThemeTokens(
        bg: Color(hex: "#f5f3ee"),
        surface: Color(hex: "#ffffff"),
        surface2: Color(hex: "#ebe8e0"),
        surface3: Color(hex: "#ebe8e0"),
        border: Color(hex: "#d9d5c9"),
        borderStrong: Color(hex: "#b8b2a2"),
        text: Color(hex: "#1a1814"),
        muted: Color(hex: "#6b665a"),
        dim: Color(hex: "#9a9588"),
        accent: Color(hex: "#a35a00"),
        accentSoft: Color(hex: "#f0e4cf"),
        ok: Color(hex: "#2e7d32"),
        warn: Color(hex: "#b8860b"),
        err: Color(hex: "#b00020")
    )

    public static let dark = ThemeTokens(
        bg: Color(hex: "#0f0f0d"),
        surface: Color(hex: "#171714"),
        surface2: Color(hex: "#1e1e1a"),
        surface3: Color(hex: "#26251f"),
        border: Color(hex: "#2d2c26"),
        borderStrong: Color(hex: "#3f3e35"),
        text: Color(hex: "#e8e4d6"),
        muted: Color(hex: "#8f897a"),
        dim: Color(hex: "#5e594e"),
        accent: Color(hex: "#d99a4a"),
        accentSoft: Color(hex: "#3a2a15"),
        ok: Color(hex: "#7fc084"),
        warn: Color(hex: "#d4a84a"),
        err: Color(hex: "#e06a7a")
    )
}

/// User-selectable theme mode persisted in `Config`. `system` follows the
/// environment `ColorScheme`; the other two are explicit overrides.
public enum ThemeMode: String, CaseIterable, Sendable, Codable {
    case system
    case light
    case dark
}

/// Resolved theme for the current environment. Construct via
/// `Theme.resolve(mode:colorScheme:)`; inject via the `.theme(...)` modifier;
/// read inside views via `@Environment(\.theme)`.
public struct Theme: Sendable {
    public let mode: ThemeMode
    public let tokens: ThemeTokens
    public let isDark: Bool

    public static func resolve(mode: ThemeMode, colorScheme: ColorScheme) -> Theme {
        let dark: Bool
        switch mode {
        case .system: dark = (colorScheme == .dark)
        case .light: dark = false
        case .dark: dark = true
        }
        return Theme(
            mode: mode,
            tokens: dark ? .dark : .light,
            isDark: dark
        )
    }

    /// Default fallback (light) — matches what views see before a parent
    /// installs `.theme(...)`. Production app always installs one.
    public static let fallback = Theme(mode: .light, tokens: .light, isDark: false)
}

private struct ThemeKey: EnvironmentKey {
    static let defaultValue: Theme = .fallback
}

extension EnvironmentValues {
    public var theme: Theme {
        get { self[ThemeKey.self] }
        set { self[ThemeKey.self] = newValue }
    }
}

extension View {
    /// Inject a resolved theme into the environment. Place once at the root of
    /// each scene, after computing from `@Environment(\.colorScheme)` and the
    /// user's `ThemeMode` preference.
    public func theme(_ theme: Theme) -> some View {
        environment(\.theme, theme)
    }
}
