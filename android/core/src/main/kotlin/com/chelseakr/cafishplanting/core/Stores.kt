package com.chelseakr.cafishplanting.core

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import java.io.IOException
import java.time.Instant

/** Where the app keeps its few files. The names match the iOS app's. */
class AppStorageLayout(val directory: File) {
    val snapshotFile: File get() = File(directory, "snapshot.json")
    val snapshotMetaFile: File get() = File(directory, "snapshot.meta.json")

    // On-disk name kept from the iOS app: never rename it.
    val favoritesFile: File get() = File(directory, "favourites.json")
    val alertStateFile: File get() = File(directory, "alert-state.json")
    val entitlementFile: File get() = File(directory, "entitlement.json")
    val mutedWatersFile: File get() = File(directory, "muted-alerts.json")
    val onboardingFile: File get() = File(directory, "onboarding.json")
    val reviewPromptFile: File get() = File(directory, "review-prompt.json")
    val widgetDigestFile: File get() = File(directory, "widget-digest.json")

    fun ensureDirectory() {
        if (!directory.isDirectory && !directory.mkdirs()) throw IOException("could not create $directory")
    }
}

internal val storeJson = Json {
    ignoreUnknownKeys = true
    prettyPrint = true
    encodeDefaults = true
}

/** `java.time.Instant` as its ISO 8601 string. */
object InstantSerializer : KSerializer<Instant> {
    override val descriptor = kotlinx.serialization.descriptors.PrimitiveSerialDescriptor(
        "Instant",
        kotlinx.serialization.descriptors.PrimitiveKind.STRING,
    )
    override fun serialize(encoder: kotlinx.serialization.encoding.Encoder, value: Instant) = encoder.encodeString(value.toString())
    override fun deserialize(decoder: kotlinx.serialization.encoding.Decoder): Instant = Instant.parse(decoder.decodeString())
}

/**
 * One JSON file, written atomically (a temporary file, then a rename).
 * [load] returns `null` for a missing file and throws for a corrupt one, so
 * the caller decides what absence means.
 */
class JsonFileStore<T>(val file: File, private val serializer: KSerializer<T>) {
    fun load(): T? {
        if (!file.exists()) return null
        return storeJson.decodeFromString(serializer, file.readText())
    }

    /** `null` for a missing or corrupt file. */
    fun loadOrNull(): T? = try {
        load()
    } catch (_: Exception) {
        null
    }

    fun save(value: T) {
        file.parentFile?.mkdirs()
        val temp = File(file.parentFile, ".${file.name}.tmp")
        temp.writeText(storeJson.encodeToString(serializer, value))
        if (!temp.renameTo(file)) {
            file.delete()
            if (!temp.renameTo(file)) throw IOException("could not write $file")
        }
    }
}

/** Ordered, unique. The order is the order the person favorited in. */
@Serializable
data class Favorites(val ids: List<String> = emptyList()) {
    fun contains(id: String): Boolean = id in ids

    /** The list with [id] added or removed, and whether it is now a favorite. */
    fun toggled(id: String): Pair<Favorites, Boolean> =
        if (contains(id)) Favorites(ids - id) to false else Favorites(ids + id) to true

    fun removing(id: String): Favorites = Favorites(ids - id)

    val isEmpty: Boolean get() = ids.isEmpty()

    companion object {
        fun of(ids: List<String>): Favorites = Favorites(ids.distinct())
    }
}

/**
 * The one-time purchase's cached state. Google Play is always the source of
 * truth; this only avoids a locked-looking flash at launch. A missing or
 * corrupt file reads as "not purchased", never as "purchased".
 */
@Serializable
data class PurchaseEntitlement(
    /** California full access; kept for the single-product case and older files. */
    val isPurchased: Boolean = false,
    /** Every one-time product owned, by Play product ID. */
    val ownedProducts: Set<String> = emptySet(),
) {
    val entitlements: Entitlements
        get() = Entitlements(if (isPurchased) ownedProducts + ProductCatalog.CALIFORNIA_FULL_ACCESS else ownedProducts)

    companion object {
        fun of(entitlements: Entitlements) =
            PurchaseEntitlement(entitlements.californiaFullAccess, entitlements.ownedProducts)
    }
}

/** The stores the app keeps, each reading a missing or corrupt file as its empty value. */
class Stores(val layout: AppStorageLayout) {
    private val favorites = JsonFileStore(layout.favoritesFile, Favorites.serializer())
    private val alertState = JsonFileStore(layout.alertStateFile, AlertState.serializer())
    private val muted = JsonFileStore(layout.mutedWatersFile, MutedWaters.serializer())
    private val onboarding = JsonFileStore(layout.onboardingFile, OnboardingState.serializer())
    private val entitlement = JsonFileStore(layout.entitlementFile, PurchaseEntitlement.serializer())
    private val reviewPrompt = JsonFileStore(layout.reviewPromptFile, ReviewPromptState.serializer())

    fun loadFavorites(): Favorites = favorites.loadOrNull()?.let { Favorites.of(it.ids) } ?: Favorites()
    fun saveFavorites(value: Favorites) = favorites.save(value)

    fun loadAlertState(): AlertState = alertState.loadOrNull() ?: AlertState()
    fun saveAlertState(value: AlertState) = alertState.save(value)

    /** A disk problem can only turn alerts back on, never silence a water. */
    fun loadMuted(): MutedWaters = muted.loadOrNull() ?: MutedWaters()
    fun saveMuted(value: MutedWaters) = muted.save(value)

    fun loadOnboarding(): OnboardingState = onboarding.loadOrNull() ?: OnboardingState()
    fun saveOnboarding(value: OnboardingState) = onboarding.save(value)

    fun loadEntitlement(): PurchaseEntitlement = entitlement.loadOrNull() ?: PurchaseEntitlement()
    fun saveEntitlement(value: PurchaseEntitlement) = entitlement.save(value)

    fun loadReviewPrompt(): ReviewPromptState = reviewPrompt.loadOrNull() ?: ReviewPromptState()
    fun saveReviewPrompt(value: ReviewPromptState) = reviewPrompt.save(value)
}
