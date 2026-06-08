# 🎸 Stems Pro

> AI-powered stem separation — upload a song, get 6 isolated tracks, play them back in perfect sync with mute/solo/metronome.

## Deployment Options

**5 configurations, from zero-cost to fully hands-off:**

| # | Setup | GPU | Needs Cloud Server | Monthly Cost | Remote Access | Best For |
|---|-------|-----|-------------------|-------------|---------------|----------|
| ① | Cloud Server + Local GPU | Your PC | ✅ 2c/6G VPS | ~$5 | ✅ | Set it and forget it |
| ② | Cloud Server + Colab | Colab T4 | ✅ 2c/6G VPS | ~$5 | ✅ | No NVIDIA GPU needed |
| ③ | Tailscale P2P | Your PC | ❌ | Free | ✅ | Zero cost, direct connection |
| ④ | Cloudflare Tunnel | Your PC | ❌ | Free | ✅ | Works behind any firewall |
| ⑤ | Fully Offline | Your PC | ❌ | Free | ❌ | No network at all |

**Options ③④ are ready to run** with `local/local_server.py` — a single `python local_server.py` command.

```
        ┌──── Android App ───────────────────────────┐
        │  Pick .ncm → Upload → Wait → Download → Play │
        └──────────────────┬──────────────────────────┘
                           │
        ┌──────────────────┴──────────────────────────┐
        │  ①②: Cloud server relay                     │
        │  ③:   Tailscale P2P direct                  │
        │  ④:   Cloudflare HTTPS tunnel               │
        │  ⑤:   USB drive / LAN share                 │
        └──────────────────┬──────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │  GPU Separation │
                    │  Demucs v4      │
                    │  6 tracks MP3   │
                    └─────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Separation | Demucs v4 (htdemucs_6s) |
| GPU Compute | Google Colab (T4) / Local NVIDIA GPU |
| Server | FastAPI + SQLite (cloud) / Flask (serverless) |
| Android App | Kotlin + Jetpack Compose + MediaCodec |
| NCM Decrypt | Pure Python (pycryptodome) |
| BPM Detection | librosa (HPSS + onset + octave correction) |

## Project Structure

```
stems-pro/
├── colab/
│   ├── stems_pro.py                    # Colab 4-cell batch processor
│   └── Stems_Pro_GPU_Separation.ipynb
├── local/
│   ├── local_processor.py              # Windows local GPU processor
│   ├── local_server.py                 # Flask mini-server (for options ③④)
│   ├── run.bat                         # One-click launcher
│   └── setup.bat                       # Dependency installer
├── server/
│   ├── fix_server_final.py             # One-command server deploy (options ①②)
│   ├── run.py                          # FastAPI entry point
│   ├── stems.service                   # systemd unit file
│   └── app/
│       ├── main.py                     # API routes
│       ├── models.py                   # ORM models
│       ├── database.py                 # SQLite connection
│       ├── schemas.py                  # Pydantic validation
│       ├── admin.py                    # Admin dashboard
│       └── templates/admin.html
└── android/StemsPro/                   # Android App (Kotlin/Compose)
    └── app/src/main/java/com/stemspro/app/
        ├── player/
        │   ├── MultiTrackPlayer.kt     # Mix engine (pre-decode + phase-counter metronome)
        │   └── AudioDecoder.kt         # MediaCodec → PCM ShortArray
        ├── data/
        │   ├── api/StemsApi.kt         # Retrofit API interface
        │   ├── repository/             # Data layer
        │   └── local/AppDatabase.kt    # Room cache
        ├── ui/screens/
        │   ├── LibraryScreen.kt        # Song list
        │   ├── PlayerScreen.kt         # Player (BPM hold-to-repeat)
        │   └── UploadScreen.kt         # Upload screen
        └── di/AppContainer.kt          # Manual DI container
```

## Deployment

### Option ① Cloud Server + Local GPU

**Server:**
```bash
# Upload server/fix_server_final.py to /tmp/
python3 /tmp/fix_server_final.py && systemctl restart stems
```

**GPU PC (at home):**
```bash
setup.bat              # Install dependencies (once)
run.bat                # Process all pending songs, then exit
run.bat --watch        # Keep watching, auto-process new uploads
```

### Option ② Cloud Server + Colab

Same server setup as above. Open `colab/stems_pro.py`, paste each CELL into Colab (Runtime → T4 GPU), Run all.

### Option ③ Tailscale P2P (No Server)

```
Home (GPU PC)                       Classroom (Tablet)
     │                                    │
     └───── Tailscale P2P ── Internet ────┘
                     │
          Virtual IP: 100.x.x.x
          Like being on the same LAN
```

1. Sign up for [Tailscale](https://tailscale.com) (free for up to 3 users). Install the client on both your GPU PC and tablet. Log into the same account.
2. On your GPU PC, start the local server:
   ```bash
   pip install flask
   python local/local_server.py --host 0.0.0.0 --port 5000
   ```
3. In the App, set the server address to your GPU PC's Tailscale IP, e.g. `http://100.64.32.17:5000`

Tailscale prioritizes P2P direct connections (low latency, no third-party relay). If the school network blocks UDP, it automatically falls back to DERP relay over HTTPS port 443.

### Option ④ Cloudflare Tunnel (Ultimate Firewall Bypass)

```bash
winget install cloudflare.cloudflared
cloudflared tunnel --url http://localhost:5000
# Output: https://stems-pro-try.trycloudflare.com
```

Point the App at that URL. Uses HTTPS 443 — works under any network policy. The URL changes each restart, but it's fine for a study session.

### Option ⑤ Fully Offline

Run `local_processor.py` on your GPU PC to process `.ncm` files. Copy the stems via USB drive or LAN share. App plays local WAV/MP3 files directly.

## API

All deployment options share the same REST API:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/songs` | List songs |
| GET | `/api/songs/pending` | Songs awaiting processing |
| POST | `/api/songs` | Create song |
| DELETE | `/api/songs/{id}` | Delete song |
| POST | `/api/songs/{id}/tracks` | Upload a stem track |
| POST | `/api/songs/{id}/original` | Upload original audio file |
| GET | `/api/songs/{id}/original/download` | Download original file |
| GET | `/api/songs/{id}/download` | Download all stems as ZIP |
| GET | `/api/tracks/{id}/download` | Download single track |
| POST | `/api/songs/{id}/status` | Update status + BPM |
| GET | `/api/stats` | Server statistics |

## Technical Challenges & Solutions

### 1. NCM File Decryption (Wrong AES Key)

**Problem:** NCM decryption failed — AES-ECB output didn't contain `neteasecloudmusic` marker.

**Root Cause:** The AES key used early in development was incorrect. The wrong key was `687A4852416D626F526E68394D41454B4B`; the correct one is `687A4852416D736F356B496E62617857`. They look similar as hex but differ in 8 of 16 bytes.

**Solution:** Found the correct CORE_KEY and META_KEY from the ncmdump open-source project. NCM file structure: `CTENFDAM(8) + gap(2) + key_len(4) + key_data + metadata + image + RC4-encrypted audio`. The key is XOR'd with 0x64, then AES-ECB decrypted. The 17 bytes after `neteasecloudmusic` form the RC4 key.

### 2. Android Playback — No Sound

**Problem:** After downloading stems, pressing Play produced no sound. UI showed "Playing" but the progress bar didn't move.

**Root Cause:** `play()` called `stop()` internally, and `stop()` executed `paths.clear()`. The 6 file paths loaded by `loadPaths()` were instantly wiped.

**Solution:** `play()` no longer calls `stop()`. Instead, it manually cleans up the previous `playJob` and `AudioTrack` while preserving `paths`. A `wasStopped` flag determines whether to reset `currentFrame`.

### 3. Stuttering — 6×MediaCodec Real-time Decoding

**Problem:** Intermittent audio dropouts during playback, especially noticeable on dense music (metal, orchestral).

**Root Cause:** The `streamMix()` loop ran 6 `MediaCodec` instances simultaneously. Each 4096-sample cycle required 6 `dequeueOutputBuffer()` blocking calls. Six decoders competing for hardware resources caused cumulative latency exceeding the buffer duration.

**Attempted fixes:**
- Larger buffers (4096→8192→32768): At 32768 samples the total buffer was ~1.5 seconds, but the instantaneous CPU spike from 6 concurrent decoders still caused frame drops
- ArrayDeque ring buffer: Reduced allocation overhead, but decoder scheduling latency was the real bottleneck

**Final Solution — Pre-decode to memory:** `AudioDecoder.decode()` decodes each track sequentially (one `MediaCodec` at a time) into a `ShortArray`. Playback reads directly from memory arrays with zero decoding calls. Both the BASS Audio Library and Android SoundPool documentation recommend this approach. 6 tracks ≈ 120MB — well within modern phone memory.

### 4. Low Mix Volume

**Problem:** The 6-track mix was significantly quieter than the original song.

**Root Cause (3 factors):**
- Stereo downmix: `(L+R)/2` → -6dB
- Track mixing: `mixBuf[i] / active` dividing by 6 → -15dB
- Demucs default `--clip-mode rescale` independently attenuates each stem

**Solution:**
- Downmix: `L+R` without dividing by 2 (32-bit `IntArray` won't overflow with 6 stereo stems)
- Mix: Direct sum with `coerceIn` hard-clip safety net
- Demucs parameter: `--clip-mode clamp` instead of rescale

### 5. NCM Upload Race Condition

**Problem:** ROG watch mode detected a new song and immediately began downloading it, but the tablet hadn't finished uploading the `.ncm` file yet.

**Solution:** The watch loop now checks both `status == "pending"` AND `original_file is not None` before starting GPU processing.

### 6. MediaCodec Deadlock (INFO_OUTPUT_FORMAT_CHANGED)

**Problem:** `MediaCodec` occasionally got stuck in an infinite loop while decoding MP3.

**Root Cause:** `dequeueOutputBuffer()` returns `INFO_OUTPUT_FORMAT_CHANGED (-2)` when the codec output format changes. The code did not handle this return value, so the loop kept spinning with no progress.

**Solution:** Added a complete `when` branch to handle all possible `outIdx` values.

### 7. Metronome — No Sound + No Accent Distinction

**Problem:** Metronome toggle produced no audible clicks. When accent was enabled, all 4 beats sounded identical.

**Root Cause:** The click sample array covered the entire bar (`metroClicks = ShortArray(barLen)`) but only position 0 was filled; beats 2-4 had zero samples. Additionally, `prebuildMetronome()` only generated one click type (accent OR normal via if-else), so all beats used the same sample.

**Solution:** Split into two arrays: `metroClickAccent` (1800Hz, beat-0) and `metroClickSamples` (1200Hz, beats 1-3). Both are always generated. The injection loop selects accent on `beatIdx % 4 == 0`, normal otherwise.

### 8. Metronome Timing Drift

**Problem:** Metronome clicks drifted out of sync with the music — getting worse over time, completely wrong after seeking.

**Root Cause:** Beat position was calculated using absolute frame position: `beatIdx = gf / metroBeatLen`. This anchored the beat grid at frame 0 of the audio file. Integer `metroBeatLen` caused accumulating error. After `seek()`, `gf` jumped to a non-beat-aligned frame, causing complete misalignment.

**Solution:** Replaced with a phase counter:
```
metroPhase++ each sample
when metroPhase >= metroBeatLen: metroPhase=0, metroBeatIdx=(beatIdx+1)%4
click injected while metroPhase < clickLen, phase-0 = exact beat boundary
on seek/stop: metroPhase=0, metroBeatIdx=0
on BPM change: if (metroPhase >= metroBeatLen) { reset }
```
Benefits:
- **Zero drift:** Each beat is exactly `metroBeatLen` samples; integer truncation affects only the last beat tail (< 1 sample error, inaudible)
- **Instant alignment after seek:** Phase resets to 0, next beat starts at seek position
- **Sample-accurate:** Click injection and audio data share the same buffer → same frame → same `write()` call, guaranteeing perfect sync

### 9. Android Storage Permissions

**Problem:** Old version stored downloaded tracks in `/sdcard/Music/StemsPro/`, failing silently on some devices.

**Solution:** Switched to app-internal storage `context.filesDir/tracks/{songId}/`. No permissions required. Cleaned automatically on uninstall.

## App Features

- 🎧 6-track synchronized playback (pre-decode + memory mixing)
- 🔊 Per-track volume sliders
- 🔇 Mute / 🎸 Solo per track
- 🥁 Metronome (on/off + volume + accent + sample-accurate phase sync)
- ⏱️ BPM display + slider + hold ± buttons (auto-accelerate)
- 📥 One-tap ZIP download
- 📤 Upload songs (auto-decrypt .ncm NetEase Cloud Music format)
- 🗑️ Delete songs

## License

MIT
