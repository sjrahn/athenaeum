import Foundation

/// App-Group-backed settings shared between the main app and the share
/// extensions. Thin wrapper around `UserDefaults(suiteName:)` — don't reach
/// for `UserDefaults.standard` anywhere in AthenaeumKit.
// UserDefaults is thread-safe for atomic reads/writes of property-list
// types, which is all this struct performs. Swift's strict concurrency can't
// prove that statically, so we opt into `@unchecked Sendable` deliberately.
public struct Config: @unchecked Sendable {
    /// The canonical App Group identifier for Athenaeum. Matches
    /// `APPLE-CLIENT-PLAN.md`.
    public static let appGroup = "group.dev.rahn.athenaeum"

    /// Default server URL used on first launch; overridable via the
    /// Preferences / Settings scene.
    public static let defaultServerURL = URL(string: "http://example-host.tailnet.example:8080")!

    private let defaults: UserDefaults

    /// Production initializer — backs storage with the App Group suite.
    public init() {
        guard let defaults = UserDefaults(suiteName: Self.appGroup) else {
            fatalError(
                "AthenaeumKit.Config: couldn't open UserDefaults for group \(Self.appGroup) — "
                    + "check that the app target declares the App Group capability."
            )
        }
        self.defaults = defaults
    }

    /// Test initializer.
    public init(defaults: UserDefaults) {
        self.defaults = defaults
    }

    public var serverURL: URL {
        get {
            (defaults.string(forKey: Keys.serverURL).flatMap(URL.init(string:)))
                ?? Self.defaultServerURL
        }
        nonmutating set {
            defaults.set(newValue.absoluteString, forKey: Keys.serverURL)
        }
    }

    public var lastUsedCorpus: String? {
        get { defaults.string(forKey: Keys.lastUsedCorpus) }
        nonmutating set {
            if let value = newValue {
                defaults.set(value, forKey: Keys.lastUsedCorpus)
            } else {
                defaults.removeObject(forKey: Keys.lastUsedCorpus)
            }
        }
    }

    private enum Keys {
        static let serverURL = "athenaeum.serverURL"
        static let lastUsedCorpus = "athenaeum.lastUsedCorpus"
    }
}
