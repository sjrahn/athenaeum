//
//  AthenaeumApp.swift
//  Athenaeum
//

import SwiftUI
import AthenaeumKit

@main
struct AthenaeumApp: App {
    @State private var preferences: PreferencesStore

    init() {
        AthenaeumFonts.registerBundledFonts()
        _preferences = State(initialValue: PreferencesStore())
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .athenaeumEnvironment(preferences)
        }

        #if os(macOS)
        Settings {
            PreferencesView()
                .athenaeumEnvironment(preferences)
        }
        #endif
    }
}

extension View {
    /// Installs theme + density + preferences into the environment. Compose
    /// once at the root of each scene so every descendant sees the same
    /// resolved theme.
    @MainActor
    func athenaeumEnvironment(_ preferences: PreferencesStore) -> some View {
        modifier(AthenaeumEnvironment(preferences: preferences))
    }
}

private struct AthenaeumEnvironment: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    let preferences: PreferencesStore

    func body(content: Content) -> some View {
        let theme = Theme.resolve(mode: preferences.themeMode, colorScheme: colorScheme)
        content
            .environment(preferences)
            .theme(theme)
            .density(preferences.density)
            .background(theme.tokens.bg)
            .foregroundStyle(theme.tokens.text)
            .preferredColorScheme(
                preferences.themeMode == .system ? nil : (preferences.themeMode == .dark ? .dark : .light)
            )
    }
}
