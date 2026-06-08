package com.stemspro.app.di

import android.content.Context
import androidx.room.Room
import com.stemspro.app.data.api.StemsApi
import com.stemspro.app.data.local.AppDatabase
import com.stemspro.app.data.repository.SongRepository
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/** Manually-built DI container — simple and no code-gen required. */
class AppContainer(context: Context) {

    companion object {
        // Change this to your server IP or domain (behind 火盾云 CDN)
        const val BASE_URL = "http://YOUR_SERVER_IP:8000/"
    }

    // Network
    private val okHttpClient: OkHttpClient by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }
        OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(120, TimeUnit.SECONDS)
            .addInterceptor(logging)
            .build()
    }

    val api: StemsApi by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(StemsApi::class.java)
    }

    // Database
    val database: AppDatabase by lazy {
        Room.databaseBuilder(
            context.applicationContext,
            AppDatabase::class.java,
            "stems_pro.db"
        ).build()
    }

    // Repository
    val songRepository: SongRepository by lazy {
        SongRepository(api, database, context.applicationContext)
    }
}
