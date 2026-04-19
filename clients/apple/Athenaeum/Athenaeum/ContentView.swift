//
//  ContentView.swift
//  Athenaeum
//
//  Created by Steven Rahn on 2026-04-19.
//

import SwiftUI
import AthenaeumKit

struct ContentView: View {
    var body: some View {
        VStack {
            Image(systemName: "globe")
                .imageScale(.large)
                .foregroundStyle(.tint)
            Text("Hello, world!")
            Text(AthenaeumKit.version)
        }
        .padding()
    }
}

#Preview {
    ContentView()
}
