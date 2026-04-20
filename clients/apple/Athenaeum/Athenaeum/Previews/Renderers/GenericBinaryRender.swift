import SwiftUI
import AthenaeumKit

/// Fallback renderer for unknown mimes. No attempt to preview — shows the
/// bare metadata and an action bar driving the external open / quick-look
/// fallback paths.
struct GenericBinaryRender: View {
    @Environment(\.theme) private var theme
    let artifact: ArtifactRef
    let url: URL

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                theme.tokens.bg
                VStack(spacing: 10) {
                    Image(systemName: "doc")
                        .font(.system(size: 36))
                        .foregroundStyle(theme.tokens.dim)
                    Text("binary artifact")
                        .font(.athenaeum(.mono, size: 10))
                        .foregroundStyle(theme.tokens.dim)
                    Text(ArtifactRefHelpers.filename(from: artifact.ref))
                        .font(.athenaeum(.mono, size: 11, weight: .semibold))
                        .foregroundStyle(theme.tokens.text)
                    Text("\(artifact.mimetype ?? "application/octet-stream")")
                        .font(.athenaeum(.mono, size: 10))
                        .foregroundStyle(theme.tokens.muted)
                }
                .padding(24)
                .frame(maxWidth: 320)
                .background(
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .fill(theme.tokens.surface)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .strokeBorder(theme.tokens.border, lineWidth: 1)
                )
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            RendererFooter(
                filename: ArtifactRefHelpers.filename(from: artifact.ref),
                detail: artifact.mimetype ?? "application/octet-stream",
                fileURL: url
            )
        }
    }
}
