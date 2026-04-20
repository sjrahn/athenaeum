import Foundation
import Observation

/// Observable wrapper around `Config` so SwiftUI views can bind to preferences
/// and persist changes. UserDefaults doesn't publish mutations, so this type
/// is the single source of truth at runtime — never read `Config` directly
/// inside a view body once the store is in the environment.
@Observable
@MainActor
public final class PreferencesStore {
    public var serverURL: URL {
        didSet { config.serverURL = serverURL }
    }
    public var lastUsedCorpus: String? {
        didSet { config.lastUsedCorpus = lastUsedCorpus }
    }
    public var themeMode: ThemeMode {
        didSet { config.themeMode = themeMode }
    }
    public var density: Density {
        didSet { config.density = density }
    }

    private let config: Config

    public init(config: Config = Config()) {
        self.config = config
        self.serverURL = config.serverURL
        self.lastUsedCorpus = config.lastUsedCorpus
        self.themeMode = config.themeMode
        self.density = config.density
    }
}
