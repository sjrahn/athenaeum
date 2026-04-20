import SwiftUI

/// Three-step density scale. Drives row height, paddings, gap, and text sizes
/// across every list / toolbar / detail surface. Default is `.dense`.
public enum Density: String, CaseIterable, Sendable, Codable {
    case dense
    case comfy
    case spacious

    public var rowH: CGFloat {
        switch self { case .dense: 22; case .comfy: 28; case .spacious: 36 }
    }
    public var padX: CGFloat {
        switch self { case .dense: 8; case .comfy: 12; case .spacious: 16 }
    }
    public var gap: CGFloat {
        switch self { case .dense: 4; case .comfy: 6; case .spacious: 10 }
    }
    public var fs: CGFloat {
        switch self { case .dense: 11; case .comfy: 12; case .spacious: 13 }
    }
    public var fsSm: CGFloat {
        switch self { case .dense: 10; case .comfy: 11; case .spacious: 12 }
    }
    public var fsLg: CGFloat {
        switch self { case .dense: 13; case .comfy: 14; case .spacious: 15 }
    }
}

private struct DensityKey: EnvironmentKey {
    static let defaultValue: Density = .dense
}

extension EnvironmentValues {
    public var density: Density {
        get { self[DensityKey.self] }
        set { self[DensityKey.self] = newValue }
    }
}

extension View {
    public func density(_ density: Density) -> some View {
        environment(\.density, density)
    }
}
