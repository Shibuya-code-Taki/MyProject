package com.stemspro.app.data.repository

import android.content.Context
import com.stemspro.app.data.api.SongCreateRequest
import com.stemspro.app.data.api.SongDto
import com.stemspro.app.data.api.SongUpdateRequest
import com.stemspro.app.data.api.StemsApi
import com.stemspro.app.data.api.TrackDto
import com.stemspro.app.data.local.AppDatabase
import com.stemspro.app.data.local.CachedSong
import com.stemspro.app.data.local.CachedTrack
import com.stemspro.app.model.DownloadState
import com.stemspro.app.model.Song
import com.stemspro.app.model.Track
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.FileOutputStream

class SongRepository(
    private val api: StemsApi,
    private val db: AppDatabase,
    private val appContext: Context,
) {
    private val songDao = db.songDao()
    private val trackDao = db.trackDao()

    // ── Remote API ──

    suspend fun fetchSongs(page: Int = 1, search: String? = null): Result<List<Song>> = withContext(Dispatchers.IO) {
        try {
            val resp = api.listSongs(page = page, pageSize = 50, search = search)
            if (resp.code == 0 && resp.data != null) {
                val songs = resp.data.songs.map { it.toDomain() }
                Result.success(songs)
            } else {
                Result.failure(Exception(resp.message))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun createSong(title: String, artist: String): Result<Song> = withContext(Dispatchers.IO) {
        try {
            val resp = api.createSong(SongCreateRequest(title = title, artist = artist))
            if (resp.code == 0 && resp.data != null) {
                Result.success(resp.data.toDomain())
            } else {
                Result.failure(Exception(resp.message))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun updateSong(id: Int, title: String?, artist: String?): Result<Song> = withContext(Dispatchers.IO) {
        try {
            val resp = api.updateSong(id, SongUpdateRequest(title = title, artist = artist))
            if (resp.code == 0 && resp.data != null) {
                Result.success(resp.data.toDomain())
            } else {
                Result.failure(Exception(resp.message))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun deleteSong(id: Int): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            api.deleteSong(id)
            // Also clean local cache
            trackDao.deleteTracksForSong(id)
            songDao.deleteSong(id)
            deleteLocalFiles(id)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun uploadTrack(songId: Int, name: String, file: File): Result<Track> = withContext(Dispatchers.IO) {
        try {
            val mediaType = "audio/*".toMediaTypeOrNull()
            val filePart = MultipartBody.Part.createFormData(
                "file", file.name, file.asRequestBody(mediaType)
            )
            val namePart = name.toRequestBody("text/plain".toMediaTypeOrNull())
            val resp = api.uploadTrack(songId, filePart, namePart)
            if (resp.code == 0 && resp.data != null) {
                Result.success(resp.data.toDomain())
            } else {
                Result.failure(Exception(resp.message))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun uploadOriginal(songId: Int, file: File): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val mediaType = "audio/*".toMediaTypeOrNull()
            val filePart = MultipartBody.Part.createFormData(
                "file", file.name, file.asRequestBody(mediaType)
            )
            val resp = api.uploadOriginal(songId, filePart)
            if (resp.code == 0) Result.success(Unit)
            else Result.failure(Exception(resp.message))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    // ── Download ──

    suspend fun downloadTrack(track: Track, onProgress: (Float) -> Unit): Result<String> =
        withContext(Dispatchers.IO) {
            try {
                val trackDir = getTrackDir(track.songId)
                trackDir.mkdirs()
                val localFile = File(trackDir, "${track.name}.mp3")

                val responseBody = api.downloadTrack(track.id)
                val totalBytes = responseBody.contentLength()
                var downloadedBytes = 0L

                responseBody.byteStream().use { input ->
                    FileOutputStream(localFile).use { output ->
                        val buffer = ByteArray(8192)
                        var bytesRead: Int
                        while (input.read(buffer).also { bytesRead = it } != -1) {
                            output.write(buffer, 0, bytesRead)
                            downloadedBytes += bytesRead
                            if (totalBytes > 0) {
                                onProgress(downloadedBytes.toFloat() / totalBytes)
                            }
                        }
                    }
                }

                // Mark as downloaded in local DB
                trackDao.insertTrack(
                    CachedTrack(
                        id = track.id,
                        songId = track.songId,
                        name = track.name,
                        localPath = localFile.absolutePath,
                        downloadState = "DOWNLOADED",
                    )
                )
                Result.success(localFile.absolutePath)
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    // ── Local cache ──

    suspend fun getCachedTracks(songId: Int): List<CachedTrack> = withContext(Dispatchers.IO) {
        trackDao.getTracksForSong(songId)
    }

    suspend fun isSongFullyCached(songId: Int): Boolean = withContext(Dispatchers.IO) {
        val cached = trackDao.getTracksForSong(songId)
        cached.size == 6 && cached.all { it.downloadState == "DOWNLOADED" }
    }

    suspend fun isAnyTrackCached(songId: Int): Boolean = withContext(Dispatchers.IO) {
        val cached = trackDao.getTracksForSong(songId)
        cached.any { it.downloadState == "DOWNLOADED" }
    }

    fun getLocalPath(songId: Int, trackName: String): String? {
        for (ext in listOf("mp3", "m4a")) {
            val file = File(getTrackDir(songId), "$trackName.$ext")
            if (file.exists()) return file.absolutePath
        }
        return null
    }

    // ── Helpers ──

    /** App-internal storage: no permissions needed, cleaned on uninstall */
    private fun getTrackDir(songId: Int): File {
        return File(appContext.filesDir, "tracks/$songId")
    }

    private fun deleteLocalFiles(songId: Int) {
        getTrackDir(songId).deleteRecursively()
    }

    private fun SongDto.toDomain(): Song = Song(
        id = id,
        title = title,
        artist = artist,
        coverUrl = cover_url,
        bpm = bpm,
        createdAt = created_at,
        updatedAt = updated_at,
        tracks = tracks.map { it.toDomain() },
    )

    private fun TrackDto.toDomain(): Track = Track(
        id = id,
        songId = song_id,
        name = name,
        filePath = file_path,
        fileSize = file_size,
        duration = duration,
        downloadUrl = "",
    )
}
