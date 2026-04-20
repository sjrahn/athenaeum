import SwiftUI
import AthenaeumKit

/// `metadata` tab. Mono 11pt key/value table with a 170pt dim left column and
/// a selectable right column. Ends with an API-echo box showing the
/// `GET /api/records/{uuid}` call shape.
struct MetadataView: View {
    @Environment(\.theme) private var theme
    let detail: RecordDetail

    var body: some View {
        let fm = detail.record.frontmatter
        let rows = Self.rows(for: fm)
        return ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    HStack(alignment: .top, spacing: 12) {
                        Text(row.key)
                            .font(.athenaeum(.mono, size: 11))
                            .foregroundStyle(theme.tokens.dim)
                            .frame(width: 170, alignment: .leading)
                        Text(row.value)
                            .font(.athenaeum(.mono, size: 11))
                            .foregroundStyle(theme.tokens.text)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                apiEchoBox(uuid: fm.uuid)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(theme.tokens.bg)
    }

    private struct Row { let key: String; let value: String }

    private static func rows(for fm: Frontmatter) -> [Row] {
        var out: [Row] = []
        out.append(Row(key: "id", value: fm.uuid.uuidString))
        out.append(Row(key: "kind", value: fm.recordType.rawValue))
        out.append(Row(key: "title", value: fm.title))
        if !fm.description.isEmpty {
            out.append(Row(key: "description", value: fm.description))
        }
        if let origin = fm.originUrl ?? fm.originName {
            out.append(Row(key: "origin", value: origin))
        }
        if let c = fm.constituents, !c.isEmpty {
            out.append(Row(key: "depends_on", value: "\(c.count) records"))
        }
        out.append(Row(key: "primary_mime", value: fm.contentType))
        if !fm.artifactRefs.isEmpty {
            let mimes = fm.artifactRefs.compactMap { $0.mimetype }.joined(separator: ", ")
            out.append(Row(key: "artifacts", value: "\(fm.artifactRefs.count) (\(mimes))"))
        }
        if let cap = fm.captureDate { out.append(Row(key: "captured", value: cap)) }
        if let norm = fm.normalizationDate { out.append(Row(key: "normalized", value: norm)) }
        if !fm.tags.isEmpty { out.append(Row(key: "tags", value: fm.tags.joined(separator: ", "))) }
        out.append(Row(key: "status", value: fm.status.rawValue))
        if let tier = fm.credibilityTier {
            out.append(Row(key: "credibility_tier", value: tier))
        }
        if let v = fm.visibility {
            out.append(Row(key: "visibility", value: v))
        }
        return out
    }

    private func apiEchoBox(uuid: UUID) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("GET /api/records/\(uuid.uuidString.lowercased())")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
            Text("→ returns this record's detail as JSON")
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.dim)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.tokens.surface2)
        .overlay(
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .strokeBorder(theme.tokens.border, lineWidth: 1)
        )
        .padding(.top, 16)
    }
}
