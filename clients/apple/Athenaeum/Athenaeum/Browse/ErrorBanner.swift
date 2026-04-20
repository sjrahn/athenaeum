import SwiftUI
import AthenaeumKit

/// Single-line error banner above the record list. Renders when the store's
/// records / corpora fetch fails. `.notReachable` gets Tailscale-specific copy;
/// other errors surface `localizedDescription` verbatim.
struct ErrorBanner: View {
    @Environment(\.theme) private var theme
    let error: APIError
    let retry: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(theme.tokens.err)
                .font(.system(size: 11, weight: .semibold))
            Text(message)
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.text)
                .lineLimit(2)
            Spacer(minLength: 8)
            Btn("retry", action: retry)
        }
        .padding(.horizontal, 10)
        .frame(height: 32)
        .background(theme.tokens.accentSoft.opacity(0.6))
        .overlay(alignment: .bottom) { Hairline() }
    }

    private var message: String {
        switch error {
        case .notReachable:
            "Cannot reach server — is Tailscale connected?"
        default:
            error.localizedDescription
        }
    }
}
