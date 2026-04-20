import SwiftUI
import AthenaeumKit

/// Gallery grid with per-MIME abstract thumbnails (no real image fetch until
/// Phase 3). Each card: 180pt min, 96pt thumb, title (2-line clamp), origin
/// placeholder (1-line clamp).
struct GalleryView: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density
    @Environment(BrowseStore.self) private var store

    private let columns = [GridItem(.adaptive(minimum: 180), spacing: 12)]

    var body: some View {
        ZStack {
            theme.tokens.bg.ignoresSafeArea()
            content
        }
    }

    @ViewBuilder
    private var content: some View {
        if let result = store.records.value {
            if result.records.isEmpty {
                empty
            } else {
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(result.records) { card(for: $0) }
                    }
                    .padding(12)
                }
            }
        } else if store.records.isLoading {
            ProgressView().controlSize(.small)
        }
    }

    private func card(for record: RecordSummary) -> some View {
        let selected = store.selectedRecordID == record.uuid
        return Button {
            store.select(record.uuid)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                Thumb(
                    mime: record.contentType,
                    imageURL: imageURL(for: record)
                )
                .frame(height: 96)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 4) {
                        KindChip(recordType: RecordType(rawValue: record.recordType) ?? .source)
                        MimeChip(mime: record.contentType)
                    }
                    Text(record.title.isEmpty ? "(untitled)" : record.title)
                        .font(.athenaeum(.sans, size: 11, weight: .semibold))
                        .foregroundStyle(theme.tokens.text)
                        .lineLimit(2)
                    Text(record.tags.prefix(3).joined(separator: " · "))
                        .font(.athenaeum(.mono, size: 9))
                        .foregroundStyle(theme.tokens.dim)
                        .lineLimit(1)
                }
                .padding(8)
            }
            .background(theme.tokens.surface)
            .overlay(
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .strokeBorder(selected ? theme.tokens.accent : theme.tokens.border, lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var empty: some View {
        Text("no records match the current filters")
            .font(.athenaeum(.mono, size: 11))
            .foregroundStyle(theme.tokens.muted)
    }

    /// Build a thumbnail URL when the record's primary artifact is an
    /// image. For non-image primary artifacts (PDF first-page render, video
    /// poster) we could do more — deferred to a thumbnailer in Phase 6.
    private func imageURL(for record: RecordSummary) -> URL? {
        let mime = (record.primaryArtifactMimetype ?? record.contentType).lowercased()
        guard mime.hasPrefix("image/") else { return nil }
        return store.thumbnailURL(for: record)
    }
}

/// Per-MIME thumbnail. Image-primary records render the actual image via
/// `AsyncImage`; other MIMEs fall back to abstract SwiftUI-shape stand-ins
/// that Phase 6 can upgrade (PDF first-page render, video poster frames).
private struct Thumb: View {
    @Environment(\.theme) private var theme
    let mime: String
    let imageURL: URL?

    var body: some View {
        let key = MimeChip.shortKey(for: mime)
        GeometryReader { _ in
            if let imageURL {
                imageCard(url: imageURL)
            } else {
                switch key {
                case "pdf": pdfThumb
                case "mp4": videoThumb
                case "mp3": audioThumb
                case "html": htmlThumb
                case "png", "jpg": imageThumb
                case "eml": emailThumb
                default: textThumb
                }
            }
        }
    }

    private func imageCard(url: URL) -> some View {
        ZStack {
            Color(hex: "#151310")
            AsyncImage(url: url) { phase in
                switch phase {
                case .empty:
                    ProgressView().controlSize(.small)
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                case .failure:
                    imageThumb // fall back to gradient if network/decoding fails
                @unknown default:
                    EmptyView()
                }
            }
        }
        .clipped()
    }

    private var pdfThumb: some View {
        ZStack {
            Rectangle().fill(Color.white)
            VStack(alignment: .leading, spacing: 4) {
                ForEach(0..<7, id: \.self) { _ in
                    Rectangle()
                        .fill(Color(hex: "#999999"))
                        .frame(height: 1)
                        .opacity(0.5)
                }
            }
            .padding(14)
        }
    }

    private var videoThumb: some View {
        ZStack {
            Rectangle().fill(Color(hex: "#0e0e0e"))
            Image(systemName: "play.fill")
                .foregroundStyle(Color.white.opacity(0.85))
                .font(.system(size: 22))
        }
    }

    private var audioThumb: some View {
        // Heights are a fixed pseudo-waveform so the thumb doesn't flicker
        // across re-renders; Phase 3 swaps in a real waveform computed from
        // the audio artifact.
        let heights: [CGFloat] = [
            14, 26, 38, 22, 46, 30, 18, 34, 44, 28, 12, 40,
            24, 36, 20, 32, 48, 26, 14, 30, 42, 22, 36, 18,
        ]
        return ZStack {
            Rectangle().fill(theme.tokens.surface2)
            HStack(spacing: 2) {
                ForEach(Array(heights.enumerated()), id: \.offset) { _, h in
                    Capsule()
                        .fill(theme.tokens.accent)
                        .frame(width: 2, height: h)
                }
            }
            .padding(.horizontal, 8)
        }
    }

    private var htmlThumb: some View {
        ZStack {
            Rectangle().fill(Color.white)
            VStack(alignment: .leading, spacing: 0) {
                Rectangle().fill(theme.tokens.surface2).frame(height: 14)
                Rectangle().fill(theme.tokens.border).frame(height: 1)
                Spacer()
            }
        }
    }

    private var imageThumb: some View {
        LinearGradient(
            colors: [Color(hex: "#d6a36b"), Color(hex: "#6b4a2a")],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var emailThumb: some View {
        ZStack {
            Rectangle().fill(Color.white)
            VStack(alignment: .leading, spacing: 3) {
                Rectangle()
                    .fill(theme.tokens.accent)
                    .frame(height: 2)
                ForEach(0..<5, id: \.self) { _ in
                    Rectangle()
                        .fill(Color(hex: "#aaaaaa"))
                        .frame(height: 1)
                        .opacity(0.6)
                }
            }
            .padding(14)
        }
    }

    private var textThumb: some View {
        ZStack {
            Rectangle().fill(theme.tokens.surface2)
            VStack(alignment: .leading, spacing: 4) {
                Text("# title")
                    .font(.athenaeum(.mono, size: 9, weight: .semibold))
                    .foregroundStyle(theme.tokens.text)
                Text("## section")
                    .font(.athenaeum(.mono, size: 9))
                    .foregroundStyle(theme.tokens.muted)
                Text("- item")
                    .font(.athenaeum(.mono, size: 9))
                    .foregroundStyle(theme.tokens.dim)
                Text("- item")
                    .font(.athenaeum(.mono, size: 9))
                    .foregroundStyle(theme.tokens.dim)
            }
            .padding(10)
        }
    }
}
