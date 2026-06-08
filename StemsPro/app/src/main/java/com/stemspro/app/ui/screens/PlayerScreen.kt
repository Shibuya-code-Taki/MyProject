package com.stemspro.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.stemspro.app.data.repository.SongRepository
import com.stemspro.app.model.Song
import com.stemspro.app.model.Track
import com.stemspro.app.player.MultiTrackPlayer
import com.stemspro.app.player.PlayerState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.delay

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(songId: Int, repository: SongRepository, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val player = remember { MultiTrackPlayer() }
    val ps by player.state.collectAsState()

    var song by remember { mutableStateOf<Song?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var isDownloading by remember { mutableStateOf(false) }
    var isDecoding by remember { mutableStateOf(false) }
    var downProg by remember { mutableStateOf(0f) }
    var cachedCount by remember { mutableStateOf(0) }
    var errMsg by remember { mutableStateOf<String?>(null) }

    DisposableEffect(Unit) {
        onDispose { player.destroy() }
    }

    LaunchedEffect(songId) {
        isLoading = true
        repository.fetchSongs().onSuccess { songs ->
            song = songs.find { it.id == songId }
            song?.let { s -> if (s.bpm > 0) player.setBpm(s.bpm) }
        }
        val ct = repository.getCachedTracks(songId)
        cachedCount = ct.size
        isLoading = false
    }

    fun doDownload(onDone: () -> Unit) {
        val tracks = song?.tracks ?: return
        scope.launch {
            isDownloading = true; downProg = 0f; var done = 0
            for (t in tracks) {
                repository.downloadTrack(t) { p -> downProg = (done + p) / tracks.size }
                    .onSuccess { done++; downProg = done.toFloat() / tracks.size }
                    .onFailure { e -> errMsg = "下载 ${t.name} 失败: ${e.message}" }
            }
            isDownloading = false
            cachedCount = repository.getCachedTracks(songId).size
            onDone()
        }
    }

    fun loadAndPlay() {
        val hasLocal = song?.tracks?.any { t -> repository.getLocalPath(songId, t.name) != null } == true
        if (!hasLocal) { errMsg = "请先下载分轨"; return }
        val paths = song?.tracks?.mapNotNull { t -> repository.getLocalPath(songId, t.name) } ?: return
        if (paths.isEmpty()) { errMsg = "没有找到本地音轨文件"; return }
        errMsg = null
        scope.launch {
            isDecoding = true; downProg = 0f
            player.loadAndDecode(paths) { done, total -> downProg = done.toFloat() / total }
            isDecoding = false
            player.play()
        }
    }

    fun handlePlay() {
        if (ps.state == PlayerState.PLAYING) { player.pause(); return }
        if (ps.state == PlayerState.PAUSED) { player.play(); return }
        if (!player.isLoaded) {
            if (cachedCount == 0) {
                doDownload { loadAndPlay() }
            } else {
                loadAndPlay()
            }
        } else {
            player.play()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(song?.title ?: "", maxLines = 1) },
                navigationIcon = { IconButton(onClick = { player.destroy(); onBack() }) { Icon(Icons.Default.ArrowBack, null) } }
            )
        }
    ) { pad ->
        if (isLoading) { Box(Modifier.padding(pad).fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }; return@Scaffold }
        val s = song ?: run { Box(Modifier.padding(pad).fillMaxSize(), contentAlignment = Alignment.Center) { Text("歌曲未找到") }; return@Scaffold }

        Column(Modifier.padding(pad).fillMaxSize().padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(s.artist.ifBlank { "未知歌手" }, style = MaterialTheme.typography.titleMedium)
            Text("${s.tracks.size} 轨", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.outline)
            if (s.bpm > 0) Text("${s.bpm.toInt()} BPM", style = MaterialTheme.typography.bodyMedium, color = Color(0xFFA29BFE))
            Spacer(Modifier.height(16.dp))

            // Play/Pause
            Row(horizontalArrangement = Arrangement.spacedBy(24.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { player.stop() }) { Icon(Icons.Default.SkipPrevious, null, Modifier.size(36.dp)) }
                IconButton(
                    onClick = { handlePlay() },
                    modifier = Modifier.size(64.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primary),
                    enabled = !isDownloading,
                ) {
                    val ico = when {
                        isDownloading -> Icons.Default.HourglassEmpty
                        ps.state == PlayerState.PLAYING -> Icons.Default.Pause
                        ps.state == PlayerState.IDLE && !player.isLoaded -> Icons.Default.HourglassEmpty
                        else -> Icons.Default.PlayArrow
                    }
                    Icon(ico, null, tint = Color.White, modifier = Modifier.size(36.dp))
                }
            }

            errMsg?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall) }

            // Progress
            if (ps.duration > 0) {
                Spacer(Modifier.height(12.dp))
                Slider(value = ps.position, onValueChange = { player.seek(it) }, valueRange = 0f..ps.duration.coerceAtLeast(1f), modifier = Modifier.fillMaxWidth())
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(fmtTime(ps.position), style = MaterialTheme.typography.labelSmall)
                    Text(fmtTime(ps.duration), style = MaterialTheme.typography.labelSmall)
                }
            }

            // Download
            if (cachedCount < s.tracks.size && !isDownloading) {
                Button(onClick = { doDownload { loadAndPlay() } }) {
                    Icon(Icons.Default.Download, null); Spacer(Modifier.width(6.dp)); Text("下载分轨 (${cachedCount}/${s.tracks.size})")
                }
            }
            if (isDownloading) {
                LinearProgressIndicator(progress = { downProg }, modifier = Modifier.fillMaxWidth().padding(top = 4.dp))
                Text("下载中 ${(downProg * 100).toInt()}%", style = MaterialTheme.typography.labelMedium)
            }
            if (isDecoding) {
                LinearProgressIndicator(progress = { downProg }, modifier = Modifier.fillMaxWidth().padding(top = 4.dp))
                Text("解码中 ${(downProg * 100).toInt()}%", style = MaterialTheme.typography.labelMedium)
            }

            Spacer(Modifier.height(12.dp))

            // Metronome card
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(12.dp)) {
                Column(Modifier.padding(12.dp)) {
                    // BPM row
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        BpmRepeatButton(
                            icon = { Icon(Icons.Default.Remove, "-", Modifier.size(16.dp), tint = Color(0xFFA29BFE)) },
                            onChange = { delta -> player.setBpm((ps.bpm + delta).coerceIn(30f, 300f)) },
                            deltaPerStep = -0.1f,
                        )
                        Slider(
                            value = ps.bpm.coerceIn(30f, 300f),
                            onValueChange = { player.setBpm(Math.round(it * 10).toFloat() / 10f) },
                            valueRange = 30f..300f,
                            modifier = Modifier.weight(1f),
                            colors = SliderDefaults.colors(thumbColor = Color(0xFFA29BFE), activeTrackColor = Color(0xFFA29BFE))
                        )
                        BpmRepeatButton(
                            icon = { Icon(Icons.Default.Add, "+", Modifier.size(16.dp), tint = Color(0xFFA29BFE)) },
                            onChange = { delta -> player.setBpm((ps.bpm + delta).coerceIn(30f, 300f)) },
                            deltaPerStep = 0.1f,
                        )
                        Text(fmtBpm(ps.bpm), style = MaterialTheme.typography.titleMedium, color = Color(0xFFA29BFE), modifier = Modifier.width(52.dp))
                    }
                    Text("长按 +/- 持续调节 | 拖动滑块也可微调", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.outline)

                    // Beat dots + metronome toggle
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            for (i in 0..3) {
                                val active = i == ps.beat % 4 && ps.state == PlayerState.PLAYING
                                Box(Modifier.size(10.dp).clip(CircleShape).background(
                                    if (active) Color(0xFFF1C40F)
                                    else if (i == 0) Color(0xFFA29BFE).copy(0.5f)
                                    else Color(0xFF444466)
                                ))
                            }
                        }
                        IconButton(
                            onClick = { player.toggleMetronome() },
                            modifier = Modifier.size(36.dp).clip(CircleShape).background(
                                if (ps.metronomeEnabled) Color(0xFFF1C40F).copy(0.2f) else MaterialTheme.colorScheme.surfaceVariant
                            )
                        ) {
                            Icon(Icons.Default.MusicNote, "节拍器",
                                tint = if (ps.metronomeEnabled) Color(0xFFF1C40F) else MaterialTheme.colorScheme.outline,
                                modifier = Modifier.size(20.dp))
                        }
                    }

                    // Volume slider when metronome is on
                    AnimatedVisibility(ps.metronomeEnabled) {
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
                            Icon(Icons.Default.VolumeUp, null, Modifier.size(16.dp), tint = Color(0xFFF1C40F))
                            Slider(
                                value = ps.metronomeVolume, onValueChange = { player.setMetronomeVolume(it) },
                                valueRange = 0f..1f, modifier = Modifier.weight(1f).padding(horizontal = 8.dp),
                                colors = SliderDefaults.colors(thumbColor = Color(0xFFF1C40F), activeTrackColor = Color(0xFFF1C40F))
                            )
                            Text("${(ps.metronomeVolume * 100).toInt()}%", style = MaterialTheme.typography.labelSmall, color = Color(0xFFF1C40F))
                        }
                    }
                }
            }

            Spacer(Modifier.height(12.dp))
            Text("音轨控制", style = MaterialTheme.typography.titleSmall)

            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.weight(1f)) {
                items(s.tracks) { t ->
                    val ts = ps.tracks[t.name] ?: com.stemspro.app.player.TrackUiState()
                    val tc = Color(t.colorLong())
                    val anySolo = ps.tracks.values.any { it.soloed }
                    val dimmed = ts.muted || (anySolo && !ts.soloed)
                    val ec = if (dimmed) tc.copy(0.3f) else tc
                    var localVol by remember { mutableStateOf(ts.volume) }
                    LaunchedEffect(ts.volume) { if (ts.volume != localVol) localVol = ts.volume }

                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), shape = RoundedCornerShape(12.dp)) {
                        Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            IconButton(onClick = { player.toggleMute(t.name) }, modifier = Modifier.size(36.dp)) {
                                Icon(if (ts.muted) Icons.Default.VolumeOff else Icons.Default.VolumeUp, null, tint = ec)
                            }
                            TextButton(onClick = { player.toggleSolo(t.name) }, modifier = Modifier.width(44.dp),
                                colors = ButtonDefaults.textButtonColors(contentColor = if (ts.soloed) Color(0xFFF1C40F) else MaterialTheme.colorScheme.outline)
                            ) { Text("S", style = MaterialTheme.typography.labelLarge, textAlign = TextAlign.Center) }
                            Column(Modifier.weight(1f)) {
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Text(t.displayName(), style = MaterialTheme.typography.labelLarge, color = ec)
                                    Text("${(localVol * 100).toInt()}%", style = MaterialTheme.typography.labelSmall, color = ec)
                                }
                                Slider(
                                    value = localVol,
                                    onValueChange = { localVol = it; player.setVolume(t.name, it) },
                                    valueRange = 0f..1f, modifier = Modifier.fillMaxWidth(),
                                    colors = SliderDefaults.colors(thumbColor = ec, activeTrackColor = ec)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

fun fmtTime(s: Float): String {
    if (s.isNaN() || s.isInfinite()) return "0:00"
    val m = (s / 60).toInt()
    return "$m:${(s % 60).toInt().toString().padStart(2, '0')}"
}

fun fmtBpm(b: Float): String = if (b <= 0 || b.isNaN()) "--" else String.format("%.1f", b)

/** BPM repeat button: tap = +/-0.1, hold = auto-repeat with acceleration. */
@Composable
fun BpmRepeatButton(
    icon: @Composable () -> Unit,
    onChange: (delta: Float) -> Unit,
    deltaPerStep: Float,
) {
    val interactionSource = remember { MutableInteractionSource() }
    val isPressed by interactionSource.collectIsPressedAsState()

    LaunchedEffect(isPressed) {
        if (!isPressed) return@LaunchedEffect
        var delayMs = 400L
        val minDelay = 30L
        while (isPressed) {
            onChange(deltaPerStep)
            delay(delayMs)
            delayMs = (delayMs - (delayMs / 5)).coerceAtLeast(minDelay)
        }
    }

    IconButton(
        onClick = { onChange(deltaPerStep) },
        modifier = Modifier.size(28.dp),
        interactionSource = interactionSource,
    ) { icon() }
}
