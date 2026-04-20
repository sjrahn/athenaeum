import Foundation
import AthenaeumKit

/// Single-axis async state for views. `APIError` is the surfaced error so
/// banners / error rows can render a consistent message.
enum LoadState<T: Sendable>: Sendable {
    case idle
    case loading
    case loaded(T)
    case error(APIError)

    var value: T? {
        if case .loaded(let v) = self { return v } else { return nil }
    }
    var error: APIError? {
        if case .error(let e) = self { return e } else { return nil }
    }
    var isLoading: Bool {
        if case .loading = self { return true } else { return false }
    }
}

/// Liveness of the server, independent of query state. Polled every 10s.
enum HealthState: Sendable, Equatable {
    case unknown
    case ok
    case down(String)

    var isOK: Bool { if case .ok = self { return true } else { return false } }
}
