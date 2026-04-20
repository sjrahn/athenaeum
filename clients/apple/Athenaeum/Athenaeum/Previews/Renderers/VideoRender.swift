import SwiftUI
import AVKit
import AthenaeumKit

/// Video playback via SwiftUI's `VideoPlayer` over `AVPlayer`. AVPlayer does
/// byte-range streaming automatically, so scrubbing to minute 40 of a long
/// video doesn't re-download from the start.
struct VideoRender: View {
    @Environment(\.theme) private var theme
    let artifact: ArtifactRef
    let url: URL

    @State private var player: AVPlayer?

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                Color.black
                if let player {
                    VideoPlayer(player: player)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            RendererFooter(
                filename: ArtifactRefHelpers.filename(from: artifact.ref),
                detail: artifact.mimetype ?? "video/mp4",
                fileURL: url
            )
        }
        .onAppear {
            if player == nil {
                player = AVPlayer(url: url)
            }
        }
        .onDisappear {
            player?.pause()
        }
        .onChange(of: url) { _, newURL in
            player?.pause()
            player = AVPlayer(url: newURL)
        }
    }
}
