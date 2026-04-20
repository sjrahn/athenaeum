import Foundation

/// Lightweight record row for list views. Mirrors Rust `RecordSummary`.
///
/// `contentType` is the record's primary MIME (v9) — no client-side
/// derivation needed, list rows can render the `MimeChip` directly.
public struct RecordSummary: Codable, Sendable, Hashable, Identifiable {
    public let uuid: UUID
    public let title: String
    public let status: String
    public let contentType: String
    public let recordType: String
    public let tags: [String]
    /// Editorial visibility; `nil` or `"visible"` = visible.
    public let visibility: String?

    public var id: UUID { uuid }

    public init(
        uuid: UUID,
        title: String,
        status: String,
        contentType: String,
        recordType: String,
        tags: [String],
        visibility: String? = nil
    ) {
        self.uuid = uuid
        self.title = title
        self.status = status
        self.contentType = contentType
        self.recordType = recordType
        self.tags = tags
        self.visibility = visibility
    }

    private enum CodingKeys: String, CodingKey {
        case uuid, title, status, tags, visibility
        case contentType = "content_type"
        case recordType = "record_type"
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
