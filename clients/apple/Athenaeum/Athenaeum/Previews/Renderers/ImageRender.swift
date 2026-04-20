import SwiftUI
import AthenaeumKit

/// Image artifact renderer. Uses `AsyncImage` for URL-based loading with a
/// neutral dark backdrop so colour images don't fight the surface tokens.
/// Multi-image records rely on the caller (`OriginalView`) advancing the
/// `ArtifactSwitcher` — we only render the single selected artifact.
struct ImageRender: View {
    @Environment(\.theme) private var theme
    let artifact: ArtifactRef
    let url: URL

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                Color(hex: "#151310")
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .empty:
                        ProgressView().controlSize(.small)
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFit()
                            .padding(24)
                    case .failure:
                        RendererErrorView(message: "image failed to load")
                    @unknown default:
                        EmptyView()
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            RendererFooter(
                filename: ArtifactRefHelpers.filename(from: artifact.ref),
                detail: artifact.mimetype ?? "image/*",
                fileURL: url
            )
        }
    }
}
