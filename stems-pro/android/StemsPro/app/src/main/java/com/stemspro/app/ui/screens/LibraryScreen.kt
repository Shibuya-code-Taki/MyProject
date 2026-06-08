package com.stemspro.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.stemspro.app.data.repository.SongRepository
import com.stemspro.app.model.Song
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(
    repository: SongRepository,
    onPlaySong: (Int) -> Unit,
    onUploadClick: () -> Unit,
) {
    var songs by remember { mutableStateOf<List<Song>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var searchQuery by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    fun load() {
        scope.launch {
            isLoading = true
            repository.fetchSongs(search = searchQuery.ifBlank { null })
                .onSuccess { songs = it; error = null }
                .onFailure { error = it.message }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) { load() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Stems Pro") },
                actions = {
                    IconButton(onClick = { load() }) { Icon(Icons.Default.Refresh, "刷新") }
                    IconButton(onClick = onUploadClick) { Icon(Icons.Default.Add, "上传") }
                }
            )
        }
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            OutlinedTextField(
                value = searchQuery, onValueChange = { searchQuery = it },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                placeholder = { Text("搜索...") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                singleLine = true,
            )
            LaunchedEffect(searchQuery) { load() }

            when {
                isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("加载失败", color = MaterialTheme.colorScheme.error)
                        Button(onClick = { load() }) { Text("重试") }
                    }
                }
                songs.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.MusicNote, null, modifier = Modifier.size(64.dp), tint = MaterialTheme.colorScheme.outline)
                        Text("还没有歌曲", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.outline)
                        Text("点右上角 + 上传新歌", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.outline)
                    }
                }
                else -> LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(songs, key = { it.id }) { song ->
                        SongCard(song = song, onPlay = { onPlaySong(song.id) }, onDelete = {
                            scope.launch { repository.deleteSong(song.id).onSuccess { load() } }
                        })
                    }
                }
            }
        }
    }
}

@Composable
fun SongCard(song: Song, onPlay: () -> Unit, onDelete: () -> Unit) {
    var showDel by remember { mutableStateOf(false) }
    Card(
        modifier = Modifier.fillMaxWidth().clickable { onPlay() },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(song.title, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (song.artist.isNotBlank()) Text(song.artist, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.outline)
                    if (song.bpm > 0) Text("${song.bpm.toInt()} BPM", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.outline)
                }
                Text("${song.tracks.size}轨", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.outline)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                song.tracks.forEach { t ->
                    Surface(
                        shape = MaterialTheme.shapes.extraSmall,
                        color = androidx.compose.ui.graphics.Color(t.colorLong()).copy(alpha = 0.2f),
                    ) { Text(t.displayName(), modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp), style = MaterialTheme.typography.labelSmall, color = androidx.compose.ui.graphics.Color(t.colorLong())) }
                }
            }
            Spacer(Modifier.height(8.dp))
            if (!showDel) {
                TextButton(onClick = { showDel = true }, colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error.copy(alpha = 0.6f))) {
                    Icon(Icons.Default.Delete, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("删除")
                }
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { onDelete() }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { Text("确认删除") }
                    OutlinedButton(onClick = { showDel = false }) { Text("取消") }
                }
            }
        }
    }
}
