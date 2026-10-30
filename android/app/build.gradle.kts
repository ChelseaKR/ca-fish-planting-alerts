import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

// The snapshot the app ships with is a committed v2 snapshot (every state) in
// src/main/assets/snapshot.json, refreshed by scripts/sync-bundled-snapshot.sh.

android {
    namespace = "com.chelseakr.cafishplanting"
    compileSdk = 36

    defaultConfig {
        // The iOS bundle identifier's stem (docs/DECISIONS.md 0010).
        applicationId = "com.chelseakr.cafishplanting"
        minSdk = 26
        targetSdk = 36
        // Play rejects an upload whose versionCode is not above every earlier
        // upload's, so the release workflow passes ANDROID_VERSION_CODE (and
        // ANDROID_VERSION_NAME, which follows CHANGELOG's SemVer like the iOS
        // MARKETING_VERSION). Unset, as in CI and local builds, these are the
        // values below. A bump is still a reviewed edit here.
        versionCode = System.getenv("ANDROID_VERSION_CODE")?.toIntOrNull() ?: 1
        versionName = System.getenv("ANDROID_VERSION_NAME")?.takeIf { it.isNotBlank() } ?: "1.0.0"
    }

    // Upload-key signing, applied when the release workflow (or the owner's shell)
    // sets all four values. With any of them unset nothing is configured and
    // the release build stays unsigned, exactly as CI's assembleRelease expects.
    // Nothing here is ever printed or written to the repository.
    val uploadKeystore = System.getenv("ANDROID_UPLOAD_KEYSTORE_FILE")?.takeIf { it.isNotBlank() }
    val uploadStorePassword = System.getenv("ANDROID_UPLOAD_KEYSTORE_PASSWORD")?.takeIf { it.isNotEmpty() }
    val uploadKeyAlias = System.getenv("ANDROID_UPLOAD_KEY_ALIAS")?.takeIf { it.isNotBlank() }
    val uploadKeyPassword = System.getenv("ANDROID_UPLOAD_KEY_PASSWORD")?.takeIf { it.isNotEmpty() }
    val hasUploadKey = uploadKeystore != null && uploadStorePassword != null &&
        uploadKeyAlias != null && uploadKeyPassword != null
    if (hasUploadKey) {
        signingConfigs {
            create("upload") {
                storeFile = file(uploadKeystore!!)
                storePassword = uploadStorePassword
                keyAlias = uploadKeyAlias
                keyPassword = uploadKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // Signing is the owner's (android/README.md, docs/ANDROID-RELEASE.md):
            // Play App Signing holds the app key; the upload key never enters
            // the repo and signs when the environment supplies it.
            if (hasUploadKey) signingConfig = signingConfigs.getByName("upload")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    lint {
        abortOnError = true
        warningsAsErrors = true
        checkDependencies = true
        // Renovate proposes version bumps (renovate.json); lint's own
        // "a newer version exists" checks would fail builds on a calendar.
        disable += setOf("GradleDependency", "NewerVersionAvailable", "AndroidGradlePluginVersion", "OldTargetApi")
        xmlReport = true
        htmlReport = true
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}", "DebugProbesKt.bin")
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
        allWarningsAsErrors.set(true)
    }
}

dependencies {
    implementation(project(":core"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.foundation)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.extended)
    implementation(libs.androidx.compose.material3.navigation.suite)
    implementation(libs.androidx.adaptive)
    implementation(libs.androidx.adaptive.layout)
    implementation(libs.androidx.adaptive.navigation)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.process)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.glance.appwidget)
    implementation(libs.androidx.glance.material3)
    implementation(libs.billing.ktx)
    implementation(libs.play.review.ktx)
    implementation(libs.kotlinx.serialization.json)
    debugImplementation(libs.androidx.compose.ui.tooling)
    testImplementation(libs.junit)
}

// SnapshotLoaderTest opens the real bundled snapshot, so a new one reruns it.
tasks.withType<Test>().configureEach {
    inputs.file(layout.projectDirectory.file("src/main/assets/snapshot.json"))
}
