import Foundation

/// Actor-wrapped client that speaks every ath-server route. Construct once
/// and share across the app; it's `Sendable` and all methods are async.
public actor APIClient {
    public let endpoints: Endpoints
    private let session: URLSession
    private let decoder: JSONDecoder

    public init(baseURL: URL, session: URLSession = .shared) {
        self.endpoints = Endpoints(baseURL: baseURL)
        self.session = session
        self.decoder = JSONDecoder()
    }

    /// Convenience — reads the configured server URL from the App Group.
    public init(config: Config = Config(), session: URLSession = .shared) {
        self.init(baseURL: config.serverURL, session: session)
    }

    // MARK: - Endpoints

    public func health() async throws -> String {
        try await getString(endpoints.health())
    }

    public func listCorpora() async throws -> [CorpusInfo] {
        try await getJSON(endpoints.corpora())
    }

    public func facets(corpus: String) async throws -> FacetsResponse {
        try await getJSON(endpoints.facets(corpus: corpus))
    }

    public func records(query: QueryParams) async throws -> QueryResult {
        try await getJSON(endpoints.records(query: query))
    }

    public func record(uuid: UUID) async throws -> RecordDetail {
        try await getJSON(endpoints.record(uuid: uuid))
    }

    public nonisolated func fileURL(
        corpus: String,
        kind: String,
        uuid: UUID,
        filename: String
    ) -> URL {
        endpoints.file(corpus: corpus, kind: kind, uuid: uuid, filename: filename)
    }

    /// POST a multipart submission. `files` are read from disk via
    /// `InputStream` — safe to call from memory-constrained contexts.
    public func submit(
        corpus: String,
        title: String,
        description: String? = nil,
        url: String? = nil,
        sourceType: String? = nil,
        files: [Multipart.FilePart]
    ) async throws -> SubmitResponse {
        let multipart = Multipart()
        var textParts: [Multipart.TextPart] = [
            .init(name: "corpus", value: corpus),
            .init(name: "title", value: title),
        ]
        if let description { textParts.append(.init(name: "description", value: description)) }
        if let url { textParts.append(.init(name: "url", value: url)) }
        if let sourceType { textParts.append(.init(name: "source_type", value: sourceType)) }

        let bodyURL: URL
        do {
            bodyURL = try multipart.writeBody(textParts: textParts, fileParts: files)
        } catch {
            throw APIError.invalidResponse("multipart build failed: \(error)")
        }
        defer { try? FileManager.default.removeItem(at: bodyURL) }

        var request = URLRequest(url: endpoints.submit())
        request.httpMethod = "POST"
        request.setValue(multipart.contentType, forHTTPHeaderField: "Content-Type")

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.upload(for: request, fromFile: bodyURL)
        } catch {
            throw mapTransportError(error)
        }
        try validate(response: response, body: data)
        return try decodeBody(data)
    }

    public func submissions(corpus: String) async throws -> SubmissionsResponse {
        try await getJSON(endpoints.submissions(corpus: corpus))
    }

    // MARK: - Low-level helpers

    private func getString(_ url: URL) async throws -> String {
        let (data, response) = try await fetch(url)
        try validate(response: response, body: data)
        guard let string = String(data: data, encoding: .utf8) else {
            throw APIError.invalidResponse("response body is not UTF-8")
        }
        return string
    }

    private func getJSON<T: Decodable>(_ url: URL) async throws -> T {
        let (data, response) = try await fetch(url)
        try validate(response: response, body: data)
        return try decodeBody(data)
    }

    private func fetch(_ url: URL) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(from: url)
        } catch {
            throw mapTransportError(error)
        }
    }

    private func validate(response: URLResponse, body: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse("response is not HTTP")
        }
        guard (200..<300).contains(http.statusCode) else {
            let text = String(data: body, encoding: .utf8)
            throw APIError.statusCode(http.statusCode, body: text)
        }
    }

    private func decodeBody<T: Decodable>(_ data: Data) throws -> T {
        do {
            return try decoder.decode(T.self, from: data)
        } catch let DecodingError.keyNotFound(key, context) {
            throw APIError.decodingFailed(
                "key '\(key.stringValue)' not found: \(context.debugDescription)")
        } catch let DecodingError.typeMismatch(_, context) {
            throw APIError.decodingFailed(
                "type mismatch at \(context.codingPath.map(\.stringValue).joined(separator: ".")): "
                    + context.debugDescription)
        } catch let DecodingError.valueNotFound(_, context) {
            throw APIError.decodingFailed(
                "value missing at \(context.codingPath.map(\.stringValue).joined(separator: ".")): "
                    + context.debugDescription)
        } catch let DecodingError.dataCorrupted(context) {
            throw APIError.decodingFailed("data corrupted: \(context.debugDescription)")
        } catch {
            throw APIError.decodingFailed(String(describing: error))
        }
    }

    private func mapTransportError(_ error: any Error) -> APIError {
        if let urlError = error as? URLError {
            switch urlError.code {
            case .notConnectedToInternet, .cannotConnectToHost,
                .cannotFindHost, .timedOut, .networkConnectionLost:
                return .notReachable(urlError.localizedDescription)
            default:
                return .invalidResponse(urlError.localizedDescription)
            }
        }
        return .invalidResponse(String(describing: error))
    }
}
