import Foundation

/// Distinct filter values for a corpus. Returned by `GET /api/facets?corpus=X`.
public struct FacetsResponse: Codable, Sendable, Hashable {
    public let contentTypes: [String]
    public let statuses: [String]
    public let tags: [String]
    public let originNames: [String]
    public let credibilityTiers: [String]

    public init(
        contentTypes: [String],
        statuses: [String],
        tags: [String],
        originNames: [String],
        credibilityTiers: [String]
    ) {
        self.contentTypes = contentTypes
        self.statuses = statuses
        self.tags = tags
        self.originNames = originNames
        self.credibilityTiers = credibilityTiers
    }

    private enum CodingKeys: String, CodingKey {
        case contentTypes = "content_types"
        case statuses, tags
        case originNames = "origin_names"
        case credibilityTiers = "credibility_tiers"
    }
}
