import Foundation

/// URL construction for every ath-server route. All methods return `URL` —
/// actual transport lives in `APIClient`. Keeping this free-function style
/// makes URLs trivially testable without spinning up the actor.
public struct Endpoints: Sendable {
    public let baseURL: URL

    public init(baseURL: URL) {
        self.baseURL = baseURL
    }

    public func health() -> URL { baseURL.appending(path: "api/health") }
    public func corpora() -> URL { baseURL.appending(path: "api/corpora") }

    public func facets(corpus: String) -> URL {
        var components = components(path: "api/facets")
        components.queryItems = [URLQueryItem(name: "corpus", value: corpus)]
        return components.url!
    }

    public func records(query: QueryParams) -> URL {
        var components = components(path: "api/records")
        components.queryItems = query.queryItems()
        return components.url!
    }

    public func record(uuid: UUID) -> URL {
        baseURL.appending(path: "api/records/\(uuid.uuidString.lowercased())")
    }

    public func file(corpus: String, kind: String, uuid: UUID, filename: String) -> URL {
        // Path components need to be percent-encoded individually so that
        // filenames with spaces, `#`, `?`, etc. don't break the URL.
        let encodedCorpus = encodePathSegment(corpus)
        let encodedKind = encodePathSegment(kind)
        let encodedFilename = encodePathSegment(filename)
        let uuidString = uuid.uuidString.lowercased()
        return baseURL.appending(
            path: "api/files/\(encodedCorpus)/\(encodedKind)/\(uuidString)/\(encodedFilename)"
        )
    }

    public func submit() -> URL { baseURL.appending(path: "api/submit") }

    public func submissions(corpus: String) -> URL {
        var components = components(path: "api/submissions")
        components.queryItems = [URLQueryItem(name: "corpus", value: corpus)]
        return components.url!
    }

    public func reload() -> URL { baseURL.appending(path: "api/reload") }

    // MARK: - Private helpers

    private func components(path: String) -> URLComponents {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
            ?? URLComponents()
        components.scheme = components.scheme ?? baseURL.scheme
        components.host = components.host ?? baseURL.host
        components.port = components.port ?? baseURL.port
        // Join base path (if any) with our path.
        let basePath = baseURL.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let joined = basePath.isEmpty ? path : "\(basePath)/\(path)"
        components.path = "/\(joined)"
        return components
    }

    private func encodePathSegment(_ segment: String) -> String {
        // `urlPathAllowed` lets `/` through, which we explicitly don't want
        // inside a single path segment.
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove(charactersIn: "/")
        return segment.addingPercentEncoding(withAllowedCharacters: allowed) ?? segment
    }
}
