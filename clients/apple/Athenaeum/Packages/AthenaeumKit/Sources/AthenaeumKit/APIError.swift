import Foundation

/// The single error surface AthenaeumKit presents to callers. Views consume
/// this enum to render a consistent banner; internal URLError / DecodingError
/// are wrapped and never leaked.
public enum APIError: Error, Sendable, Equatable {
    /// Server is unreachable (connection refused, DNS failure, offline).
    case notReachable(String)
    /// Response decoded to an HTTP error status.
    case statusCode(Int, body: String?)
    /// The server returned something we couldn't make sense of (missing body,
    /// wrong Content-Type, unexpected structure at a pre-decode layer).
    case invalidResponse(String)
    /// JSON decoding failed. The string is a best-effort description of
    /// which key / type mismatched — useful in logs, not for end users.
    case decodingFailed(String)

    public var localizedDescription: String {
        switch self {
        case .notReachable(let detail):
            "Cannot reach Athenaeum server — \(detail)"
        case .statusCode(let code, let body):
            body.map { "Server returned \(code): \($0)" } ?? "Server returned \(code)"
        case .invalidResponse(let detail):
            "Invalid response — \(detail)"
        case .decodingFailed(let detail):
            "Could not decode response — \(detail)"
        }
    }
}
