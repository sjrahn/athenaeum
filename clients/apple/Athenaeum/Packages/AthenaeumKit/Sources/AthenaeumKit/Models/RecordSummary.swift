import Foundation

/// Lightweight record row for list views. Mirrors Rust `RecordSummary`.
///
/// `contentType` is the record's primary MIME (v9) — no client-side
/// derivation needed, list rows can render the `MimeChip` directly.
///
/// `primaryArtifactRef` / `primaryArtifactMimetype` carry just enough
/// information for gallery / list views to build a thumbnail URL without
/// fetching the full record detail per row. Both are absent on document
/// records and on sources with no artifacts.
public struct RecordSummary: Codable, Sendable, Hashable, Identifiable {
    public let uuid: UUID
    public let title: String
    public let status: String
    public let contentType: String
    public let recordType: String
    public let tags: [String]
    /// Editorial visibility; `nil` or `"visible"` = visible.
    public let visibility: String?
    /// The record's primary artifact URI (e.g. `artifacts://image_001.jpg`),
    /// or `nil` when the record has no artifacts.
    public let primaryArtifactRef: String?
    /// The MIME advertised for the primary artifact, or `nil` when absent.
    public let primaryArtifactMimetype: String?

    public var id: UUID { uuid }

    public init(
        uuid: UUID,
        title: String,
        status: String,
        contentType: String,
        recordType: String,
        tags: [String],
        visibility: String? = nil,
        primaryArtifactRef: String? = nil,
        primaryArtifactMimetype: String? = nil
    ) {
        self.uuid = uuid
        self.title = title
        self.status = status
        self.contentType = contentType
        self.recordType = recordType
        self.tags = tags
        self.visibility = visibility
        self.primaryArtifactRef = primaryArtifactRef
        self.primaryArtifactMimetype = primaryArtifactMimetype
    }

    private enum CodingKeys: String, CodingKey {
        case uuid, title, status, tags, visibility
        case contentType = "content_type"
        case recordType = "record_type"
        case primaryArtifactRef = "primary_artifact_ref"
        case primaryArtifactMimetype = "primary_artifact_mimetype"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.uuid = try container.decode(UUID.self, forKey: .uuid)
        self.title = try container.decode(String.self, forKey: .title)
        self.status = try container.decode(String.self, forKey: .status)
        self.contentType = try container.decode(String.self, forKey: .contentType)
        self.recordType = try container.decode(String.self, forKey: .recordType)
        self.tags = try container.decodeIfPresent([String].self, forKey: .tags) ?? []
        self.visibility = try container.decodeIfPresent(String.self, forKey: .visibility)
        self.primaryArtifactRef = try container.decodeIfPresent(
            String.self, forKey: .primaryArtifactRef
        )
        self.primaryArtifactMimetype = try container.decodeIfPresent(
            String.self, forKey: .primaryArtifactMimetype
        )
    }
}

/// Page of records returned by `GET /api/records`.
public struct QueryResult: Codable, Sendable, Hashable {
    public let total: UInt64
    public let records: [RecordSummary]

    public init(total: UInt64, records: [RecordSummary]) {
        self.total = total
        self.records = records
    }
}

/// Full record detail returned by `GET /api/records/:uuid`.
public struct RecordDetail: Codable, Sendable, Hashable {
    public let record: Record
    public let parents: [RecordSummary]
    public let children: [RecordSummary]

    public init(record: Record, parents: [RecordSummary], children: [RecordSummary]) {
        self.record = record
        self.parents = parents
        self.children = children
    }
}
