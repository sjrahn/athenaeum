import SwiftUI
import CoreText
import os

/// Athenaeum's two typefaces. Mono = JetBrains Mono (UI chrome, metadata);
/// sans = IBM Plex Sans (titles, body prose). Never `.system` as a design
/// choice — fallbacks are bug markers only.
public enum AthenaeumFontFamily: Sendable {
    case mono
    case sans
}

extension Font {
    /// Returns a design-system font. `weight` maps to the registered face
    /// (regular/medium/semibold/bold); intermediate SwiftUI weights fall
    /// through to the nearest match.
    public static func athenaeum(
        _ family: AthenaeumFontFamily,
        size: CGFloat,
        weight: Font.Weight = .regular
    ) -> Font {
        let name = AthenaeumFonts.postScriptName(family: family, weight: weight)
        return .custom(name, fixedSize: size)
    }

    /// Same as above but scales with Dynamic Type against the provided
    /// `TextStyle`. Use for body prose (`NormalizedView`), not UI chrome.
    public static func athenaeumRelative(
        _ family: AthenaeumFontFamily,
        size: CGFloat,
        weight: Font.Weight = .regular,
        relativeTo textStyle: Font.TextStyle = .body
    ) -> Font {
        let name = AthenaeumFonts.postScriptName(family: family, weight: weight)
        return .custom(name, size: size, relativeTo: textStyle)
    }
}

/// Registers bundled font files with the CoreText font manager. Call once at
/// app launch (before any SwiftUI view materializes) from every process that
/// needs to render text — main app and share extensions alike.
public enum AthenaeumFonts {
    private static let log = Logger(subsystem: "dev.rahn.athenaeum", category: "fonts")
    private static let fontFileNames: [String] = [
        "JetBrainsMono-Regular",
        "JetBrainsMono-Medium",
        "JetBrainsMono-SemiBold",
        "JetBrainsMono-Bold",
        "IBMPlexSans-Regular",
        "IBMPlexSans-Medium",
        "IBMPlexSans-SemiBold",
        "IBMPlexSans-Bold",
    ]

    private static let registrationLock = NSLock()
    nonisolated(unsafe) private static var didRegister = false

    /// Idempotent. Safe to call from multiple entry points.
    public static func registerBundledFonts() {
        registrationLock.lock()
        defer { registrationLock.unlock() }
        guard !didRegister else { return }
        didRegister = true

        let bundle = Bundle.module
        var registered = 0
        var missing: [String] = []
        for name in fontFileNames {
            guard let url = bundle.url(forResource: name, withExtension: "ttf", subdirectory: "Fonts")
                ?? bundle.url(forResource: name, withExtension: "ttf")
            else {
                missing.append(name)
                continue
            }
            var err: Unmanaged<CFError>?
            if CTFontManagerRegisterFontsForURL(url as CFURL, .process, &err) {
                registered += 1
            } else if let error = err?.takeRetainedValue() {
                let desc = CFErrorCopyDescription(error) as String? ?? "unknown"
                log.warning("font registration failed for \(name): \(desc)")
            }
        }
        if !missing.isEmpty {
            log.warning("missing bundled fonts: \(missing.joined(separator: ", "))")
        }
        log.debug("registered \(registered) of \(fontFileNames.count) bundled fonts")
    }

    /// Map (family, weight) to the PostScript name of the registered face.
    /// Note: IBM Plex Sans uses abbreviated suffixes in its PS names
    /// (`Medm` / `SmBld`) and has no suffix on the regular face.
    static func postScriptName(family: AthenaeumFontFamily, weight: Font.Weight) -> String {
        switch (family, bucket(for: weight)) {
        case (.mono, .regular): "JetBrainsMono-Regular"
        case (.mono, .medium): "JetBrainsMono-Medium"
        case (.mono, .semibold): "JetBrainsMono-SemiBold"
        case (.mono, .bold): "JetBrainsMono-Bold"
        case (.sans, .regular): "IBMPlexSans"
        case (.sans, .medium): "IBMPlexSans-Medm"
        case (.sans, .semibold): "IBMPlexSans-SmBld"
        case (.sans, .bold): "IBMPlexSans-Bold"
        }
    }

    private enum WeightBucket { case regular, medium, semibold, bold }

    private static func bucket(for weight: Font.Weight) -> WeightBucket {
        switch weight {
        case .ultraLight, .thin, .light, .regular: .regular
        case .medium: .medium
        case .semibold: .semibold
        case .bold, .heavy, .black: .bold
        default: .regular
        }
    }
}
