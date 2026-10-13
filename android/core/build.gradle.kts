import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// Plain Kotlin, no Android: the same rules as ios/PlantingCore, tested on
// the JVM. Foundation-only there, kotlinx-serialization-only here.
plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
        allWarningsAsErrors.set(true)
    }
}

dependencies {
    implementation(libs.kotlinx.serialization.json)
    testImplementation(libs.junit)
}

tasks.test {
    // The parity tests read the Swift package's fixtures, so both planners
    // are held to the same files; the decoder test reads the app's bundled
    // v1 snapshot. Both come from the repository itself.
    systemProperty("repoRoot", rootProject.projectDir.parentFile.absolutePath)
    inputs.dir(rootProject.projectDir.parentFile.resolve("ios/PlantingCore/Tests/PlantingCoreTests/Fixtures"))
    inputs.file(rootProject.projectDir.resolve("app/src/main/assets/snapshot.json"))
    testLogging {
        events("failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
