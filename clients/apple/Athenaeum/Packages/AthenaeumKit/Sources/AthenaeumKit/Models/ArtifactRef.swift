import Foundation

/// An artifact attached to a source record.
///
/// Mirrors Rust `ath_core::model::ArtifactRef` (v9). `mimetype` is the
/// canonical MIME for this artifact; `primary` is set on exactly one entry
/// per source (when properly populated) and drives the Original tab's default
/// selection. Both are tolerant during the corpus migration window:
/// `mimetype` may be absent on legacy records; `primary` may be absent on all
/// entries (client falls back to the first artifact).
public struct ArtifactRef: Codable, Sendable, Hashable, Identifiable {
    /// Schema-style URI, e.g. `artifacts://thread.html`.
    public let ref: String
    public let sha256: String
    public let mimetype: String?
    public let primary: Bool

    public var id: String { ref }

    public init(
        ref: String,
        sha256: String,
        mimetype: String? = nil,
        primary: Bool = false
    ) {
        self.ref = ref
        self.sha256 = sha256
        self.mimetype = mimetype
        self.primary = primary
    }

    private enum CodingKeys: String, CodingKey {
        case ref, sha256, mimetype, primary
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.ref = try container.decode(String.self, forKey: .ref)
        self.sha256 = try container.decode(String.self, forKey: .sha256)
        self.mimetype = try container.decodeIfPresent(String.self, forKey: .mimetype)
        self.primary = try container.decodeIfPresent(Bool.self, forKey: .primary) ?? false
    }
}

/// An asset referenced by a document record (figures, attachments derived
/// from merged sources). Mirrors Rust `ath_core::model::AssetRef`.
public struct AssetRef: Codable, Sendable, Hashable, Identifiable {
    public let ref: String
    public let sha256: String?
    public let source: UUID?

    public var id: String { ref }

    public init(ref: String, sha256: String? = nil, source: UUID? = nil) {
        self.ref = ref
        self.sha256 = sha256
        self.source = source
    }
}
