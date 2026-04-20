//
//  AthenaeumApp.swift
//  Athenaeum
//

import SwiftUI
import AthenaeumKit

@main
struct AthenaeumApp: App {
    @State private var preferences: PreferencesStore
    @State private var browse: BrowseStore

    init() {
        AthenaeumFonts.registerBundledFonts()
        let prefs = PreferencesStore()
        _preferences = State(initialValue: prefs)
        _browse = State(initialValue: BrowseStore(preferences: prefs))
    }

    var body: some Scene {
        WindowGroup("Athenaeum") {
            ContentView()
                .athenaeumEnvironment(preferences)
                .environment(browse)
                .task { browse.start() }
        }
        .defaultSize(width: 1280, height: 820)
        .commands {
            CommandGroup(after: .sidebar) {
                Button("Switch to corpus-public") {
                    browse.switchCorpus("corpus-public")
                }
                .keyboardShortcut("1", modifiers: [.command, .control])
                Button("Switch to corpus-private") {
                    browse.switchCorpus("corpus-private")
                }
                .keyboardShortcut("2", modifiers: [.command, .control])
            }
            CommandMenu("Corpus") {
                Button("Reload") { browse.reloadAll() }
                    .keyboardShortcut("r", modifiers: [.command])
                Divider()
                Button("Switch to corpus-public") {
                    browse.switchCorpus("corpus-public")
                }
                Button("Switch to corpus-private") {
                    browse.switchCorpus("corpus-private")
                }
            }
            CommandMenu("View") {
                Picker("List style", selection: Binding(
                    get: { browse.listVariant },
                    set: { browse.listVariant = $0 }
                )) {
                    ForEach(ListVariant.allCases, id: \.self) { v in
                        Text(v.label).tag(v)
                    }
                }
            }
        }

        WindowGroup(id: "detail", for: UUID.self) { $uuid in
            if let uuid {
                DetailWindow(uuid: uuid)
                    .athenaeumEnvironment(preferences)
                    .environment(browse)
            } else {
                Text("no record")
            }
        }

        Window("Quick Look", id: "quicklook") {
            QuickLookWindow()
                .athenaeumEnvironment(preferences)
                .environment(browse)
        }
        .defaultSize(width: 360, height: 320)
        .keyboardShortcut("y", modifiers: [.shift, .command])

        Window("Submit", id: "submit") {
            SubmitWindow()
                .athenaeumEnvironment(preferences)
        }
        .defaultSize(width: 520, height: 460)

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
