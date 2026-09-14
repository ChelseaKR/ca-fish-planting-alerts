// swift-tools-version: 5.10
// PlantingCore: the app's data layer. Foundation only. Builds and tests on
// macOS (`swift test`, no simulator needed) and on iOS. No third-party
// dependencies — that is the product.
//
// `type: .dynamic`, not `.static`: the app target's unit tests run *hosted*
// inside the app (TEST_HOST/BUNDLE_LOADER, so `@testable import
// CAFishPlanting` and `Bundle.main` resolve to the real app). A static
// PlantingCore linked into both the app and the hosted test bundle fails at
// link time ("linked as a static library by 'CAFishPlantingTests' and
// 'CAFishPlanting'. This will result in duplication of library code" —
// measured via `xcodebuild build`, not theoretical). A dynamic library is
// linked once and shared. queer-tv-guide/ios/GuideCore currently declares
// `type: .static` with the same hosted-test shape; it will hit this same
// error once its Xcode project links a test target — worth fixing there too.
import PackageDescription

let package = Package(
    name: "PlantingCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "PlantingCore", type: .dynamic, targets: ["PlantingCore"]),
    ],
    targets: [
        .target(
            name: "PlantingCore",
            path: "Sources/PlantingCore"
        ),
        .testTarget(
            name: "PlantingCoreTests",
            dependencies: ["PlantingCore"],
            path: "Tests/PlantingCoreTests"
        ),
    ]
)
