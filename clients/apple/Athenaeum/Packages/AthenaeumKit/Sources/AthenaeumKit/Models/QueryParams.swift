import Foundation

/// Parameters for `GET /api/records`. Mirrors Rust `QueryParams`.
///
/// Only `corpus` is required. All other fields default to a sensible "no
/// filter" value. Serialized into the URL via `Endpoints.records(query:)`.
public struct QueryParams: Sendable, Hashable {
    public var corpus: String
    public var q: String
    public var sort: String
    public var offset: UInt64
    public var limit: UInt64
    public var contentType: String?
    public var status: String?
    public var tag: String?
    public var originName: String?
    public var credibilityTier: String?
    public var recordType: String?
    /// Editorial visibility filter. `nil` or `"visible"` hides deranked/hidden.
    /// Pass `"all"` to include everything; pass a specific value to target that tier.
    public var visibility: String?

    public init(
        corpus: String,
        q: String = "",
        sort: String = "title_asc",
        offset: UInt64 = 0,
        limit: UInt64 = 100,
        contentType: String? = nil,
        status: String? = nil,
        tag: String? = nil,
        originName: String? = nil,
        credibilityTier: String? = nil,
        recordType: String? = nil,
        visibility: String? = nil
    ) {
        self.corpus = corpus
        self.q = q
        self.sort = sort
        self.offset = offset
        self.limit = limit
        self.contentType = contentType
        self.status = status
        self.tag = tag
        self.originName = originName
        self.credibilityTier = credibilityTier
        self.recordType = recordType
        self.visibility = visibility
    }

    /// Serialize to `URLQueryItem`s for `URLComponents`.
    public func queryItems() -> [URLQueryItem] {
        var items: [URLQueryItem] = [URLQueryItem(name: "corpus", value: corpus)]
        if !q.isEmpty { items.append(.init(name: "q", value: q)) }
        if !sort.isEmpty { items.append(.init(name: "sort", value: sort)) }
        if offset > 0 { items.append(.init(name: "offset", value: String(offset))) }
        items.append(.init(name: "limit", value: String(limit)))
        if let v = contentType { items.append(.init(name: "content_type", value: v)) }
        if let v = status { items.append(.init(name: "status", value: v)) }
        if let v = tag { items.append(.init(name: "tag", value: v)) }
        if let v = originName { items.append(.init(name: "origin_name", value: v)) }
        if let v = credibilityTier { items.append(.init(name: "credibility_tier", value: v)) }
        if let v = recordType { items.append(.init(name: "record_type", value: v)) }
        if let v = visibility { items.append(.init(name: "visibility", value: v)) }
        return items
    }
}
