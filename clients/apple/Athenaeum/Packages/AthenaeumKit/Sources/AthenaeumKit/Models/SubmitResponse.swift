import Foundation

/// Response from `POST /api/submit`.
public struct SubmitResponse: Codable, Sendable, Hashable {
    public let folder: String
    public let fileCount: UInt32

    public init(folder: String, fileCount: UInt32) {
        self.folder = folder
        self.fileCount = fileCount
    }

    private enum CodingKeys: String, CodingKey {
        case folder
        case fileCount = "file_count"
    }
}

/// A pending capture folder in the submission queue.
public struct SubmissionEntry: Codable, Sendable, Hashable, Identifiable {
    public let folder: String
    public let title: String
    public let url: String?
    public let sourceType: String?
    /// RFC 3339 timestamp string. May be empty if capture metadata is missing.
    public let captureDate: String
    public let files: [String]

    public var id: String { folder }

    public init(
        folder: String,
        title: String,
        url: String? = nil,
        sourceType: String? = nil,
        captureDate: String,
        files: [String]
    ) {
        self.folder = folder
        self.title = title
        self.url = url
        self.sourceType = sourceType
        self.captureDate = captureDate
        self.files = files
    }

    private enum CodingKeys: String, CodingKey {
        case folder, title, url, files
        case sourceType = "source_type"
        case captureDate = "capture_date"
    }
}

/// Response from `GET /api/submissions?corpus=X`.
public struct SubmissionsResponse: Codable, Sendable, Hashable {
    public let submissions: [SubmissionEntry]

    public init(submissions: [SubmissionEntry]) {
        self.submissions = submissions
    }
}
