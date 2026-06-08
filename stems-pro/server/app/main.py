"""Stems Pro — FastAPI application entry point.

Song CRUD API + Track upload/download.
"""

import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import Song, Track
from .schemas import ApiResponse, SongCreate, SongUpdate, SongResponse, TrackInfo
from .admin import admin_router

# ——— Config ———
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORAGE_DIR = BASE_DIR / "storage"
TRACK_NAMES = ["vocals", "drums", "bass", "guitar", "piano", "other"]

app = FastAPI(title="Stems Pro API", version="0.1.0")

# CORS — allow all origins during dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount admin routes
app.mount("/admin", admin_router)


@app.on_event("startup")
def startup():
    init_db()


# ═══════════════════════════════════════════════════
#  Song CRUD
# ═══════════════════════════════════════════════════

@app.get("/api/songs")
def list_songs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search title/artist"),
    db: Session = Depends(get_db),
):
    q = db.query(Song)
    if search:
        like = f"%{search}%"
        q = q.filter((Song.title.ilike(like)) | (Song.artist.ilike(like)))
    total = q.count()
    songs = q.order_by(Song.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for s in songs:
        d = s.to_dict()
        d["tracks"] = [t.to_dict() for t in s.tracks]
        result.append(d)

    return {
        "code": 0,
        "message": "success",
        "data": {
            "songs": result,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@app.get("/api/songs/{song_id}")
def get_song(song_id: int, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    d = song.to_dict()
    d["tracks"] = [t.to_dict() for t in song.tracks]
    return {"code": 0, "message": "success", "data": d}


@app.post("/api/songs")
def create_song(body: SongCreate, db: Session = Depends(get_db)):
    song = Song(title=body.title, artist=body.artist, cover_url=body.cover_url)
    db.add(song)
    db.commit()
    db.refresh(song)

    # Create storage directory
    song_dir = STORAGE_DIR / str(song.id)
    song_dir.mkdir(parents=True, exist_ok=True)

    return {"code": 0, "message": "success", "data": song.to_dict()}


@app.put("/api/songs/{song_id}")
def update_song(song_id: int, body: SongUpdate, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    if body.title is not None:
        song.title = body.title
    if body.artist is not None:
        song.artist = body.artist
    if body.cover_url is not None:
        song.cover_url = body.cover_url
    db.commit()
    db.refresh(song)
    return {"code": 0, "message": "success", "data": song.to_dict()}


@app.delete("/api/songs/{song_id}")
def delete_song(song_id: int, db: Session = Depends(get_db)):
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    # Remove files on disk
    song_dir = STORAGE_DIR / str(song_id)
    if song_dir.exists():
        shutil.rmtree(song_dir)

    db.delete(song)
    db.commit()
    return {"code": 0, "message": "deleted"}


# ═══════════════════════════════════════════════════
#  Track upload / download
# ═══════════════════════════════════════════════════

@app.post("/api/songs/{song_id}/tracks")
def upload_track(
    song_id: int,
    file: UploadFile = File(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    """Upload a single track for a song."""
    if name not in TRACK_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid track name. Must be one of: {TRACK_NAMES}")

    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    # Deduplicate: delete old track with same name
    old = db.query(Track).filter(Track.song_id == song_id, Track.name == name).first()
    if old:
        old_path = Path(old.file_path)
        if old_path.exists():
            old_path.unlink()
        db.delete(old)

    # Save file
    song_dir = STORAGE_DIR / str(song_id)
    song_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix if file.filename else ".m4a"
    filename = f"{name}{ext}"
    file_path = song_dir / filename

    with open(file_path, "wb") as f:
        f.write(file.filename and file.file.read())

    track = Track(
        song_id=song_id,
        name=name,
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    return {"code": 0, "message": "uploaded", "data": track.to_dict()}


@app.post("/api/songs/{song_id}/tracks/batch")
async def batch_upload_tracks(
    song_id: int,
    db: Session = Depends(get_db),
):
    """Batch upload endpoint — use multipart with multiple files.

    Client sends: files[] (up to 6) with filenames like "vocals.m4a", "drums.m4a", etc.
    Actually we use a simpler approach — see the single upload endpoint above.
    """
    # This is a placeholder; batch upload via multipart is complex in FastAPI.
    # The Android app calls the single upload endpoint for each track.
    raise HTTPException(status_code=501, detail="Use single track upload endpoint")


@app.get("/api/songs/{song_id}/download")
def download_song_zip(song_id: int, db: Session = Depends(get_db)):
    """Download all tracks of a song as a zip file.

    For the Android app — download individual tracks via /api/tracks/{track_id}/download.
    """
    import zipfile
    import io

    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    if not song.tracks:
        raise HTTPException(status_code=404, detail="No tracks found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for t in song.tracks:
            fp = Path(t.file_path)
            if fp.exists():
                zf.write(fp, fp.name)
    buf.seek(0)

    return FileResponse(
        buf,
        media_type="application/zip",
        filename=f"{song.title or song.id}_stems.zip",
    )


@app.get("/api/tracks/{track_id}/download")
def download_track(track_id: int, db: Session = Depends(get_db)):
    """Download a single track file."""
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    file_path = Path(track.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        str(file_path),
        media_type="audio/mp4",
        filename=f"{track.song.title}_{track.name}{file_path.suffix}",
    )


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Simple server stats."""
    song_count = db.query(Song).count()
    track_count = db.query(Track).count()
    total_size = 0
    for t in db.query(Track).all():
        fp = Path(t.file_path)
        if fp.exists():
            total_size += fp.stat().st_size
    return {
        "code": 0,
        "data": {
            "song_count": song_count,
            "track_count": track_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
        },
    }
