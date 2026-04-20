// swift-tools-version: 6.3

import PackageDescription

let package = Package(
    name: "AthenaeumKit",
    platforms: [
        .macOS(.v26),
        .iOS(.v26),
    ],
    products: [
        .library(
            name: "AthenaeumKit",
            targets: ["AthenaeumKit"]
        ),
    ],
    targets: [
        .target(
            name: "AthenaeumKit",
            resources: [.copy("Fonts")]
        ),
        .testTarget(
            name: "AthenaeumKitTests",
            dependencies: ["AthenaeumKit"],
            resources: [.copy("Fixtures")]
        ),
    ],
    swiftLanguageModes: [.v6]
)
