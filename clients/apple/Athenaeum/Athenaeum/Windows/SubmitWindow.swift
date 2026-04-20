import SwiftUI
import AthenaeumKit
import UniformTypeIdentifiers

/// 520×460 dedicated submit window. Pre-selects the current corpus, accepts
/// file drops, and POSTs via `AthenaeumKit.Multipart`. Phase 2 landing is a
/// functional form; Phase 6 can polish drag affordances, tag autocomplete,
/// and keyboard shortcut handling.
struct SubmitWindow: View {
    @Environment(\.theme) private var theme
    @Environment(PreferencesStore.self) private var preferences
    @Environment(\.dismissWindow) private var dismissWindow

    @State private var corpus: String = "corpus-public"
    @State private var title: String = ""
    @State private var description: String = ""
    @State private var urlText: String = ""
    @State private var tagDraft: String = ""
    @State private var tags: [String] = []
    @State private var droppedFiles: [URL] = []
    @State private var submitting: Bool = false
    @State private var resultMessage: String?
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            dropZone
            titleField
            descriptionField
            urlField
            tagsRow
            Spacer(minLength: 0)
            footer
            if let resultMessage {
                Text(resultMessage)
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.ok)
            }
            if let errorMessage {
                Text(errorMessage)
                    .font(.athenaeum(.mono, size: 10))
                    .foregroundStyle(theme.tokens.err)
            }
        }
        .padding(16)
        .frame(width: 520, height: 460)
        .background(theme.tokens.bg)
        .onAppear {
            corpus = preferences.lastUsedCorpus ?? "corpus-public"
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("submit to")
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.muted)
            PillAccent(corpus.replacingOccurrences(of: "corpus-", with: ""))
            Spacer(minLength: 0)
        }
    }

    private var dropZone: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .strokeBorder(
                    style: StrokeStyle(lineWidth: 1, dash: [4, 4])
                )
                .foregroundStyle(theme.tokens.accent)
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(theme.tokens.accentSoft.opacity(0.6))
            VStack(spacing: 6) {
                Image(systemName: "tray.and.arrow.down")
                    .font(.system(size: 26))
                    .foregroundStyle(theme.tokens.accent)
                if droppedFiles.isEmpty {
                    Text("drop files here")
                        .font(.athenaeum(.mono, size: 11, weight: .semibold))
                        .foregroundStyle(theme.tokens.accent)
                } else {
                    VStack(spacing: 2) {
                        ForEach(droppedFiles, id: \.self) { url in
                            Text(url.lastPathComponent)
                                .font(.athenaeum(.mono, size: 10))
                                .foregroundStyle(theme.tokens.text)
                                .lineLimit(1)
                        }
                    }
                }
            }
        }
        .frame(height: 120)
        .onDrop(of: [.fileURL], isTargeted: nil) { providers in
            handleDrop(providers: providers)
        }
    }

    private var titleField: some View {
        labeled("title") {
            TextField("", text: $title)
                .textFieldStyle(.plain)
                .padding(.horizontal, 8)
                .frame(height: 24)
                .background(theme.tokens.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .strokeBorder(theme.tokens.border, lineWidth: 1)
                )
        }
    }

    private var descriptionField: some View {
        labeled("description") {
            TextField("", text: $description, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(2...3)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(theme.tokens.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .strokeBorder(theme.tokens.border, lineWidth: 1)
                )
        }
    }

    private var urlField: some View {
        labeled("url") {
            TextField("https://…", text: $urlText)
                .textFieldStyle(.plain)
                .padding(.horizontal, 8)
                .frame(height: 24)
                .background(theme.tokens.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: 2, style: .continuous)
                        .strokeBorder(theme.tokens.border, lineWidth: 1)
                )
        }
    }

    private var tagsRow: some View {
        labeled("tags") {
            HStack(spacing: 6) {
                ForEach(tags, id: \.self) { tag in
                    Button {
                        tags.removeAll { $0 == tag }
                    } label: {
                        HStack(spacing: 4) {
                            Text("#\(tag)")
                            Text("×")
                        }
                        .font(.athenaeum(.mono, size: 10))
                        .foregroundStyle(theme.tokens.accent)
                        .padding(.horizontal, 6)
                        .frame(height: 18)
                        .background(
                            RoundedRectangle(cornerRadius: 2, style: .continuous)
                                .fill(theme.tokens.accentSoft)
                        )
                    }
                    .buttonStyle(.plain)
                }
                TextField("add tag", text: $tagDraft)
                    .textFieldStyle(.plain)
                    .onSubmit {
                        let trimmed = tagDraft.trimmingCharacters(in: .whitespaces)
                        if !trimmed.isEmpty { tags.append(trimmed) }
                        tagDraft = ""
                    }
                    .padding(.horizontal, 6)
                    .frame(height: 18)
                    .background(theme.tokens.surface)
                    .overlay(
                        RoundedRectangle(cornerRadius: 2, style: .continuous)
                            .strokeBorder(theme.tokens.border, lineWidth: 1)
                    )
                    .frame(width: 120)
            }
        }
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Spacer(minLength: 0)
            Btn("cancel", variant: .ghost) { dismissWindow() }
            Btn(.primary, action: submit) {
                HStack(spacing: 4) {
                    Text(submitting ? "submitting…" : "submit")
                    if !submitting { Kbd("⌘↵") }
                }
            }
            .disabled(submitting || !canSubmit)
            .keyboardShortcut(.return, modifiers: [.command])
        }
    }

    private var canSubmit: Bool {
        !title.trimmingCharacters(in: .whitespaces).isEmpty
            || !droppedFiles.isEmpty
            || !urlText.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private func labeled<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(.athenaeum(.mono, size: 9, weight: .semibold))
                .tracking(0.8)
                .foregroundStyle(theme.tokens.dim)
            content()
        }
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                guard let url else { return }
                Task { @MainActor in
                    if !droppedFiles.contains(url) {
                        droppedFiles.append(url)
                    }
                }
            }
        }
        return true
    }

    private func submit() {
        guard canSubmit else { return }
        submitting = true
        errorMessage = nil
        resultMessage = nil

        let effectiveTitle = title.trimmingCharacters(in: .whitespaces).isEmpty
            ? (droppedFiles.first?.lastPathComponent ?? "submission")
            : title.trimmingCharacters(in: .whitespaces)

        let fileParts: [Multipart.FilePart] = droppedFiles.map { url in
            Multipart.FilePart(
                name: "file",
                filename: url.lastPathComponent,
                contentType: UTType(filenameExtension: url.pathExtension)?.preferredMIMEType
                    ?? "application/octet-stream",
                fileURL: url
            )
        }

        let descParam = description.isEmpty ? nil : description
        let urlParam = urlText.isEmpty ? nil : urlText
        let corpusParam = corpus

        Task { @MainActor in
            do {
                let client = APIClient(config: Config())
                let response = try await client.submit(
                    corpus: corpusParam,
                    title: effectiveTitle,
                    description: descParam,
                    url: urlParam,
                    sourceType: nil,
                    files: fileParts
                )
                resultMessage = "submitted → \(response.folder) (\(response.fileCount) files)"
                droppedFiles.removeAll()
                title = ""
                description = ""
                urlText = ""
                tags.removeAll()
            } catch let error as APIError {
                errorMessage = error.localizedDescription
            } catch {
                errorMessage = String(describing: error)
            }
            submitting = false
        }
    }
}
