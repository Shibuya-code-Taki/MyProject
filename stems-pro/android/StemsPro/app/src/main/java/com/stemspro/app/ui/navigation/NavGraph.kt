package com.stemspro.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.stemspro.app.StemsProApp
import com.stemspro.app.ui.screens.LibraryScreen
import com.stemspro.app.ui.screens.PlayerScreen
import com.stemspro.app.ui.screens.UploadScreen

object Routes {
    const val LIBRARY = "library"
    const val PLAYER = "player/{songId}"
    const val UPLOAD = "upload"

    fun player(songId: Int) = "player/$songId"
}

@Composable
fun StemsNavGraph() {
    val navController = rememberNavController()
    val context = LocalContext.current
    val container = (context.applicationContext as StemsProApp).container

    NavHost(navController = navController, startDestination = Routes.LIBRARY) {
        composable(Routes.LIBRARY) {
            LibraryScreen(
                repository = container.songRepository,
                onPlaySong = { songId -> navController.navigate(Routes.player(songId)) },
                onUploadClick = { navController.navigate(Routes.UPLOAD) },
            )
        }
        composable(
            Routes.PLAYER,
            arguments = listOf(navArgument("songId") { type = NavType.IntType })
        ) { backStackEntry ->
            val songId = backStackEntry.arguments?.getInt("songId") ?: return@composable
            PlayerScreen(
                songId = songId,
                repository = container.songRepository,
                onBack = { navController.popBackStack() },
            )
        }
        composable(Routes.UPLOAD) {
            UploadScreen(
                repository = container.songRepository,
                onBack = { navController.popBackStack() },
            )
        }
    }
}
