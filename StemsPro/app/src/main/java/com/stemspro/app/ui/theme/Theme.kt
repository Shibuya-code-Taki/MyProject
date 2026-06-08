package com.stemspro.app.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF6C5CE7),
    onPrimary = Color.White,
    primaryContainer = Color(0xFF4A3DB5),
    secondary = Color(0xFFA29BFE),
    background = Color(0xFF0F0F14),
    surface = Color(0xFF1A1A24),
    surfaceVariant = Color(0xFF252536),
    onBackground = Color(0xFFE0E0E8),
    onSurface = Color(0xFFE0E0E8),
    outline = Color(0xFF2A2A3A),
    error = Color(0xFFE74C3C),
)

@Composable
fun StemsProTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = Typography(),
        content = content
    )
}
