import Foundation

/// Mirrors Rust `ath_core::model::Frontmatter` (v9).
///
/// All date fields arrive from the server as `YYYY-MM-DD` strings — kept as
/// `String?` on this side rather than `Date` to avoid locale/timezone
/// hazards; parse at the call site if needed.
///
/// Extended (content-type-specific) fields are flattened into JSON at the top
/// level by the Rust `#[serde(flatten)]`. This type preserves them via a
/// custom `init(from:)` that strips the known keys and collects the rest
/// into `extended`.
public struct Frontmatter: Codable, Sendable, Hashable {
    // --- Core fields ---
    public let uuid: UUID
    public let title: String
    public let description: String
    public let recordType: RecordType
    /// IANA MIME type. Required on v9 records. `"unknown"` is a valid sentinel.
    public let contentType: String
    public let status: Status
    public let tags: [String]
    /// Editorial visibility. Absent means `"visible"`.
    public let visibility: String?

    // --- Quality ---
    public let credibilityTier: String?
    public let normalizationConfidence: Double
    public let normalizationModel: String?
    public let normalizationDate: String?

    // --- Source-specific ---
    public let originUrl: String?
    public let originName: String?
    public let originalFilename: String?
    public let captureDate: String?
    public let artifactStore: String?
    public let artifactRefs: [ArtifactRef]
    public let author: String?
    public let datePublished: String?

    // --- Document-specific ---
    public let constituents: [UUID]?
    public let mergeRationale: String?
    public let assetStore: String?
    public let assetRefs: [AssetRef]

    // --- Pipeline ---
    public let conversionMethod: String?
    public let conversionTool: String?
    public let conversionDate: String?

    // --- Issues + v9 relations ---
    public let issues: [Issue]
    public let partOf: [UUID]
    public let sameAs: [UUID]

    // --- Extended (content-type-specific) ---
    /// Every top-level JSON field not claimed by one of the typed fields
    /// above. Wire format is snake_case — keys here retain that form.
    public let extended: [String: JSONValue]

    /// The selected primary artifact: the first entry with `primary == true`,
    /// or the first entry if none are flagged. `nil` when the record has no
    /// artifacts (e.g. document records).
    public var primaryArtifact: ArtifactRef? {
        artifactRefs.first(where: \.primary) ?? artifactRefs.first
    }

    // MARK: - Codable

    /// Wire-format keys. Must stay in sync with `ath_core::api_types` /
    /// Rust `Frontmatter` snake_case names.
    private static let knownKeys: Set<String> = [
        "uuid", "title", "description", "record_type", "content_type",
        "status", "tags", "visibility",
        "credibility_tier", "normalization_confidence", "normalization_model",
        "normalization_date",
        "origin_url", "origin_name", "original_filename", "capture_date",
        "artifact_store", "artifact_refs", "author", "date_published",
        "constituents", "merge_rationale", "asset_store", "asset_refs",
        "conversion_method", "conversion_tool", "conversion_date",
        "issues", "part_of", "same_as",
        // v8 compatibility: the server should no longer emit `relations` but
        // if a legacy fixture leaks through, skip rather than put it in
        // `extended`.
        "relations",
    ]

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: DynamicKey.self)

        func string(_ key: String) -> String? {
            try? container.decodeIfPresent(String.self, forKey: DynamicKey(stringValue: key))
        }

        guard let uuidString = string("uuid"), let uuid = UUID(uuidString: uuidString) else {
            throw DecodingError.dataCorruptedError(
                forKey: DynamicKey(stringValue: "uuid"),
                in: container,
                debugDescription: "missing or invalid uuid"
            )
        }
        self.uuid = uuid
        self.title = string("title") ?? ""
        self.description = string("description") ?? ""
        self.recordType = try container.decode(
            RecordType.self,
            forKey: DynamicKey(stringValue: "record_type")
        )
        self.contentType = string("content_type") ?? ""
        self.status = try container.decode(Status.self, forKey: DynamicKey(stringValue: "status"))
        self.tags =
            (try? container.decodeIfPresent([String].self, forKey: DynamicKey(stringValue: "tags")))
            ?? []
        self.visibility = string("visibility")

        self.credibilityTier = string("credibility_tier")
        self.normalizationConfidence =
            (try? container.decodeIfPresent(
                Double.self,
                forKey: DynamicKey(stringValue: "normalization_confidence")
            )) ?? 0
        self.normalizationModel = string("normalization_model")
        self.normalizationDate = string("normalization_date")

        self.originUrl = string("origin_url")
        self.originName = string("origin_name")
        self.originalFilename = string("original_filename")
        self.captureDate = string("capture_date")
        self.artifactStore = string("artifact_store")
        self.artifactRefs =
            (try? container.decodeIfPresent(
                [ArtifactRef].self,
                forKey: DynamicKey(stringValue: "artifact_refs")
            )) ?? []
        self.author = string("author")
        self.datePublished = string("date_published")

        self.constituents = try container.decodeIfPresent(
            [UUID].self,
            forKey: DynamicKey(stringValue: "constituents")
        )
        self.mergeRationale = string("merge_rationale")
        self.assetStore = string("asset_store")
        self.assetRefs =
            (try? container.decodeIfPresent(
                [AssetRef].self,
                forKey: DynamicKey(stringValue: "asset_refs")
            )) ?? []

        self.conversionMethod = string("conversion_method")
        self.conversionTool = string("conversion_tool")
        self.conversionDate = string("conversion_date")

        self.issues =
            (try? container.decodeIfPresent(
                [Issue].self,
                forKey: DynamicKey(stringValue: "issues")
            )) ?? []
        self.partOf =
            (try? container.decodeIfPresent(
                [UUID].self,
                forKey: DynamicKey(stringValue: "part_of")
            )) ?? []
        self.sameAs =
            (try? container.decodeIfPresent(
                [UUID].self,
                forKey: DynamicKey(stringValue: "same_as")
            )) ?? []

        var extended: [String: JSONValue] = [:]
        for key in container.allKeys where !Self.knownKeys.contains(key.stringValue) {
            if let value = try? container.decode(JSONValue.self, forKey: key) {
                extended[key.stringValue] = value
            }
        }
        self.extended = extended
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: DynamicKey.self)

        try container.encode(uuid.uuidString.lowercased(), forKey: DynamicKey(stringValue: "uuid"))
        try container.encode(title, forKey: DynamicKey(stringValue: "title"))
        try container.encode(description, forKey: DynamicKey(stringValue: "description"))
        try container.encode(recordType, forKey: DynamicKey(stringValue: "record_type"))
        try container.encode(contentType, forKey: DynamicKey(stringValue: "content_type"))
        try container.encode(status, forKey: DynamicKey(stringValue: "status"))
        if !tags.isEmpty {
            try container.encode(tags, forKey: DynamicKey(stringValue: "tags"))
        }
        try container.encodeIfPresent(visibility, forKey: DynamicKey(stringValue: "visibility"))

        try container.encodeIfPresent(
            credibilityTier, forKey: DynamicKey(stringValue: "credibility_tier"))
        try container.encode(
            normalizationConfidence,
            forKey: DynamicKey(stringValue: "normalization_confidence"))
        try container.encodeIfPresent(
            normalizationModel, forKey: DynamicKey(stringValue: "normalization_model"))
        try container.encodeIfPresent(
            normalizationDate, forKey: DynamicKey(stringValue: "normalization_date"))

        try container.encodeIfPresent(originUrl, forKey: DynamicKey(stringValue: "origin_url"))
        try container.encodeIfPresent(originName, forKey: DynamicKey(stringValue: "origin_name"))
        try container.encodeIfPresent(
            originalFilename, forKey: DynamicKey(stringValue: "original_filename"))
        try container.encodeIfPresent(captureDate, forKey: DynamicKey(stringValue: "capture_date"))
        try container.encodeIfPresent(
            artifactStore, forKey: DynamicKey(stringValue: "artifact_store"))
        if !artifactRefs.isEmpty {
            try container.encode(artifactRefs, forKey: DynamicKey(stringValue: "artifact_refs"))
        }
        try container.encodeIfPresent(author, forKey: DynamicKey(stringValue: "author"))
        try container.encodeIfPresent(
            datePublished, forKey: DynamicKey(stringValue: "date_published"))

        try container.encodeIfPresent(constituents, forKey: DynamicKey(stringValue: "constituents"))
        try container.encodeIfPresent(
            mergeRationale, forKey: DynamicKey(stringValue: "merge_rationale"))
        try container.encodeIfPresent(assetStore, forKey: DynamicKey(stringValue: "asset_store"))
        if !assetRefs.isEmpty {
            try container.encode(assetRefs, forKey: DynamicKey(stringValue: "asset_refs"))
        }

        try container.encodeIfPresent(
            conversionMethod, forKey: DynamicKey(stringValue: "conversion_method"))
        try container.encodeIfPresent(
            conversionTool, forKey: DynamicKey(stringValue: "conversion_tool"))
        try container.encodeIfPresent(
            conversionDate, forKey: DynamicKey(stringValue: "conversion_date"))

        if !issues.isEmpty {
            try container.encode(issues, forKey: DynamicKey(stringValue: "issues"))
        }
        if !partOf.isEmpty {
            try container.encode(partOf, forKey: DynamicKey(stringValue: "part_of"))
        }
        if !sameAs.isEmpty {
            try container.encode(sameAs, forKey: DynamicKey(stringValue: "same_as"))
        }

        for (key, value) in extended {
            try container.encode(value, forKey: DynamicKey(stringValue: key))
        }
    }
}
