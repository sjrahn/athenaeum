//
//  PreferencesView.swift
//  Athenaeum
//

import SwiftUI
import AthenaeumKit

struct PreferencesView: View {
    @Environment(PreferencesStore.self) private var preferences
    @Environment(\.theme) private var theme

    var body: some View {
        @Bindable var prefs = preferences

        Form {
            Section("Appearance") {
                Picker("Theme", selection: $prefs.themeMode) {
                    Text("System").tag(ThemeMode.system)
                    Text("Light").tag(ThemeMode.light)
                    Text("Dark").tag(ThemeMode.dark)
                }
                .pickerStyle(.segmented)

                Picker("Density", selection: $prefs.density) {
                    Text("Dense").tag(Density.dense)
                    Text("Comfy").tag(Density.comfy)
                    Text("Spacious").tag(Density.spacious)
                }
                .pickerStyle(.segmented)
            }

            Section("Server") {
                TextField(
                    "Server URL",
                    text: Binding(
                        get: { prefs.serverURL.absoluteString },
                        set: { if let u = URL(string: $0) { prefs.serverURL = u } }
                    )
                )
                .textFieldStyle(.roundedBorder)
            }
        }
        .formStyle(.grouped)
        .frame(width: 420, height: 280)
        .font(.athenaeum(.sans, size: 13))
        .background(theme.tokens.bg)
    }
}
