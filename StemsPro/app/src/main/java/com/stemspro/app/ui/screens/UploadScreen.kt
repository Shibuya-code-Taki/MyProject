package com.stemspro.app.ui.screens

import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.stemspro.app.data.repository.SongRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UploadScreen(repository: SongRepository, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current

    var artist by remember { mutableStateOf("") }
    var title by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf("") }
    var uri by remember { mutableStateOf<Uri?>(null) }
    var fname by remember { mutableStateOf("") }
    var done by remember { mutableStateOf(false) }
    var step by remember { mutableStateOf("") }
    var uploadProgress by remember { mutableStateOf(0f) }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { u ->
        if (u == null) return@rememberLauncherForActivityResult
        uri = u
        try {
            ctx.contentResolver.query(u, null, null, null, null)?.use { c ->
                if (c.moveToFirst()) { val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME); if (i >= 0) fname = c.getString(i) ?: "" }
            }
        } catch (_: Exception) {}
        val name = fname.substringBeforeLast(".")
        if (name.contains(" - ")) {
            val p = name.split(" - ", limit = 2)
            if (artist.isBlank()) artist = p[0].trim()
            if (title.isBlank()) title = p[1].trim()
        } else if (title.isBlank()) title = name.trim()
    }

    fun upload() {
        val u = uri ?: return
        if (artist.isBlank() || title.isBlank()) return
        scope.launch {
            busy = true; done = false; msg = ""; uploadProgress = 0f
            step = "1/3 创建歌曲..."
            repository.createSong(artist = artist, title = title).onSuccess { song ->
                val sid = song.id
                step = "2/3 复制文件..."
                try {
                    val ext = fname.substringAfterLast(".", "mp3")
                    val tmp = File(ctx.cacheDir, "upload_${sid}.$ext")
                    withContext(Dispatchers.IO) {
                        ctx.contentResolver.openInputStream(u)?.use { inp ->
                            tmp.outputStream().use { out -> inp.copyTo(out) }
                        }
                    }
                    step = "3/3 上传到服务器 (${tmp.length()/1024/1024}MB)..."
                    step = "3/3 上传中... (${tmp.length()/1024/1024}MB)"
                    repository.uploadOriginal(sid, tmp).onSuccess {
                        tmp.delete()
                        done = true; step = ""
                        msg = "✅「${song.title}」已上传！\nROG 正在自动分离..."
                        kotlinx.coroutines.delay(4000)
                        artist = ""; title = ""; uri = null; fname = ""; done = false; msg = ""; uploadProgress = 0f
                        onBack()
                    }.onFailure { e ->
                        tmp.delete()
                        msg = "上传失败: ${e.message}\n请检查网络后重试。"
                    }
                } catch (e: Exception) {
                    msg = "文件处理失败: ${e.message}"
                }
            }.onFailure { e -> msg = "创建失败: ${e.message}" }
            busy = false
        }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("上传歌曲") }, navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, null) } }) }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("上传后 ROG 自动处理", style = MaterialTheme.typography.titleMedium)
            Text("选择歌曲 → 填信息 → 上传 → ROG 自动分离", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.outline)

            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Row(Modifier.padding(14.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (fname.isNotBlank()) fname else "未选择", style = MaterialTheme.typography.bodyLarge)
                        if (fname.isNotBlank()) {
                            val sz = try { ctx.contentResolver.openInputStream(uri!!)?.available() } catch (_: Exception) { null }
                            if (sz != null) Text("${sz / 1024 / 1024} MB", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.outline)
                        }
                    }
                    Button(onClick = { picker.launch("*/*") }) { Text(if (uri != null) "更换" else "选择文件") }
                }
            }

            OutlinedTextField(value = artist, onValueChange = { artist = it }, label = { Text("歌手") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("歌名") }, modifier = Modifier.fillMaxWidth(), singleLine = true)

            Button(onClick = { upload() }, modifier = Modifier.fillMaxWidth().height(50.dp), enabled = !busy && artist.isNotBlank() && title.isNotBlank() && uri != null) {
                if (busy) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                    Spacer(Modifier.width(8.dp))
                    Text(step, style = MaterialTheme.typography.bodySmall)
                } else Text("上传", style = MaterialTheme.typography.titleSmall)
            }

            if (busy && uploadProgress > 0) {
                LinearProgressIndicator(progress = { uploadProgress }, modifier = Modifier.fillMaxWidth())
            }

            if (msg.isNotBlank()) {
                Card(colors = CardDefaults.cardColors(containerColor = if (done) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant)) {
                    Text(msg, Modifier.padding(14.dp))
                }
            }
        }
    }
}
