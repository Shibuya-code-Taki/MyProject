package com.stemspro.app.data.local

import androidx.room.*

@Entity(tableName = "cached_songs")
data class CachedSong(
    @PrimaryKey val id: Int,
    val title: String,
    val artist: String,
    val coverUrl: String,
    val createdAt: String,
)

@Entity(tableName = "cached_tracks")
data class CachedTrack(
    @PrimaryKey val id: Int,
    val songId: Int,
    val name: String,
    val localPath: String,
    val downloadState: String = "NOT_DOWNLOADED",
)

@Dao
interface SongDao {
    @Query("SELECT * FROM cached_songs ORDER BY createdAt DESC")
    suspend fun getAllSongs(): List<CachedSong>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertSong(song: CachedSong)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertSongs(songs: List<CachedSong>)

    @Query("DELETE FROM cached_songs WHERE id = :id")
    suspend fun deleteSong(id: Int)

    @Query("SELECT * FROM cached_songs WHERE id = :id")
    suspend fun getSong(id: Int): CachedSong?
}

@Dao
interface TrackDao {
    @Query("SELECT * FROM cached_tracks WHERE songId = :songId")
    suspend fun getTracksForSong(songId: Int): List<CachedTrack>

    @Query("SELECT * FROM cached_tracks WHERE id = :id")
    suspend fun getTrack(id: Int): CachedTrack?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTrack(track: CachedTrack)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTracks(tracks: List<CachedTrack>)

    @Query("UPDATE cached_tracks SET downloadState = :state WHERE id = :id")
    suspend fun updateDownloadState(id: Int, state: String)

    @Query("DELETE FROM cached_tracks WHERE songId = :songId")
    suspend fun deleteTracksForSong(songId: Int)

    @Query("DELETE FROM cached_tracks WHERE id = :trackId")
    suspend fun deleteTrack(trackId: Int)
}

@Database(entities = [CachedSong::class, CachedTrack::class], version = 1, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun songDao(): SongDao
    abstract fun trackDao(): TrackDao
}
