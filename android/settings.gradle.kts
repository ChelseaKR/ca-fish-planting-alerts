// Trout Truck for Android. Two modules:
//
// - core: plain Kotlin (JVM), no Android. The data layer, the same rules as
//   ios/PlantingCore: the strict snapshot decoder, the alert planner, the
//   on-disk stores, freshness, search and the words the app shows. Its unit
//   tests run on the JVM with no emulator, and the alert planner is held to
//   the same shared fixtures as the Swift package
//   (ios/PlantingCore/Tests/PlantingCoreTests/Fixtures/alert-planner-parity.json).
// - app: the Jetpack Compose app, the WorkManager refresh, notifications,
//   Play Billing, the Glance widget and the in-app review prompt.
pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "TroutTruck"
include(":core", ":app")
