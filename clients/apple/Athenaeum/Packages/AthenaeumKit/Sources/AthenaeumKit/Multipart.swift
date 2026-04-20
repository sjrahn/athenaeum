import Foundation

/// Minimal multipart/form-data builder. No third-party deps. Used by the
/// submit endpoint to assemble capture folders.
///
/// File parts are written to disk rather than held in memory so iOS share
/// extensions (≈120 MB memory ceiling) can upload large videos. The caller
/// consumes the result as an `InputStream`-backed URL suitable for
/// `URLSession.upload(for:fromFile:)`.
public struct Multipart {
    public let boundary: String

    public init(boundary: String = "athenaeum-" + UUID().uuidString) {
        self.boundary = boundary
    }

    public var contentType: String { "multipart/form-data; boundary=\(boundary)" }

    public struct TextPart: Sendable {
        public let name: String
        public let value: String
        public init(name: String, value: String) {
            self.name = name
            self.value = value
        }
    }

    public struct FilePart: Sendable {
        public let name: String
        public let filename: String
        public let contentType: String
        public let fileURL: URL
        public init(name: String, filename: String, contentType: String, fileURL: URL) {
            self.name = name
            self.filename = filename
            self.contentType = contentType
            self.fileURL = fileURL
        }
    }

    /// Serialize the given parts to a temp file on disk. Caller is
    /// responsible for removing the returned URL after upload.
    public func writeBody(
        textParts: [TextPart],
        fileParts: [FilePart]
    ) throws -> URL {
        let tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("multipart-\(UUID().uuidString).bin")
        FileManager.default.createFile(atPath: tempURL.path, contents: nil)
        guard let handle = try? FileHandle(forWritingTo: tempURL) else {
            throw APIError.invalidResponse("could not open temp file for multipart body")
        }
        defer { try? handle.close() }

        for part in textParts {
            try handle.write(contentsOf: headerData(for: part))
            try handle.write(contentsOf: Data(part.value.utf8))
            try handle.write(contentsOf: Data("\r\n".utf8))
        }
        for part in fileParts {
            try handle.write(contentsOf: headerData(for: part))
            let input = try FileHandle(forReadingFrom: part.fileURL)
            defer { try? input.close() }
            while let chunk = try input.read(upToCount: 64 * 1024), !chunk.isEmpty {
                try handle.write(contentsOf: chunk)
            }
            try handle.write(contentsOf: Data("\r\n".utf8))
        }
        try handle.write(contentsOf: Data("--\(boundary)--\r\n".utf8))
        return tempURL
    }

    // MARK: - Part headers

    private func headerData(for part: TextPart) -> Data {
        let header =
            "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(escape(part.name))\"\r\n\r\n"
        return Data(header.utf8)
    }

    private func headerData(for part: FilePart) -> Data {
        let header =
            "--\(boundary)\r\n"
            + "Content-Disposition: form-data; name=\"\(escape(part.name))\"; "
            + "filename=\"\(escape(part.filename))\"\r\n"
            + "Content-Type: \(part.contentType)\r\n\r\n"
        return Data(header.utf8)
    }

    /// Escape a header token as RFC 7578 recommends — replace CR/LF/quote
    /// with safe substitutes. Intentionally narrow; not full RFC 2047.
    private func escape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "\r", with: "")
            .replacingOccurrences(of: "\n", with: "")
            .replacingOccurrences(of: "\"", with: "\\\"")
    }
}
