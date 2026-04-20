import Foundation

/// Four browse list styles, toggled from the toolbar's view switcher. Matches
/// the design's `mac-lists.jsx` inventory.
enum ListVariant: String, CaseIterable, Sendable {
    case columns
    case table
    case gallery
    case cards

    var label: String {
        switch self {
        case .columns: "columns"
        case .table: "table"
        case .gallery: "gallery"
        case .cards: "cards"
        }
    }
}

/// Detail layout mode (Mac-only). Phase 2 ships `.tabbed` only; the other two
/// are placeholders for Phase 6 polish.
enum DetailMode: String, CaseIterable, Sendable {
    case tabbed
    case split
    case drawer
}

/// Kind filter (all / source / document). `all` is the default.
enum KindFilter: String, CaseIterable, Sendable, Hashable {
    case all
    case source
    case document

    var recordTypeParam: String? {
        switch self {
        case .all: nil
        case .source: "source"
        case .document: "document"
        }
    }

    var label: String {
        switch self {
        case .all: "all"
        case .source: "src"
        case .document: "doc"
        }
    }
}
