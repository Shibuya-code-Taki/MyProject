#!/usr/bin/env python3
# =====================================================================
# Stems Pro - ROG 本地 GPU 处理器
#
# 在 ROG Windows 上运行，使用本地 NVIDIA GPU 做音轨分离。
# 替代/补充 Google Colab，不受 Colab GPU 额度限制。
#
# 用法:
#   python local_processor.py              <- 处理所有待处理歌曲后退出
#   python local_processor.py --watch      <- 持续监听，有歌就处理
#   python local_processor.py --song 3     <- 只处理指定 ID 的歌曲
#
# 依赖 (setup.bat 一键安装):
#   - Python 3.10+
#   - PyTorch with CUDA
#   - demucs
#   - ffmpeg (放 ffmpeg.exe 到本目录，或加入系统 PATH)
#   - pycryptodome (NCM 解密)
# =====================================================================

import argparse
import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

# ============================================================
# NCM Constants (from known working implementations)
# ============================================================
CORE_KEY = bytes.fromhex("687A4852416D736F356B496E62617857")  # 16 bytes AES-128
META_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")  # 16 bytes AES-128

# ============================================================
# 配置 — 根据你的环境修改
# ============================================================
SERVER_URL = os.environ.get("STEMS_SERVER", "http://YOUR_SERVER_IP:8000")
TRACKS = ["vocals", "drums", "bass", "guitar", "piano", "other"]
POLL_INTERVAL = 15  # watch 模式下轮询间隔(秒)
FFMPEG_PATH = "ffmpeg"  # 启动时自动检测，优先用 local 目录下的单文件

# ============================================================
# 颜色输出 (Windows 10+ 支持 ANSI)
# ============================================================
GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN = "\033[96m"; BOLD = "\033[1m"; RESET = "\033[0m"


def log(msg: str, color: str = ""):
    ts = time.strftime("%H:%M:%S")
    print(f"{color}[{ts}]{RESET} {msg}", flush=True)


def check_dependencies() -> bool:
    """检查所有依赖，缺少的给安装提示。"""
    global FFMPEG_PATH

    log("=" * 55, CYAN)
    log("  Stems Pro — ROG Local GPU Processor", BOLD + CYAN)
    log("=" * 55, CYAN)

    ok = True

    # 1. Python version
    py_ver = sys.version_info
    if py_ver >= (3, 10):
        log(f"  Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}  OK", GREEN)
    else:
        log(f"  Python {py_ver.major}.{py_ver.minor} FAIL  need 3.10+", RED)
        ok = False

    # 2. PyTorch + CUDA
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        if cuda_ok:
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
            log(f"  PyTorch {torch.__version__}  |  GPU: {gpu_name} ({vram_gb:.1f} GB)  OK", GREEN)
        else:
            log(f"  PyTorch {torch.__version__}  |  CUDA: NOT FOUND  FAIL", RED)
            log(f"     pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124", YELLOW)
            ok = False
    except ImportError:
        log(f"  PyTorch: NOT INSTALLED  FAIL", RED)
        log(f"     pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124", YELLOW)
        ok = False

    # 3. demucs
    try:
        import demucs
        log(f"  demucs: installed  OK", GREEN)
    except ImportError:
        log(f"  demucs: NOT INSTALLED  FAIL", RED)
        log(f"     pip install demucs", YELLOW)
        ok = False

    # 4. ffmpeg (优先找 local 目录下的 ffmpeg.exe)
    local_ffmpeg = Path(__file__).parent / "ffmpeg.exe"
    system_ffmpeg = shutil.which("ffmpeg")
    if local_ffmpeg.exists():
        FFMPEG_PATH = str(local_ffmpeg)
        log(f"  ffmpeg: {FFMPEG_PATH} (local)  OK", GREEN)
    elif system_ffmpeg:
        FFMPEG_PATH = system_ffmpeg
        log(f"  ffmpeg: {FFMPEG_PATH}  OK", GREEN)
    else:
        log(f"  ffmpeg: NOT FOUND  FAIL", RED)
        log(f"     下载: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", YELLOW)
        log(f"     或国内镜像: https://mirror.ghproxy.com/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip", YELLOW)
        log(f"     解压后把 bin/ffmpeg.exe 复制到此目录:", YELLOW)
        log(f"     {Path(__file__).parent}", YELLOW)
        ok = False

    # 5. librosa (BPM detection)
    try:
        import librosa
        log(f"  librosa: installed  OK", GREEN)
    except ImportError:
        log(f"  librosa: NOT INSTALLED  (BPM 检测才需要)", YELLOW)
        log(f"     pip install librosa", YELLOW)

    # 6. pycryptodome (NCM decrypt)
    try:
        from Crypto.Cipher import AES
        log(f"  pycryptodome: installed  OK", GREEN)
    except ImportError:
        log(f"  pycryptodome: NOT INSTALLED  (只有 .ncm 文件才需要)", YELLOW)
        log(f"     pip install pycryptodome", YELLOW)

    # 7. requests
    try:
        import requests
        log(f"  requests: installed  OK", GREEN)
    except ImportError:
        log(f"  requests: NOT INSTALLED  FAIL", RED)
        log(f"     pip install requests", YELLOW)
        ok = False

    # 8. Server connectivity
    try:
        r = requests.get(f"{SERVER_URL}/api/stats", timeout=10)
        if r.status_code == 200:
            stats = r.json().get("data", {})
            log(f"  Server: {SERVER_URL}  ({stats.get('song_count',0)} songs) OK", GREEN)
        else:
            log(f"  Server: {SERVER_URL}  returned {r.status_code}", YELLOW)
    except Exception as e:
        log(f"  Server: {SERVER_URL}  UNREACHABLE  FAIL  ({e})", RED)
        ok = False

    print()
    return ok


# ============================================================
# NCM 解密 (与 Colab 版本相同逻辑)
# ============================================================
def pkcs7_unpad(s: bytes) -> bytes:
    """Remove PKCS#7 padding."""
    n = s[-1]
    return s[:-n]


def decrypt_ncm(ncm_path: Path, out_dir: Path) -> Path | None:
    """Standard NCM decrypt based on well-known open-source implementations."""
    from Crypto.Cipher import AES

    with open(ncm_path, "rb") as f:
        # 1. Header: CTENFDAM (8) + gap (2) + key_len (4)
        if f.read(8) != b"CTENFDAM":
            return None
        f.read(2)

        key_len = struct.unpack("<I", f.read(4))[0]

        # 2. Read key data, XOR 0x64, AES-ECB decrypt with CORE_KEY
        key_data = bytearray(f.read(key_len))
        for i in range(len(key_data)):
            key_data[i] ^= 0x64

        pad = (16 - len(key_data) % 16) % 16
        if pad:
            key_data += b"\x00" * pad

        cryptor = AES.new(CORE_KEY, AES.MODE_ECB)
        decrypted = cryptor.decrypt(bytes(key_data))

        try:
            decrypted = pkcs7_unpad(decrypted)
        except Exception:
            pass
        if decrypted[:17] != b"neteasecloudmusic":
            return None
        rc4_key = decrypted[17:]
        rc4_key_data = bytearray(rc4_key)
        key_length = len(rc4_key_data)

        # 3. Build RC4 key_box (KSA)
        key_box = bytearray(range(256))
        c = 0
        last_byte = 0
        key_offset = 0
        for i in range(256):
            swap = key_box[i]
            c = (swap + last_byte + rc4_key_data[key_offset]) & 0xFF
            key_offset += 1
            if key_offset >= key_length:
                key_offset = 0
            key_box[i] = key_box[c]
            key_box[c] = swap
            last_byte = c

        # 4. Read metadata: XOR 0x63, base64 decode, AES decrypt with META_KEY
        meta_len = struct.unpack("<I", f.read(4))[0]
        if meta_len <= 0 or meta_len > 10 * 1024 * 1024:
            return None

        meta_enc = bytearray(f.read(meta_len))
        for i in range(len(meta_enc)):
            meta_enc[i] ^= 0x63

        meta_b64 = bytes(meta_enc[22:])
        meta_aes = base64.b64decode(meta_b64)
        meta_cryptor = AES.new(META_KEY, AES.MODE_ECB)
        meta_plain = pkcs7_unpad(meta_cryptor.decrypt(meta_aes)).decode("utf-8")[6:]
        meta = json.loads(meta_plain)
        fmt = meta.get("format", "mp3")

        # 5. Skip CRC + gap + image
        f.read(4)  # CRC32
        f.read(5)  # gap
        img_len = struct.unpack("<I", f.read(4))[0]
        if img_len > 0 and img_len < 50 * 1024 * 1024:
            f.read(img_len)

        # 6. RC4 decrypt audio
        out_path = out_dir / (ncm_path.stem.replace(".ncm", "") + "." + fmt)
        with open(out_path, "wb") as of:
            while True:
                chunk = bytearray(f.read(0x8000))
                chunk_len = len(chunk)
                if not chunk_len:
                    break
                for i in range(1, chunk_len + 1):
                    j = i & 0xFF
                    chunk[i - 1] ^= key_box[(key_box[j] + key_box[(key_box[j] + j) & 0xFF]) & 0xFF]
                of.write(chunk)
        return out_path


# ============================================================
# 处理单首歌曲
# ============================================================
def detect_bpm(wav_path: str) -> float:
    """Detect BPM from a WAV file using librosa. Returns BPM or 0 on failure."""
    try:
        import librosa
        y, sr = librosa.load(wav_path, sr=22050)
        y_perc = librosa.effects.percussive(y)
        onset_env = librosa.onset.onset_strength(y=y_perc, sr=sr)
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)[0]
        while tempo < 50:
            tempo *= 2
        while tempo > 200:
            tempo /= 2
        return round(float(tempo), 1)
    except Exception as e:
        log(f"         BPM 检测跳过 ({e})", YELLOW)
        return 0


def process_song(song: dict) -> bool:
    """下载 -> 解密 -> GPU 分离 -> 上传。成功返回 True。"""
    sid = song["id"]
    title = song.get("title", "unknown")
    artist = song.get("artist", "unknown")

    log(f"{'-' * 50}", CYAN)
    log(f"  #{sid}  {title}  --  {artist}", BOLD)
    log(f"{'-' * 50}", CYAN)

    # 标记处理中
    requests.post(f"{SERVER_URL}/api/songs/{sid}/status", data={"status": "processing"})

    # 使用系统临时目录
    work = Path(tempfile.mkdtemp(prefix=f"stems_{sid}_"))
    orig = work / "original"

    try:
        # --- Step 1: Download ---
        log(f"  [1/4] 下载中...")
        r = requests.get(f"{SERVER_URL}/api/songs/{sid}/original/download", stream=True)
        r.raise_for_status()
        with open(orig, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        size_mb = orig.stat().st_size / 1024 / 1024
        log(f"         下载完成 ({size_mb:.1f} MB)")

        # --- Step 2: Decrypt NCM ---
        head = open(orig, "rb").read(8)
        if head == b"CTENFDAM":
            log(f"  [2/4] 解密 NCM...")
            decrypted = decrypt_ncm(orig, work)
            if decrypted:
                orig = decrypted
                log(f"         -> {orig.name}")
            else:
                log(f"         NCM 解密失败", RED)
        else:
            log(f"  [2/4] 非加密格式，跳过解密")

        # --- Step 3: GPU Separation ---
        log(f"  [3/4] GPU 分离中 (预计 2-5 分钟)...")
        t_start = time.time()

        result = subprocess.run([
            sys.executable, "-m", "demucs",
            "-n", "htdemucs_6s",
            "--device", "cuda",
            "--clip-mode", "clamp",
            "-o", str(work),
            str(orig)
        ], capture_output=True, text=True)

        elapsed = time.time() - t_start
        log(f"         耗时 {elapsed:.0f}s")

        if result.returncode != 0:
            log(f"  FAIL 分离失败!", RED)
            log(f"  stderr: {result.stderr[-500:]}", RED)
            requests.post(f"{SERVER_URL}/api/songs/{sid}/status", data={"status": "failed"})
            return False

        # --- Step 4: Transcode to MP3, detect BPM, upload ---
        log(f"  [4/4] 转码+BPM...")
        wav_dir = work / "htdemucs_6s" / orig.stem
        if not wav_dir.exists():
            candidates = list(work.glob("htdemucs_6s/*/vocals.wav"))
            if candidates:
                wav_dir = candidates[0].parent
            else:
                log(f"  FAIL 找不到分离结果目录!", RED)
                requests.post(f"{SERVER_URL}/api/songs/{sid}/status", data={"status": "failed"})
                return False

        # BPM detection from drums
        detected_bpm = 0
        drums_wav = wav_dir / "drums.wav"
        if drums_wav.exists():
            detected_bpm = detect_bpm(str(drums_wav))
            log(f"         BPM: {detected_bpm}", CYAN)

        for tn in TRACKS:
            wav = wav_dir / f"{tn}.wav"
            if not wav.exists():
                log(f"         {tn} — WAV 不存在", YELLOW)
                continue
            mp3 = work / f"{tn}.mp3"
            subprocess.run([
                FFMPEG_PATH, "-y", "-i", str(wav),
                "-c:a", "libmp3lame", "-b:a", "256k", str(mp3)
            ], capture_output=True)

            if mp3.exists():
                with open(mp3, "rb") as f:
                    requests.post(
                        f"{SERVER_URL}/api/songs/{sid}/tracks",
                        files={"file": (f"{tn}.mp3", f, "audio/mpeg")},
                        data={"name": tn},
                    )
                log(f"         {tn} OK  ({mp3.stat().st_size/1024/1024:.1f} MB)")
            else:
                log(f"         {tn} — ffmpeg 失败", YELLOW)

        # --- Done ---
        requests.post(f"{SERVER_URL}/api/songs/{sid}/status",
                      data={"status": "done", "bpm": str(detected_bpm)})
        log(f"  OK 完成: {title} -- {artist}  |  BPM: {detected_bpm}", GREEN)
        return True

    except Exception as e:
        log(f"  FAIL 异常: {e}", RED)
        requests.post(f"{SERVER_URL}/api/songs/{sid}/status", data={"status": "failed"})
        return False

    finally:
        shutil.rmtree(work, ignore_errors=True)


# ============================================================
# 主入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Stems Pro — ROG Local GPU Processor")
    parser.add_argument("--watch", action="store_true", help="持续监听，有歌就处理")
    parser.add_argument("--song", type=int, help="只处理指定 ID 的歌曲")
    parser.add_argument("--server", type=str, help="服务器地址 (覆盖默认)")
    args = parser.parse_args()

    global SERVER_URL
    if args.server:
        SERVER_URL = args.server

    # 检查依赖
    if not check_dependencies():
        log("依赖检查未通过，请先运行 setup.bat 安装依赖", RED)
        sys.exit(1)

    import torch
    log(f"GPU 就绪: {torch.cuda.get_device_name(0)}", GREEN)
    log(f"服务器: {SERVER_URL}", GREEN)
    print()

    # --- 单曲模式 ---
    if args.song:
        r = requests.get(f"{SERVER_URL}/api/songs/{args.song}")
        if r.status_code != 200:
            log(f"歌曲 #{args.song} 不存在", RED)
            sys.exit(1)
        song = r.json().get("data", {})
        success = process_song(song)
        sys.exit(0 if success else 1)

    # --- Watch 模式 ---
    if args.watch:
        log(f"进入 Watch 模式，每 {POLL_INTERVAL}s 检查一次...", CYAN)
        log(f"按 Ctrl+C 停止", CYAN)
        print()
        try:
            while True:
                try:
                    r = requests.get(f"{SERVER_URL}/api/songs/pending", timeout=10)
                    pending = r.json().get("data", [])
                    # 只处理状态为 pending 的
                    # 只处理已上传完成的（有 original_file 且 status=pending）
                    pending = [s for s in pending
                               if s.get("status") == "pending"
                               and s.get("original_file") is not None]
                    if pending:
                        log(f"发现 {len(pending)} 首待处理歌曲")
                        for song in pending:
                            process_song(song)
                        log(f"本轮处理完毕，继续监听...")
                    else:
                        # 静默等待
                        time.sleep(POLL_INTERVAL)
                except requests.ConnectionError:
                    log(f"无法连接服务器，30s 后重试...", YELLOW)
                    time.sleep(30)
                except Exception as e:
                    log(f"轮询异常: {e}", YELLOW)
                    time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            log(f"用户停止", YELLOW)
            sys.exit(0)

    # --- 默认: 一次性模式 ---
    log(f"一次性模式: 处理所有 pending 歌曲", CYAN)
    print()
    r = requests.get(f"{SERVER_URL}/api/songs/pending", timeout=10)
    pending = r.json().get("data", [])
    pending = [s for s in pending
               if s.get("status") == "pending"
               and s.get("original_file") is not None]

    if not pending:
        log(f"没有待处理歌曲", GREEN)
        log(f"通过 Web 播放器上传: {SERVER_URL}/player", CYAN)
        sys.exit(0)

    log(f"共 {len(pending)} 首待处理:")
    for s in pending:
        log(f"  #{s['id']}  {s.get('title','?')}  --  {s.get('artist','?')}")

    print()
    for i, song in enumerate(pending, 1):
        log(f"[{i}/{len(pending)}] 开始处理...")
        process_song(song)
        print()

    log(f"全部完成!", BOLD + GREEN)
    log(f"打开播放器: {SERVER_URL}/player", CYAN)


if __name__ == "__main__":
    main()
