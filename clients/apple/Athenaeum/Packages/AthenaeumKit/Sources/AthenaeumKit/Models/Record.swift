import Foundation

/// Full record as served by `GET /api/records/:uuid` (inside RecordDetail).
public struct Record: Codable, Sendable, Hashable {
    public let frontmatter: Frontmatter
    public let body: String
    /// Server-side filesystem path. Useful for debugging; clients should not
    /// treat it as reachable.
    public let filePath: String

    private enum CodingKeys: String, CodingKey {
        case frontmatter, body
        case filePath = "file_path"
    }
}
