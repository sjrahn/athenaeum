//
//  ContentView.swift
//  Athenaeum
//

import SwiftUI
import AthenaeumKit

/// Main browse window. Sidebar (200pt) + content column = toolbar over a
/// horizontally split list / detail pair, capped by a 22pt StatusBar.
struct ContentView: View {
    @Environment(\.theme) private var theme
    @Environment(BrowseStore.self) private var store
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        HStack(spacing: 0) {
            Sidebar()
            VHairline()
            mainColumn
        }
        .frame(minWidth: 960, minHeight: 600)
        .background(theme.tokens.bg)
        .onAppear {
            OpenSubmitWindow.handler = { openWindow(id: "submit") }
        }
    }

    private var mainColumn: some View {
        VStack(spacing: 0) {
            MacToolbar()
            Hairline()
            errorBannerIfNeeded
            body_
            Hairline()
            StatusBar()
        }
    }

    @ViewBuilder
    private var errorBannerIfNeeded: some View {
        if let err = store.records.error {
            ErrorBanner(error: err) { store.reloadRecords() }
        } else if let err = store.corpora.error {
            ErrorBanner(error: err) { store.loadCorpora() }
        }
    }

    @ViewBuilder
    private var body_: some View {
        HSplitView {
            listPane
                .frame(minWidth: 360, idealWidth: 520)
            DocPreview()
                .frame(minWidth: 360, idealWidth: 560)
        }
    }

    @ViewBuilder
    private var listPane: some View {
        switch store.listVariant {
        case .columns: ColumnView()
        case .table: RecordsTableView()
        case .gallery: GalleryView()
        case .cards: CardFeed()
        }
    }
}
