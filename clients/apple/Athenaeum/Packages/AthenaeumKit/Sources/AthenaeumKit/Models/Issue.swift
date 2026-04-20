import Foundation

/// A data-quality issue logged on a record. Mirrors `ath_core::model::Issue`.
///
/// `type` is reserved in Swift and on the wire, so it's renamed to `kind`.
public struct Issue: Codable, Sendable, Hashable {
    public let kind: String
    public let severity: String
    public let description: String
    public let remediation: String?
    public let resolved: Bool

    public init(
        kind: String,
        severity: String,
        description: String,
        remediation: String? = nil,
        resolved: Bool = false
    ) {
        self.kind = kind
        self.severity = severity
        self.description = description
        self.remediation = remediation
        self.resolved = resolved
    }

    private enum CodingKeys: String, CodingKey {
        case kind = "type"
        case severity
        case description
        case remediation
        case resolved
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.kind = try container.decode(String.self, forKey: .kind)
        self.severity = try container.decode(String.self, forKey: .severity)
        self.description = try container.decode(String.self, forKey: .description)
        self.remediation = try container.decodeIfPresent(String.self, forKey: .remediation)
        self.resolved = try container.decodeIfPresent(Bool.self, forKey: .resolved) ?? false
    }
}
