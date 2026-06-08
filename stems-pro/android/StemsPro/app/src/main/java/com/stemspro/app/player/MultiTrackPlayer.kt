package com.stemspro.app.player

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.media.MediaExtractor
import android.media.MediaFormat
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.math.PI
import kotlin.math.sin

enum class PlayerState { IDLE, READY, PLAYING, PAUSED, STOPPED }
data class TrackUiState(val volume: Float = 1f, val muted: Boolean = false, val soloed: Boolean = false)
data class PlayerUiState(
    val state: PlayerState = PlayerState.IDLE, val position: Float = 0f, val duration: Float = 0f,
    val bpm: Float = 120f, val beat: Int = 0, val metronomeEnabled: Boolean = false,
    val metronomeVolume: Float = 0.8f, val metronomeAccent: Boolean = true,
    val tracks: Map<String, TrackUiState> = emptyMap(),
)

class MultiTrackPlayer {
    companion object {
        private const val TAG = "StemsPlayer"
        val NAMES = listOf("vocals","drums","bass","guitar","piano","other")
    }

    private val _state = MutableStateFlow(PlayerUiState(tracks = NAMES.associateWith { TrackUiState() }))
    val state: StateFlow<PlayerUiState> = _state.asStateFlow()

    // Pre-decoded PCM — decoded sequentially, one track at a time
    private val pcm = mutableMapOf<String, ShortArray>()
    private val _tracks = NAMES.associateWith { TrackUiState() }.toMutableMap()
    private val scope = CoroutineScope(Dispatchers.Main + Job())

    private var audioTrack: AudioTrack? = null
    private var playJob: Job? = null
    private var sampleRate = 44100
    private var totalFrames = 0
    private var currentFrame = 0

    var currentBpm: Float = 120f
    var metronomeEnabled: Boolean = false
    var metronomeAccent: Boolean = true
    private var _metroVolume: Float = 0.8f
    private var metroClickSamples = ShortArray(0)
    private var metroClickAccent = ShortArray(0)  // beat-0 click
    private var metroBeatLen = 0
    private var metroPhase = 0     // phase counter: 0..metroBeatLen-1, sample-accurate
    private var metroBeatIdx = 0   // which beat in the bar (0..3)
    val isLoaded: Boolean get() = pcm.isNotEmpty()

    /** Decode all tracks to memory — one at a time, with progress callback. */
    suspend fun loadAndDecode(
        filePaths: List<String>,
        onProgress: suspend (Int, Int) -> Unit = { _, _ -> }
    ) = withContext(Dispatchers.IO) {
        stop(); pcm.clear()
        val total = filePaths.size
        for ((idx, fp) in filePaths.withIndex()) {
            val name = fp.substringAfterLast("/").substringBeforeLast(".").lowercase().replace(Regex("[^a-z]"), "")
            onProgress(idx + 1, total)
            val r = AudioDecoder().decode(fp)
            if (r != null) { pcm[name] = r.samples; sampleRate = r.sampleRate }
            else Log.w(TAG, "decode FAILED: $name")
        }
        onProgress(total, total)
        if (pcm.isEmpty()) return@withContext
        totalFrames = pcm.values.maxOf { it.size }
        val dur = if (sampleRate > 0) totalFrames.toFloat() / sampleRate else 0f
        _state.value = _state.value.copy(state = PlayerState.READY, duration = dur, bpm = currentBpm, metronomeVolume = _metroVolume, metronomeAccent = metronomeAccent)
    }

    fun play() {
        if (pcm.isEmpty()) return
        val ws = _state.value.state == PlayerState.STOPPED || _state.value.state == PlayerState.IDLE
        cleanUp(); if (ws) { currentFrame = 0; metroPhase = 0; metroBeatIdx = 0 }; prebuildMetronome()
        val mb = AudioTrack.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        audioTrack = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(sampleRate).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setBufferSizeInBytes(mb.coerceAtLeast(16384) * 4).setTransferMode(AudioTrack.MODE_STREAM).build()
        audioTrack?.play()
        _state.value = _state.value.copy(state = PlayerState.PLAYING, position = 0f, beat = 0); syncTracks()
        playJob = scope.launch(Dispatchers.IO) { try { streamMix(currentFrame) } catch (e: Exception) { Log.e(TAG, "mix crash", e); withContext(Dispatchers.Main) { _state.value = _state.value.copy(state = PlayerState.STOPPED) } } }
    }

    private suspend fun streamMix(startFrame: Int) {
        val BUF = 16384; val mix = IntArray(BUF); var fr = startFrame; val total = totalFrames; var lastUi = 0L
        while (currentFrame < total) {
            mix.fill(0); val aso = _tracks.values.any { it.soloed }
            for ((n, samples) in pcm) {
                val t = _tracks[n] ?: continue; if (aso && !t.soloed) continue; if (t.muted) continue
                val v = t.volume; val end = minOf(fr + BUF, samples.size); var si = fr; var di = 0
                while (si < end) mix[di++] += (samples[si++] * v).toInt()
            }
            val out = ShortArray(BUF) { i -> mix[i].coerceIn(-32768, 32767).toShort() }
            if (metronomeEnabled && metroClickSamples.isNotEmpty() && metroBeatLen > 0) {
                // Guard: BPM change may shrink metroBeatLen past current phase
                if (metroPhase >= metroBeatLen) { metroPhase = 0; metroBeatIdx = 0 }
                for (i in 0 until BUF) {
                    val useAccent = metronomeAccent && (metroBeatIdx == 0) && metroClickAccent.isNotEmpty()
                    val clk = if (useAccent) metroClickAccent else metroClickSamples
                    if (metroPhase < clk.size) {
                        val cv = (clk[metroPhase] * _metroVolume).toInt()
                        out[i] = (out[i] + cv).coerceIn(-32768, 32767).toShort()
                    }
                    metroPhase++
                    if (metroPhase >= metroBeatLen) {
                        metroPhase = 0
                        metroBeatIdx = (metroBeatIdx + 1) % 4
                    }
                }
            }
            }
            audioTrack?.write(out, 0, BUF); fr += BUF; currentFrame = fr
            if (System.currentTimeMillis() - lastUi >= 250) { lastUi = System.currentTimeMillis(); val pos = fr.toFloat() / sampleRate; _state.value = _state.value.copy(position = pos, beat = metroBeatIdx) }
            yield()
        }
        withContext(Dispatchers.Main) { _state.value = _state.value.copy(state = PlayerState.STOPPED) }
    }

    private fun cleanUp() { playJob?.cancel(); audioTrack?.stop(); audioTrack?.release(); audioTrack = null }
    private fun prebuildMetronome() {
        metroBeatLen = (sampleRate * 60f / currentBpm).toInt().coerceIn(1, sampleRate * 10)
        val cl = (sampleRate * 0.06).toInt().coerceIn(100, 6000); val fo = cl / 3
        fun gen(f: Float): ShortArray { val s = ShortArray(cl); for (i in 0 until cl) { val env = when { i < 3 -> 1f; i < cl - fo -> 1f; else -> (cl - i).toFloat() / fo }; s[i] = (sin(2.0 * PI * f * (i.toFloat() / sampleRate)) * env * 28000).toInt().coerceIn(-32768, 32767).toShort() }; return s }
        metroClickAccent = gen(1800f)   // beat 0 — higher pitch, always stored
        metroClickSamples = gen(1200f)  // beats 1-3 — normal pitch
    }

    fun pause() { playJob?.cancel(); audioTrack?.pause(); _state.value = _state.value.copy(state = PlayerState.PAUSED) }
    fun stop() { cleanUp(); currentFrame = 0; metroPhase = 0; metroBeatIdx = 0; _state.value = _state.value.copy(state = PlayerState.IDLE, position = 0f, beat = 0) }
    fun unload() { stop(); pcm.clear() }
    fun seek(ps: Float) { val tg = (ps * sampleRate).toInt().coerceIn(0, totalFrames); val wp = _state.value.state == PlayerState.PLAYING; playJob?.cancel(); currentFrame = tg; metroPhase = 0; metroBeatIdx = 0; if (wp) { audioTrack?.pause(); audioTrack?.flush(); audioTrack?.play(); playJob = scope.launch(Dispatchers.IO) { try { streamMix(tg) } catch (_: Exception) {} }; _state.value = _state.value.copy(state = PlayerState.PLAYING, position = ps) } else _state.value = _state.value.copy(position = ps) }
    fun setVolume(n: String, v: Float) { _tracks[n] = (_tracks[n] ?: TrackUiState()).copy(volume = v) }
    fun toggleMute(n: String) { val c = _tracks[n] ?: TrackUiState(); _tracks[n] = c.copy(muted = !c.muted); syncTracks() }
    fun toggleSolo(n: String) { val c = _tracks[n] ?: TrackUiState(); _tracks[n] = c.copy(soloed = !c.soloed); syncTracks() }
    fun setMetronomeVolume(v: Float) { _metroVolume = v.coerceIn(0f, 1f); _state.value = _state.value.copy(metronomeVolume = _metroVolume) }
    fun toggleMetronomeAccent() { metronomeAccent = !metronomeAccent; prebuildMetronome(); _state.value = _state.value.copy(metronomeAccent = metronomeAccent) }
    fun toggleMetronome() { metronomeEnabled = !metronomeEnabled; _state.value = _state.value.copy(metronomeEnabled = metronomeEnabled) }
    fun setBpm(v: Float) { currentBpm = v.coerceIn(30f, 300f); prebuildMetronome(); _state.value = _state.value.copy(bpm = currentBpm) }
    private fun syncTracks() { _state.value = _state.value.copy(tracks = _tracks.toMap()) }
    fun destroy() { stop(); scope.cancel() }
}
