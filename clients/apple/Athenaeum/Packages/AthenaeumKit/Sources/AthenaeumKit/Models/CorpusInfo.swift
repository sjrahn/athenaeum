import Foundation

/// A corpus entry returned by `GET /api/corpora`.
public struct CorpusInfo: Codable, Sendable, Hashable, Identifiable {
    public let name: String
    public let recordCount: UInt64

    public var id: String { name }

    public init(name: String, recordCount: UInt64) {
        self.name = name
        self.recordCount = recordCount
    }

    private enum CodingKeys: String, CodingKey {
        case name
        case recordCount = "record_count"
    }
}
