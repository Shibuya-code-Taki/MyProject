"""Web admin panel for Stems Pro — Jinja2 + FastAPI sub-application."""

import os
import shutil
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import get_db
from .models import Song, Track

TRACK_NAMES = ["vocals", "drums", "bass", "guitar", "piano", "other"]

# Shared storage directory (under server/)
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORAGE_DIR = BASE_DIR / "storage"

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

admin_router = FastAPI(title="Stems Pro Admin", include_in_schema=False)

# Mount static files within the admin sub-app
admin_router.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="admin_static")


@admin_router.get("/", response_class=HTMLResponse)
def admin_home(request: Request, db: Session = Depends(get_db)):
    """Render the admin panel."""
    songs = db.query(Song).order_by(Song.created_at.desc()).all()
    song_list = []
    for s in songs:
        d = s.to_dict()
        tracks = db.query(Track).filter(Track.song_id == s.id).all()
        d["tracks"] = [t.to_dict() for t in tracks]
        d["track_count"] = len(tracks)
        total_size = sum(t.file_size or 0 for t in tracks)
        d["total_size_mb"] = round(total_size / 1024 / 1024, 2) if total_size else 0
        song_list.append(d)

    stats = {
        "song_count": len(songs),
        "track_count": db.query(Track).count(),
        "storage_used_mb": round(
            sum(t.file_size or 0 for t in db.query(Track).all()) / 1024 / 1024, 2
        ),
    }

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "songs": song_list,
            "stats": stats,
            "track_names": TRACK_NAMES,
        },
    )


@admin_router.post("/songs/add")
def admin_add_song(
    title: str = Form(...),
    artist: str = Form(""),
    db: Session = Depends(get_db),
):
    """Quick add song from admin panel."""
    song = Song(title=title, artist=artist)
    db.add(song)
    db.commit()
    return RedirectResponse("/admin/", status_code=303)


@admin_router.post("/songs/{song_id}/delete")
def admin_delete_song(song_id: int, db: Session = Depends(get_db)):
    """Delete song from admin panel."""
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404)

    song_dir = STORAGE_DIR / str(song_id)
    if song_dir.exists():
        shutil.rmtree(song_dir)

    db.delete(song)
    db.commit()
    return RedirectResponse("/admin/", status_code=303)


@admin_router.post("/songs/{song_id}/edit")
def admin_edit_song(
    song_id: int,
    title: str = Form(...),
    artist: str = Form(""),
    db: Session = Depends(get_db),
):
    """Edit song metadata from admin panel."""
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404)
    song.title = title
    song.artist = artist
    db.commit()
    return RedirectResponse("/admin/", status_code=303)


@admin_router.post("/songs/{song_id}/upload-track")
def admin_upload_track(
    song_id: int,
    file: UploadFile = File(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    """Upload a single track from admin panel."""
    if name not in TRACK_NAMES:
        raise HTTPException(status_code=400)

    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404)

    # Dedup
    old = db.query(Track).filter(Track.song_id == song_id, Track.name == name).first()
    if old:
        old_path = Path(old.file_path)
        if old_path.exists():
            old_path.unlink()
        db.delete(old)

    song_dir = STORAGE_DIR / str(song_id)
    song_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix if file.filename else ".m4a"
    filename = f"{name}{ext}"
    file_path = song_dir / filename

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    track = Track(
        song_id=song_id,
        name=name,
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
    )
    db.add(track)
    db.commit()
    return RedirectResponse("/admin/", status_code=303)
