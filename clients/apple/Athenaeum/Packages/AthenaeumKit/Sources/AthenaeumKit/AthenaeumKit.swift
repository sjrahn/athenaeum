import Foundation

/// Top-level namespace for AthenaeumKit. Individual types (APIClient,
/// Config, RecordSummary, …) are top-level and exported directly; this
/// namespace carries metadata and shared utilities.
public enum AthenaeumKit {
    /// Matches `ARCHITECTURE.md` spec version this kit was frozen against.
    public static let schemaVersion = "9.0"
}
