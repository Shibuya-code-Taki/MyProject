#!/usr/bin/env python3
"""Stems Pro — GPU PC Local Server

A lightweight Flask server for the "no-cloud-server" setup.
GPU machine runs this, tablet connects via Tailscale VPN.

Usage:
    pip install flask
    python local_server.py                    # listen on all interfaces, port 5000
    python local_server.py --host 127.0.0.1 --port 8080
"""

import argparse
import shutil
import tempfile
import time
from pathlib import Path

from flask import Flask, request, jsonify, send_file

from local_processor import (
    check_dependencies, process_song as gpu_separate,
    SERVER_URL as _, TRACKS, GREEN, RED, CYAN, BOLD, RESET, log,
)

app = Flask(__name__)

# Files are stored in a local temp-like directory
DATA_DIR = Path(__file__).parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
STEMS_DIR = DATA_DIR / "stems"
for d in [UPLOAD_DIR, STEMS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# In-memory song DB (simple dict, survives as long as the server runs)
songs = {}
next_id = 1


@app.route("/api/stats")
def stats():
    return jsonify({"code": 0, "data": {"song_count": len(songs)}})


@app.route("/api/songs", methods=["GET"])
def list_songs():
    result = [{**s, "tracks": s.get("tracks", [])} for s in songs.values()]
    return jsonify({"code": 0, "data": {"songs": result, "total": len(result)}})


@app.route("/api/songs/pending")
def pending():
    result = [
        {**s, "original_file": str(UPLOAD_DIR / str(s["id"]) / "original.ncm")
         if (UPLOAD_DIR / str(s["id"]) / "original.ncm").exists() else None}
        for s in songs.values() if s.get("status") == "pending"
    ]
    return jsonify({"code": 0, "data": result})


@app.route("/api/songs", methods=["POST"])
def create_song():
    global next_id
    body = request.get_json(force=True)
    sid = next_id; next_id += 1
    song = {
        "id": sid, "title": body.get("title", ""), "artist": body.get("artist", ""),
        "cover_url": body.get("cover_url", ""), "bpm": 0.0, "status": "pending",
        "tracks": [],
    }
    songs[sid] = song
    (UPLOAD_DIR / str(sid)).mkdir(parents=True, exist_ok=True)
    return jsonify({"code": 0, "data": song})


@app.route("/api/songs/<int:sid>", methods=["DELETE"])
def delete_song(sid):
    songs.pop(sid, None)
    shutil.rmtree(UPLOAD_DIR / str(sid), ignore_errors=True)
    shutil.rmtree(STEMS_DIR / str(sid), ignore_errors=True)
    return jsonify({"code": 0, "message": "deleted"})


@app.route("/api/songs/<int:sid>/original", methods=["POST"])
def upload_original(sid):
    if sid not in songs:
        return jsonify({"code": 1, "message": "not found"}), 404
    f = request.files["file"]
    d = UPLOAD_DIR / str(sid); d.mkdir(parents=True, exist_ok=True)
    ext = Path(f.filename).suffix if f.filename else ".mp3"
    fp = d / f"original{ext}"
    f.save(fp)
    return jsonify({"code": 0, "message": "ok", "data": {"path": str(fp)}})


@app.route("/api/songs/<int:sid>/original/download")
def download_original(sid):
    d = UPLOAD_DIR / str(sid)
    if not d.exists():
        return "not found", 404
    files = list(d.glob("original.*"))
    if not files:
        return "not found", 404
    return send_file(str(files[0]), mimetype="audio/mpeg")


@app.route("/api/songs/<int:sid>/tracks", methods=["POST"])
def upload_track(sid):
    if sid not in songs:
        return jsonify({"code": 1, "message": "not found"}), 404
    name = request.form["name"]
    if name not in TRACKS:
        return jsonify({"code": 1, "message": "invalid track name"}), 400
    f = request.files["file"]
    d = STEMS_DIR / str(sid); d.mkdir(parents=True, exist_ok=True)
    ext = Path(f.filename).suffix if f.filename else ".mp3"
    fp = d / f"{name}{ext}"
    f.save(fp)

    # Remove old track with same name
    songs[sid]["tracks"] = [t for t in songs[sid].get("tracks", []) if t["name"] != name]
    track = {"id": len(songs[sid]["tracks"]) + 1, "song_id": sid, "name": name,
             "file_path": str(fp), "file_size": fp.stat().st_size, "duration": 0.0}
    songs[sid]["tracks"].append(track)
    return jsonify({"code": 0, "data": track})


@app.route("/api/tracks/<int:tid>/download")
def download_track(tid):
    for s in songs.values():
        for t in s.get("tracks", []):
            if t["id"] == tid:
                fp = Path(t["file_path"])
                if fp.exists():
                    ext = fp.suffix.lower()
                    mime = "audio/mpeg" if ext == ".mp3" else "audio/mp4"
                    return send_file(str(fp), mimetype=mime)
    return "not found", 404


@app.route("/api/songs/<int:sid>/status", methods=["POST"])
def update_status(sid):
    if sid not in songs:
        return jsonify({"code": 1, "message": "not found"}), 404
    songs[sid]["status"] = request.form.get("status", "pending")
    bpm = float(request.form.get("bpm", 0))
    if bpm > 0:
        songs[sid]["bpm"] = bpm
    return jsonify({"code": 0})


@app.route("/api/songs/<int:sid>/download")
def download_zip(sid):
    import io, zipfile
    d = STEMS_DIR / str(sid)
    if not d.exists():
        return "not found", 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in d.iterdir():
            if fp.is_file():
                zf.write(fp, fp.name)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip",
                     download_name=f"{songs.get(sid, {}).get('title', sid)}_stems.zip")


# ── GPU processing endpoint (optional, can also run local_processor.py separately) ──

@app.route("/api/process", methods=["POST"])
def process_one():
    """Process a single song with local GPU. Call after upload is complete."""
    sid = request.json.get("id")
    if sid not in songs:
        return jsonify({"code": 1, "message": "not found"}), 404
    song = songs[sid]
    success = gpu_separate(song)
    return jsonify({"code": 0 if success else 1, "status": songs[sid]["status"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stems Pro Local GPU Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    print(f"{CYAN}{'='*50}{RESET}")
    print(f"{BOLD}  Stems Pro — Local GPU Server{RESET}")
    print(f"{CYAN}{'='*50}{RESET}")
    print(f"  Listening on {GREEN}http://{args.host}:{args.port}{RESET}")
    print(f"  Tablet App → set server to this address (via Tailscale)")
    print()

    if not check_dependencies():
        print(f"\n{RED}Dependency check failed. Install missing packages and re-run.{RESET}")
        exit(1)

    app.run(host=args.host, port=args.port, debug=False)
