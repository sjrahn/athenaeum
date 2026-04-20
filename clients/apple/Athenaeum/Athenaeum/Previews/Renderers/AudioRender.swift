import SwiftUI
import AVFoundation
import AthenaeumKit

/// Audio playback with a stylised waveform. Real waveform extraction requires
/// decoding the audio file into PCM samples — we stub that with a
/// deterministic pseudo-waveform that matches the gallery thumbnail, plus a
/// live playback cursor overlay. Phase 6 can swap in a real analyser.
struct AudioRender: View {
    @Environment(\.theme) private var theme
    let artifact: ArtifactRef
    let url: URL

    @State private var player: AVPlayer?
    @State private var duration: Double = 0
    @State private var elapsed: Double = 0
    @State private var playing: Bool = false
    @State private var timeObserver: Any?

    // Stable pseudo-waveform sized for the preview pane.
    private let heights: [CGFloat] = [
        18, 32, 46, 28, 52, 38, 24, 44, 54, 36, 16, 50,
        30, 42, 26, 40, 58, 32, 18, 38, 50, 28, 44, 22,
        36, 50, 30, 42, 58, 34, 22, 46, 32, 54, 40, 26,
        48, 34, 20, 44, 52, 28, 38, 24, 50, 36, 42, 30,
    ]

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                theme.tokens.surface2
                VStack(spacing: 12) {
                    Spacer()
                    waveform
                        .frame(height: 80)
                    timeline
                    controls
                    Spacer()
                }
                .padding(24)
            }
            RendererFooter(
                filename: ArtifactRefHelpers.filename(from: artifact.ref),
                detail: artifact.mimetype ?? "audio/mpeg",
                fileURL: url
            )
        }
        .onAppear { setupPlayer() }
        .onDisappear { teardownPlayer() }
        .onChange(of: url) { _, _ in
            teardownPlayer()
            setupPlayer()
        }
    }

    private var progress: Double {
        guard duration > 0 else { return 0 }
        return min(1, max(0, elapsed / duration))
    }

    private var waveform: some View {
        GeometryReader { geo in
            let idx = Int(Double(heights.count) * progress)
            HStack(spacing: 2) {
                ForEach(Array(heights.enumerated()), id: \.offset) { i, h in
                    Capsule()
                        .fill(i < idx ? theme.tokens.accent : theme.tokens.borderStrong)
                        .frame(width: 2, height: h)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .center)
        }
    }

    private var timeline: some View {
        HStack(spacing: 8) {
            Text(timeString(elapsed))
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.muted)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(theme.tokens.border)
                        .frame(height: 2)
                    Rectangle()
                        .fill(theme.tokens.accent)
                        .frame(width: geo.size.width * progress, height: 2)
                }
                .frame(height: 2)
            }
            .frame(height: 2)
            Text(timeString(duration))
                .font(.athenaeum(.mono, size: 10))
                .foregroundStyle(theme.tokens.muted)
        }
    }

    private var controls: some View {
        HStack(spacing: 14) {
            Button {
                seek(by: -10)
            } label: {
                Image(systemName: "gobackward.10")
                    .font(.system(size: 16))
                    .foregroundStyle(theme.tokens.text)
            }
            .buttonStyle(.plain)

            Button {
                togglePlayback()
            } label: {
                Image(systemName: playing ? "pause.fill" : "play.fill")
                    .font(.system(size: 22))
                    .foregroundStyle(theme.tokens.accent)
                    .frame(width: 44, height: 44)
                    .background(
                        Circle().fill(theme.tokens.accentSoft)
                    )
            }
            .buttonStyle(.plain)

            Button {
                seek(by: 10)
            } label: {
                Image(systemName: "goforward.10")
                    .font(.system(size: 16))
                    .foregroundStyle(theme.tokens.text)
            }
            .buttonStyle(.plain)
        }
    }

    private func setupPlayer() {
        let player = AVPlayer(url: url)
        self.player = player

        let interval = CMTime(seconds: 0.25, preferredTimescale: 600)
        let observer = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { time in
            elapsed = CMTimeGetSeconds(time)
            if duration == 0, let item = player.currentItem {
                let secs = CMTimeGetSeconds(item.duration)
                if secs.isFinite, secs > 0 {
                    duration = secs
                }
            }
        }
        timeObserver = observer
    }

    private func teardownPlayer() {
        if let observer = timeObserver {
            player?.removeTimeObserver(observer)
            timeObserver = nil
        }
        player?.pause()
        player = nil
        duration = 0
        elapsed = 0
        playing = false
    }

    private func togglePlayback() {
        guard let player else { return }
        if playing {
            player.pause()
        } else {
            player.play()
        }
        playing.toggle()
    }

    private func seek(by delta: Double) {
        guard let player else { return }
        let target = max(0, min(duration, elapsed + delta))
        player.seek(to: CMTime(seconds: target, preferredTimescale: 600))
    }

    private func timeString(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds > 0 else { return "0:00" }
        let total = Int(seconds)
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        if h > 0 { return String(format: "%d:%02d:%02d", h, m, s) }
        return String(format: "%d:%02d", m, s)
    }
}
