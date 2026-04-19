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
            name: "AthenaeumKit"
        ),
        .testTarget(
            name: "AthenaeumKitTests",
            dependencies: ["AthenaeumKit"]
        ),
    ],
    swiftLanguageModes: [.v6]
)
