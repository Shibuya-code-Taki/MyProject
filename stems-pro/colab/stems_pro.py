#!/usr/bin/env python3
# =====================================================================
# Stems Pro - GPU Batch Processor (Colab)
#
# HOW TO USE:
# 1. Open https://colab.research.google.com (NEW notebook)
# 2. Runtime > Change runtime type > T4 GPU > Save
# 3. Create 4 code cells, paste each CELL section below
# 4. Runtime > Run all
# =====================================================================

SERVER_URL = "http://YOUR_SERVER_IP:8000"
TRACKS = ['vocals','drums','bass','guitar','piano','other']


# #####################################################################
# CELL 1 of 4 — Install dependencies
# #####################################################################
!pip install -q demucs pycryptodome librosa
!apt-get update -qq && apt-get install -y -qq ffmpeg > /dev/null 2>&1


# #####################################################################
# CELL 2 of 4 — Imports + GPU check + NCM decrypt function
# #####################################################################
import requests, subprocess, shutil, os, struct, torch, json, base64
from pathlib import Path
from Crypto.Cipher import AES

assert torch.cuda.is_available(), "NO GPU! Go to Runtime > Change runtime type > T4 GPU"
print(f"GPU: {torch.cuda.get_device_name(0)}")

# === NCM Constants (from known working implementations) ===
CORE_KEY = bytes.fromhex("687A4852416D736F356B496E62617857")  # 16 bytes AES-128
META_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")  # 16 bytes AES-128

def pkcs7_unpad(s: bytes) -> bytes:
    """Remove PKCS#7 padding."""
    n = s[-1]
    return s[:-n]

def decrypt_ncm(ncm_path, out_dir):
    """Correct NCM decrypt based on well-known open-source implementations."""
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

        # Pad to 16-byte boundary if needed
        pad = (16 - len(key_data) % 16) % 16
        if pad:
            key_data += b"\x00" * pad

        cryptor = AES.new(CORE_KEY, AES.MODE_ECB)
        decrypted = cryptor.decrypt(bytes(key_data))

        # Unpad and skip "neteasecloudmusic" prefix (17 bytes)
        try:
            decrypted = pkcs7_unpad(decrypted)
        except Exception:
            pass
        if decrypted[:17] != b"neteasecloudmusic":
            return None
        rc4_key = decrypted[17:]
        rc4_key_data = bytearray(rc4_key)
        key_length = len(rc4_key_data)

        # 3. Build RC4 key_box (KSA - standard for NCM)
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

        # 4. Read metadata: XOR 0x63, then base64 decode, then AES+meta_key decrypt
        meta_len = struct.unpack("<I", f.read(4))[0]
        if meta_len <= 0 or meta_len > 10 * 1024 * 1024:
            return None

        meta_enc = bytearray(f.read(meta_len))
        for i in range(len(meta_enc)):
            meta_enc[i] ^= 0x63

        # Base64 decode (skip first 22 bytes — "163 key(Don't modify):")
        meta_b64 = bytes(meta_enc[22:])
        meta_aes = base64.b64decode(meta_b64)
        meta_cryptor = AES.new(META_KEY, AES.MODE_ECB)
        meta_plain = pkcs7_unpad(meta_cryptor.decrypt(meta_aes)).decode("utf-8")[6:]
        meta = json.loads(meta_plain)
        fmt = meta.get("format", "mp3")

        # 5. Skip CRC (4 bytes) + 5 gap bytes, then read image
        f.read(4)  # CRC32
        f.read(5)  # gap

        img_len = struct.unpack("<I", f.read(4))[0]
        if img_len > 0 and img_len < 50 * 1024 * 1024:
            f.read(img_len)

        # 6. RC4 decrypt audio
        out_path = os.path.join(out_dir, os.path.basename(ncm_path).replace(".ncm", "") + "." + fmt)
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

print("Ready!")

def detect_bpm(wav_path):
    """Detect BPM from a WAV file using librosa. Uses harmonic-percussive separation
    on the drum track for best accuracy. Returns BPM (float) or 0 on failure."""
    try:
        import librosa
        y, sr = librosa.load(wav_path, sr=22050)
        # Use HPSS to isolate percussive component (drums = best for tempo)
        y_perc = librosa.effects.percussive(y)
        onset_env = librosa.onset.onset_strength(y=y_perc, sr=sr)
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)[0]
        # Octave correction: bring into typical range (50-200 BPM)
        while tempo < 50:
            tempo *= 2
        while tempo > 200:
            tempo /= 2
        return round(float(tempo), 1)
    except Exception as e:
        print(f"         BPM detection skipped ({e})")
        return 0


# #####################################################################
# CELL 3 of 4 — Fetch pending songs from server
# #####################################################################
r = requests.get(f"{SERVER_URL}/api/songs/pending")
pending = r.json().get("data", [])
print(f"Pending songs: {len(pending)}")
for s in pending:
    print(f"  #{s['id']}  {s['title']}  --  {s['artist']}  status={s.get('status','?')}")


# #####################################################################
# CELL 4 of 4 — Process all pending songs (download > decrypt > GPU separate > upload)
# #####################################################################

# Known audio magic bytes for format detection
AUDIO_MAGIC = {
    b'\xff\xfb': 'MP3',
    b'\xff\xf3': 'MP3',
    b'\xff\xf2': 'MP3',
    b'ID3': 'MP3 (ID3 tag)',
    b'RIFF': 'WAV',
    b'ftyp': 'M4A/MP4',
    b'fLaC': 'FLAC',
    b'OggS': 'OGG',
    b'CTENFDAM': 'NCM encrypted',
}

def identify_format(data):
    for magic, name in AUDIO_MAGIC.items():
        if data.startswith(magic):
            return name
    return 'UNKNOWN'

def process(song):
    sid = song["id"]
    title = song["title"]
    print(f"\n{'='*50}")
    print(f"  #{sid}  {title}")
    print(f"{'='*50}")
    requests.post(f"{SERVER_URL}/api/songs/{sid}/status", data={"status":"processing"})

    work = Path(f"/content/p{sid}")
    work.mkdir(exist_ok=True)
    orig = work / "original"

    # Step 1: Download
    print("  [1/4] Downloading...")
    r = requests.get(f"{SERVER_URL}/api/songs/{sid}/original/download", stream=True)
    ct = r.headers.get("Content-Type", "?")
    print(f"         Content-Type: {ct}")
    with open(orig, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    size_mb = orig.stat().st_size / 1024 / 1024

    # Read magic bytes
    with open(orig, "rb") as f:
        magic = f.read(32)
    fmt_name = identify_format(magic)
    print(f"         Size: {size_mb:.1f} MB  |  Format: {fmt_name}")
    print(f"         First 16 bytes: {magic[:16].hex(' ')}")

    # Step 2: Decrypt if needed
    if magic[:8] == b"CTENFDAM":
        print("  [2/4] Decrypting NCM...")
        decrypted = decrypt_ncm(str(orig), str(work))
        if decrypted:
            orig = Path(decrypted)
            print(f"         -> {orig.name}")
        else:
            print(f"         NCM decrypt FAILED!")
            requests.post(f"{SERVER_URL}/api/songs/{sid}/status", data={"status":"failed"})
            return
    elif fmt_name == 'UNKNOWN':
        print(f"  [2/4] UNKNOWN FORMAT! Cannot process.")
        print(f"         This file is not a supported audio format.")
        print(f"         It may be .qmc/.kgm/.mgg/.xm encrypted (not yet supported)")
        print(f"         Full first 32 bytes: {magic.hex(' ')}")
        requests.post(f"{SERVER_URL}/api/songs/{sid}/status", data={"status":"failed"})
        return
    else:
        print(f"  [2/4] {fmt_name} format, skip decrypt")

    # Step 3: GPU separation
    print("  [3/4] GPU separating (this takes 2-5 min)...")
    t0 = __import__('time').time()
    result = subprocess.run([
        "python3", "-m", "demucs",
        "-n", "htdemucs_6s",
        "--device", "cuda",
        "--clip-mode", "clamp",
        "--shifts", "1",
        "-j", "2",
        "-o", str(work),
        str(orig)
    ], capture_output=True, text=True)
    elapsed = __import__('time').time() - t0
    print(f"         Elapsed: {elapsed:.0f}s")

    if result.returncode != 0:
        print(f"  FAILED!")
        print(f"  STDERR: {result.stderr[-600:]}")
        print(f"  STDOUT: {result.stdout[-600:]}")
        requests.post(f"{SERVER_URL}/api/songs/{sid}/status", data={"status":"failed"})
        return

    # Step 4: Transcode to MP3 and upload + detect BPM
    print("  [4/4] Transcoding + BPM...")
    wav_dir = work / "htdemucs_6s" / orig.stem
    if not wav_dir.exists():
        candidates = list(work.glob("htdemucs_6s/*/vocals.wav"))
        if candidates:
            wav_dir = candidates[0].parent

    # Detect BPM from drums WAV (best accuracy)
    detected_bpm = 0
    drums_wav = wav_dir / "drums.wav"
    if drums_wav.exists():
        detected_bpm = detect_bpm(str(drums_wav))
        print(f"         BPM: {detected_bpm}")

    for tn in TRACKS:
        wav = wav_dir / f"{tn}.wav"
        if not wav.exists():
            print(f"         {tn} -- WAV missing, skip")
            continue
        mp3 = work / f"{tn}.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "256k", str(mp3)],
            capture_output=True
        )
        if mp3.exists():
            with open(mp3, "rb") as f:
                requests.post(
                    f"{SERVER_URL}/api/songs/{sid}/tracks",
                    files={"file": (f"{tn}.mp3", f, "audio/mpeg")},
                    data={"name": tn}
                )
            print(f"         {tn} OK")
        else:
            print(f"         {tn} -- ffmpeg transcoding FAILED")

    # Done — post status with BPM
    requests.post(f"{SERVER_URL}/api/songs/{sid}/status",
                  data={"status": "done", "bpm": str(detected_bpm)})
    shutil.rmtree(work, ignore_errors=True)
    print(f"  DONE: {title}  |  BPM: {detected_bpm}")


if not pending:
    print("\nNo pending songs. Upload some from the App first!")
else:
    for song in pending:
        process(song)
    print(f"\n{'='*50}")
    print(f"  ALL {len(pending)} SONGS DONE!")
    print(f"{'='*50}")
