//
//  ContentView.swift
//  Athenaeum
//

import SwiftUI
import AthenaeumKit

/// Placeholder landing view. Exercises every design-system primitive so Phase
/// 2 can swap this out for the real browse UI with confidence the tokens
/// render correctly across themes + densities.
struct ContentView: View {
    @Environment(\.theme) private var theme
    @Environment(\.density) private var density

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                Hairline()
                typographySection
                Hairline()
                colorSection
                Hairline()
                pillSection
                Hairline()
                chipSection
                Hairline()
                buttonSection
                Hairline()
                kbdSection
            }
            .padding(density.padX * 2)
        }
        .background(theme.tokens.bg)
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: density.gap * 2) {
            Text("athenaeum")
                .font(.athenaeum(.sans, size: 22, weight: .bold))
                .foregroundStyle(theme.tokens.text)
            Text("· design system · v\(AthenaeumKit.schemaVersion)")
                .font(.athenaeum(.mono, size: 11))
                .foregroundStyle(theme.tokens.muted)
        }
    }

    private var typographySection: some View {
        sectionBox("typography") {
            VStack(alignment: .leading, spacing: density.gap) {
                Text("IBM Plex Sans — record titles & body prose")
                    .font(.athenaeum(.sans, size: 13, weight: .semibold))
                    .foregroundStyle(theme.tokens.text)
                Text("The quick brown fox jumps over the lazy dog. 0123456789")
                    .font(.athenaeum(.sans, size: 13))
                    .foregroundStyle(theme.tokens.text)
                Text("JetBrains Mono — UI chrome, metadata, kbd hints")
                    .font(.athenaeum(.mono, size: 11, weight: .semibold))
                    .foregroundStyle(theme.tokens.text)
                Text("GET /api/records/01JGX2M0YP6T7QNVR4B3W9KFZA")
                    .font(.athenaeum(.mono, size: 11))
                    .foregroundStyle(theme.tokens.muted)
            }
        }
    }

    private var colorSection: some View {
        sectionBox("color tokens") {
            let t = theme.tokens
            let swatches: [(String, Color)] = [
                ("bg", t.bg), ("surface", t.surface), ("surface2", t.surface2),
                ("border", t.border), ("text", t.text), ("muted", t.muted),
                ("dim", t.dim), ("accent", t.accent), ("accentSoft", t.accentSoft),
                ("ok", t.ok), ("warn", t.warn), ("err", t.err),
            ]
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: density.gap), count: 3), spacing: density.gap) {
                ForEach(swatches, id: \.0) { name, color in
                    HStack(spacing: density.gap) {
                        SmallSq(color)
                        Text(name)
                            .font(.athenaeum(.mono, size: 10))
                            .foregroundStyle(t.muted)
                    }
                }
            }
        }
    }

    private var pillSection: some View {
        sectionBox("pills") {
            HStack(spacing: density.gap) {
                Pill("public")
                Pill("7136")
                PillAccent("active")
                PillAccent("primary")
            }
        }
    }

    private var chipSection: some View {
        sectionBox("kind + mime chips") {
            VStack(alignment: .leading, spacing: density.gap) {
                HStack(spacing: density.gap) {
                    KindChip(.source)
                    KindChip(.document)
                }
                HStack(spacing: density.gap) {
                    MimeChip(mime: "application/pdf")
                    MimeChip(mime: "video/mp4")
                    MimeChip(mime: "text/html")
                    MimeChip(mime: "image/png")
                    MimeChip(mime: "text/markdown")
                    MimeChip(mime: "application/json")
                    MimeChip(mime: "text/vtt")
                    MimeChip(mime: "message/rfc822")
                    MimeChip(mime: "audio/mpeg")
                }
            }
        }
    }

    private var buttonSection: some View {
        sectionBox("buttons") {
            HStack(spacing: density.gap) {
                Btn("filter") {}
                Btn("+ submit", variant: .primary) {}
                Btn("reset", variant: .ghost) {}
            }
        }
    }

    private var kbdSection: some View {
        sectionBox("kbd hints") {
            HStack(spacing: density.gap) {
                Kbd("⌘F")
                Kbd("⌘1")
                Kbd("⇧⌘Y")
                Kbd("[")
                Kbd("]")
            }
        }
    }

    private func sectionBox<C: View>(_ title: String, @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: density.gap) {
            Text(title.uppercased())
                .font(.athenaeum(.mono, size: 9, weight: .semibold))
                .tracking(0.8)
                .foregroundStyle(theme.tokens.dim)
            content()
        }
    }
}

#Preview("Light / Dense") {
    ContentView()
        .athenaeumPreview(mode: .light, density: .dense)
}

#Preview("Dark / Comfy") {
    ContentView()
        .athenaeumPreview(mode: .dark, density: .comfy)
}

extension View {
    fileprivate func athenaeumPreview(mode: ThemeMode, density: Density) -> some View {
        AthenaeumFonts.registerBundledFonts()
        let theme = Theme.resolve(mode: mode, colorScheme: mode == .dark ? .dark : .light)
        return self
            .theme(theme)
            .density(density)
            .frame(width: 520, height: 680)
            .background(theme.tokens.bg)
    }
}
