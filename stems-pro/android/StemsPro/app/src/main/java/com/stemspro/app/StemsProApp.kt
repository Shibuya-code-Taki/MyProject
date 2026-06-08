package com.stemspro.app

import android.app.Application
import com.stemspro.app.di.AppContainer

class StemsProApp : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
