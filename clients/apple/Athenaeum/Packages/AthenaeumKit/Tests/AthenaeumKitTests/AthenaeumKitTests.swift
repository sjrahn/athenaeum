import Foundation
import Testing

@testable import AthenaeumKit

// MARK: - Fixture loading

private struct Fixtures {
    static func data(named name: String) throws -> Data {
        // Swift Package tests: Bundle.module resolves resources copied via
        // Package.swift's `resources:`. Fall back to directly reading from
        // the filesystem for dev-mode invocations.
        if let url = Bundle.module.url(
            forResource: name, withExtension: nil, subdirectory: "Fixtures")
        {
            return try Data(contentsOf: url)
        }
        #if DEBUG
            // Fallback: walk up from the file that built this test to locate
            // Tests/AthenaeumKitTests/Fixtures. Only used when resources
            // aren't bundled.
            let here = URL(fileURLWithPath: #filePath)
            let fixtureURL = here
                .deletingLastPathComponent()
                .appendingPathComponent("Fixtures")
                .appendingPathComponent(name)
            return try Data(contentsOf: fixtureURL)
        #else
            throw NSError(domain: "fixture", code: 1)
        #endif
    }
}

// MARK: - Version / namespace

@Test func schemaVersionIsV9() {
    #expect(AthenaeumKit.schemaVersion == "9.0")
}

// MARK: - Decoding

@Test func decodeCorpora() throws {
    let data = try Fixtures.data(named: "corpora.json")
    let corpora = try JSONDecoder().decode([CorpusInfo].self, from: data)
    #expect(!corpora.isEmpty)
    #expect(corpora.allSatisfy { !$0.name.isEmpty })
}

@Test func decodeFacets() throws {
    let data = try Fixtures.data(named: "facets.json")
    let facets = try JSONDecoder().decode(FacetsResponse.self, from: data)
    #expect(facets.contentTypes.contains("text/html"))
    #expect(facets.statuses.contains("draft"))
}

@Test func decodeRecordsQuery() throws {
    let data = try Fixtures.data(named: "records_query.json")
    let result = try JSONDecoder().decode(QueryResult.self, from: data)
    #expect(result.total > 0)
    #expect(!result.records.isEmpty)
    let first = try #require(result.records.first)
    #expect(first.contentType.contains("/") || first.contentType.isEmpty,
        "contentType should be a MIME string in v9")
    // v9: `visibility` is optional and absent-means-visible
    #expect(first.visibility == nil || first.visibility == "visible")
}

@Test func decodeRecordDetail() throws {
    let data = try Fixtures.data(named: "record_detail.json")
    let detail = try JSONDecoder().decode(RecordDetail.self, from: data)
    let fm = detail.record.frontmatter
    #expect(fm.recordType == .source || fm.recordType == .document)
    #expect(fm.contentType.contains("/") || fm.contentType.isEmpty)
    // Legacy records have artifact_refs without mimetype/primary — confirm
    // tolerant decode.
    for ref in fm.artifactRefs {
        _ = ref.mimetype
        _ = ref.primary
    }
    // Extended fields capture everything not in the typed struct.
    #expect(!fm.extended.isEmpty || fm.contentType.isEmpty,
        "this fixture should carry extended fields")
}

@Test func decodeSubmissions() throws {
    let data = try Fixtures.data(named: "submissions.json")
    let response = try JSONDecoder().decode(SubmissionsResponse.self, from: data)
    _ = response.submissions
}

// MARK: - V9-specific decoding (synthetic fixtures)

@Test func artifactRefPrimaryAndMimetypeDecode() throws {
    let json = """
        [
          {"ref":"artifacts://a.html","sha256":"e3b0","mimetype":"text/html","primary":true},
          {"ref":"artifacts://b.jpg","sha256":"a7ff","mimetype":"image/jpeg"}
        ]
        """.data(using: .utf8)!
    let refs = try JSONDecoder().decode([ArtifactRef].self, from: json)
    #expect(refs.count == 2)
    #expect(refs[0].primary)
    #expect(refs[0].mimetype == "text/html")
    #expect(!refs[1].primary)
    #expect(refs[1].mimetype == "image/jpeg")
}

@Test func frontmatterRoundTripsPartOfAndSameAs() throws {
    let partOf = UUID()
    let sameAs = UUID()
    let source = UUID()
    let json = """
        {
          "uuid": "\(source.uuidString.lowercased())",
          "title": "Test",
          "description": "",
          "record_type": "source",
          "content_type": "text/html",
          "status": "draft",
          "normalization_confidence": 0.0,
          "visibility": "deranked",
          "part_of": ["\(partOf.uuidString.lowercased())"],
          "same_as": ["\(sameAs.uuidString.lowercased())"]
        }
        """.data(using: .utf8)!
    let fm = try JSONDecoder().decode(Frontmatter.self, from: json)
    #expect(fm.partOf == [partOf])
    #expect(fm.sameAs == [sameAs])
    #expect(fm.visibility == "deranked")
    // Round-trip
    let reencoded = try JSONEncoder().encode(fm)
    let fm2 = try JSONDecoder().decode(Frontmatter.self, from: reencoded)
    #expect(fm2.partOf == fm.partOf)
    #expect(fm2.sameAs == fm.sameAs)
    #expect(fm2.visibility == fm.visibility)
}

@Test func frontmatterPreservesExtendedFields() throws {
    let json = """
        {
          "uuid": "00000000-0000-4000-a000-000000000001",
          "title": "T",
          "description": "",
          "record_type": "source",
          "content_type": "text/html",
          "status": "draft",
          "normalization_confidence": 0.9,
          "capture_method": "web_scrape",
          "tsb_number": "08-09-41",
          "reply_count": 47
        }
        """.data(using: .utf8)!
    let fm = try JSONDecoder().decode(Frontmatter.self, from: json)
    #expect(fm.extended["capture_method"] == .string("web_scrape"))
    #expect(fm.extended["tsb_number"] == .string("08-09-41"))
    #expect(fm.extended["reply_count"] == .int(47))
}

@Test func frontmatterPrimaryArtifactSelection() throws {
    let json = """
        {
          "uuid": "00000000-0000-4000-a000-000000000002",
          "title": "T",
          "description": "",
          "record_type": "source",
          "content_type": "text/html",
          "status": "draft",
          "normalization_confidence": 0.0,
          "artifact_refs": [
            {"ref": "artifacts://first.html", "sha256": "aa"},
            {"ref": "artifacts://primary.pdf", "sha256": "bb", "primary": true},
            {"ref": "artifacts://third.jpg", "sha256": "cc"}
          ]
        }
        """.data(using: .utf8)!
    let fm = try JSONDecoder().decode(Frontmatter.self, from: json)
    #expect(fm.primaryArtifact?.ref == "artifacts://primary.pdf")
}

@Test func frontmatterPrimaryArtifactFallsBackToFirst() throws {
    let json = """
        {
          "uuid": "00000000-0000-4000-a000-000000000003",
          "title": "T",
          "description": "",
          "record_type": "source",
          "content_type": "text/html",
          "status": "draft",
          "normalization_confidence": 0.0,
          "artifact_refs": [
            {"ref": "artifacts://only.html", "sha256": "aa"}
          ]
        }
        """.data(using: .utf8)!
    let fm = try JSONDecoder().decode(Frontmatter.self, from: json)
    #expect(fm.primaryArtifact?.ref == "artifacts://only.html")
}

// MARK: - Endpoints

@Test func endpointsBuildURLs() throws {
    let endpoints = Endpoints(baseURL: URL(string: "http://localhost:8080")!)
    #expect(endpoints.health().absoluteString == "http://localhost:8080/api/health")
    #expect(endpoints.corpora().absoluteString == "http://localhost:8080/api/corpora")
    #expect(
        endpoints.facets(corpus: "corpus-public").absoluteString
            == "http://localhost:8080/api/facets?corpus=corpus-public")
    let uuid = UUID(uuidString: "019d7608-1370-7180-9951-44ca8884a2a5")!
    #expect(
        endpoints.record(uuid: uuid).absoluteString
            == "http://localhost:8080/api/records/019d7608-1370-7180-9951-44ca8884a2a5")
}

@Test func endpointsEncodePathSegments() throws {
    let endpoints = Endpoints(baseURL: URL(string: "http://localhost:8080")!)
    let uuid = UUID(uuidString: "019d7608-1370-7180-9951-44ca8884a2a5")!
    let url = endpoints.file(
        corpus: "corpus-public",
        kind: "artifacts",
        uuid: uuid,
        filename: "weird name with spaces & hash#.html"
    )
    // Filename percent-encoded; spaces become %20 (or +); `/` never leaks.
    #expect(!url.absoluteString.contains(" "))
    #expect(!url.absoluteString.contains("#"))
    #expect(!url.path.contains("//"))
    #expect(url.pathComponents.last != nil)
}

@Test func queryParamsEmitExpectedQueryItems() throws {
    let q = QueryParams(
        corpus: "corpus-public",
        q: "brake",
        sort: "newest_first",
        offset: 100,
        limit: 50,
        contentType: "text/html",
        recordType: "source",
        visibility: "all"
    )
    let items = q.queryItems()
    #expect(items.contains { $0.name == "corpus" && $0.value == "corpus-public" })
    #expect(items.contains { $0.name == "q" && $0.value == "brake" })
    #expect(items.contains { $0.name == "offset" && $0.value == "100" })
    #expect(items.contains { $0.name == "limit" && $0.value == "50" })
    #expect(items.contains { $0.name == "content_type" && $0.value == "text/html" })
    #expect(items.contains { $0.name == "record_type" && $0.value == "source" })
    #expect(items.contains { $0.name == "visibility" && $0.value == "all" })
}

// MARK: - Multipart

@Test func multipartWritesBoundaryAndHeaders() throws {
    let multipart = Multipart(boundary: "TESTBOUNDARY")
    #expect(multipart.contentType == "multipart/form-data; boundary=TESTBOUNDARY")
    let bodyURL = try multipart.writeBody(
        textParts: [.init(name: "corpus", value: "corpus-public")],
        fileParts: []
    )
    defer { try? FileManager.default.removeItem(at: bodyURL) }
    let body = try String(contentsOf: bodyURL, encoding: .utf8)
    #expect(body.contains("--TESTBOUNDARY"))
    #expect(body.contains("Content-Disposition: form-data; name=\"corpus\""))
    #expect(body.contains("corpus-public"))
    #expect(body.hasSuffix("--TESTBOUNDARY--\r\n"))
}

@Test func multipartIncludesFileParts() throws {
    let tempFile = FileManager.default.temporaryDirectory
        .appendingPathComponent("test-\(UUID().uuidString).txt")
    try "hello-athenaeum".write(to: tempFile, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: tempFile) }

    let multipart = Multipart(boundary: "B")
    let bodyURL = try multipart.writeBody(
        textParts: [.init(name: "title", value: "T")],
        fileParts: [
            .init(
                name: "file", filename: "hello.txt", contentType: "text/plain", fileURL: tempFile)
        ]
    )
    defer { try? FileManager.default.removeItem(at: bodyURL) }
    let body = try String(contentsOf: bodyURL, encoding: .utf8)
    #expect(body.contains("Content-Disposition: form-data; name=\"file\"; filename=\"hello.txt\""))
    #expect(body.contains("Content-Type: text/plain"))
    #expect(body.contains("hello-athenaeum"))
}

// MARK: - Config (in-memory UserDefaults)

@Test func configReadsAndWritesServerURL() {
    let suite = "athenaeum-test-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let config = Config(defaults: defaults)
    #expect(config.serverURL == Config.defaultServerURL)
    let custom = URL(string: "http://example.test:8080")!
    config.serverURL = custom
    #expect(config.serverURL == custom)
}

@Test func configReadsAndWritesLastUsedCorpus() {
    let suite = "athenaeum-test-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let config = Config(defaults: defaults)
    #expect(config.lastUsedCorpus == nil)
    config.lastUsedCorpus = "corpus-public"
    #expect(config.lastUsedCorpus == "corpus-public")
    config.lastUsedCorpus = nil
    #expect(config.lastUsedCorpus == nil)
}
