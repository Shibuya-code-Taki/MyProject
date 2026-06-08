package com.stemspro.app.data.api

import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.http.*

/** DTOs matching the server's JSON response format. */
data class ApiResponse<T>(
    val code: Int = 0,
    val message: String = "success",
    val data: T? = null,
)

data class SongListData(
    val songs: List<SongDto>,
    val total: Int,
    val page: Int,
    val page_size: Int,
)

data class SongDto(
    val id: Int = 0,
    val title: String = "",
    val artist: String = "",
    val cover_url: String = "",
    val bpm: Float = 0f,
    val created_at: String = "",
    val updated_at: String = "",
    val tracks: List<TrackDto> = emptyList(),
)

data class TrackDto(
    val id: Int = 0,
    val song_id: Int = 0,
    val name: String = "",
    val file_path: String = "",
    val file_size: Long = 0,
    val duration: Float = 0f,
)

data class SongCreateRequest(
    val title: String,
    val artist: String = "",
    val cover_url: String = "",
    val bpm: Float = 0f,
)

data class SongUpdateRequest(
    val title: String? = null,
    val artist: String? = null,
    val cover_url: String? = null,
)

/** Retrofit API interface for Stems Pro server. */
interface StemsApi {

    @GET("api/songs")
    suspend fun listSongs(
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 50,
        @Query("search") search: String? = null,
    ): ApiResponse<SongListData>

    @GET("api/songs/{id}")
    suspend fun getSong(@Path("id") songId: Int): ApiResponse<SongDto>

    @POST("api/songs")
    suspend fun createSong(@Body body: SongCreateRequest): ApiResponse<SongDto>

    @PUT("api/songs/{id}")
    suspend fun updateSong(
        @Path("id") songId: Int,
        @Body body: SongUpdateRequest,
    ): ApiResponse<SongDto>

    @DELETE("api/songs/{id}")
    suspend fun deleteSong(@Path("id") songId: Int): ApiResponse<Any>

    @Multipart
    @POST("api/songs/{id}/tracks")
    suspend fun uploadTrack(
        @Path("id") songId: Int,
        @Part file: MultipartBody.Part,
        @Part("name") name: RequestBody,
    ): ApiResponse<TrackDto>

    @GET("api/tracks/{id}/download")
    @Streaming
    suspend fun downloadTrack(@Path("id") trackId: Int): ResponseBody

    @Multipart
    @POST("api/songs/{id}/original")
    suspend fun uploadOriginal(
        @Path("id") songId: Int,
        @Part file: MultipartBody.Part,
    ): ApiResponse<Any>

    @POST("api/songs/{id}/status")
    suspend fun updateSongStatus(
        @Path("id") songId: Int,
        @Field("status") status: String,
    ): ApiResponse<Any>
}
