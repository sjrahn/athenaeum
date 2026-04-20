import Foundation

/// Mirrors Rust `ath_core::model::RecordType`. Wire format is lowercase.
public enum RecordType: String, Codable, Sendable, Hashable {
    case source
    case document
}

/// Mirrors Rust `ath_core::model::Status`. Wire format is lowercase.
///
/// Kept as a closed enum today — if the pipeline grows new values, widen to
/// String on this side *before* shipping the server change.
public enum Status: String, Codable, Sendable, Hashable {
    case stub
    case draft
    case normalized
}
