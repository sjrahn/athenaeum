import SwiftUI

/// 14pt tall, mono 9pt SemiBold uppercase, 1pt border, transparent bg.
/// `.source` → accent (label `SRC`). `.document` → `#4a6b8a` (label `DOC`).
public struct KindChip: View {
    @Environment(\.theme) private var theme
    private let kind: Kind

    public enum Kind { case source, document }

    public init(_ kind: Kind) { self.kind = kind }

    public init(recordType: RecordType) {
        switch recordType {
        case .source: self.kind = .source
        case .document: self.kind = .document
        }
    }

    private var color: Color {
        switch kind {
        case .source: return theme.tokens.accent
        case .document: return Color(hex: "#4a6b8a")
        }
    }

    private var label: String {
        switch kind {
        case .source: return "SRC"
        case .document: return "DOC"
        }
    }

    public var body: some View {
        Text(label)
            .font(.athenaeum(.mono, size: 9, weight: .semibold))
            .tracking(0.6)
            .foregroundStyle(color)
            .padding(.horizontal, 4)
            .frame(height: 14)
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(color, lineWidth: 1)
            )
    }
}
