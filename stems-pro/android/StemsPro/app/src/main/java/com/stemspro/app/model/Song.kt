package com.stemspro.app.model

/** Domain model for a song with its separated tracks. */
data class Song(
    val id: Int = 0,
    val title: String,
    val artist: String = "",
    val coverUrl: String = "",
    val createdAt: String = "",
    val updatedAt: String = "",
    val bpm: Float = 0f,
    val tracks: List<Track> = emptyList(),
)

/** Domain model for a single audio track within a song. */
data class Track(
    val id: Int = 0,
    val songId: Int = 0,
    val name: String,       // vocals, drums, bass, guitar, piano, other
    val filePath: String = "",
    val fileSize: Long = 0,
    val duration: Float = 0f,
    val downloadUrl: String = "",
) {
    companion object {
        val NAMES = listOf("vocals", "drums", "bass", "guitar", "piano", "other")
        val LABELS = mapOf(
            "vocals" to "人声",
            "drums" to "鼓组",
            "bass" to "贝斯",
            "guitar" to "吉他",
            "piano" to "钢琴",
            "other" to "其他",
        )
        val COLORS = mapOf(
            "vocals" to 0xFF6C5CE7,
            "drums" to 0xFFE74C3C,
            "bass" to 0xFF2ECC71,
            "guitar" to 0xFFF1C40F,
            "piano" to 0xFF3498DB,
            "other" to 0xFF95A5A6,
        )
    }

    fun displayName(): String = LABELS[name] ?: name
    fun colorLong(): Long = COLORS[name] ?: 0xFF888888
}

/** Download state for a track. */
enum class DownloadState {
    NOT_DOWNLOADED,
    DOWNLOADING,
    DOWNLOADED,
    FAILED,
}

/** Local track info stored in Room. */
data class LocalTrack(
    val trackId: Int,
    val songId: Int,
    val name: String,
    val localPath: String,
    val downloadState: DownloadState = DownloadState.NOT_DOWNLOADED,
)
