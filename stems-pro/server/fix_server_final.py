"""Complete server rewrite with correct route ordering and upload support.
Copy to server and run: python3 /tmp/fix_server_final.py && systemctl restart stems
"""
import os

BASE = '/server/stems_project/app'
os.makedirs(BASE, exist_ok=True)

with open(BASE + '/main.py', 'w') as f:
    f.write('''
import os, shutil
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db, init_db, engine
from app.models import Song, Track
from app.schemas import SongCreate, SongUpdate
from app.admin import admin_router

BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORAGE_DIR = BASE_DIR / "storage"
ORIGINAL_DIR = BASE_DIR / "uploads"
ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
TRACK_NAMES = ["vocals","drums","bass","guitar","piano","other"]

app = FastAPI(title="Stems Pro API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/admin", admin_router)

@app.on_event("startup")
def startup():
    init_db()
    for col in [("status","pending"),("bpm",0.0)]:
        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE songs ADD COLUMN {col[0]} DEFAULT '{col[1]}'"))
                conn.commit()
        except: pass

# ⚠️ CRITICAL: /pending MUST come before /{song_id}

@app.get("/api/songs/pending")
def get_pending(db:Session=Depends(get_db)):
    songs=db.query(Song).all()
    result=[]
    for s in songs:
        od=ORIGINAL_DIR/str(s.id)
        orig_file=None
        if od.exists():
            files=list(od.glob("original.*"))
            if files: orig_file=str(files[0])
        d=s.to_dict()
        d["original_file"]=orig_file
        result.append(d)
    return {"code":0,"data":result}

@app.get("/api/songs")
def list_songs(page:int=1,page_size:int=50,search:Optional[str]=None,db:Session=Depends(get_db)):
    q=db.query(Song)
    if search:
        like=f"%{search}%"
        q=q.filter((Song.title.ilike(like))|(Song.artist.ilike(like)))
    total=q.count()
    songs=q.order_by(Song.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    result=[]
    for s in songs:
        d=s.to_dict()
        d["tracks"]=[t.to_dict() for t in s.tracks]
        result.append(d)
    return {"code":0,"data":{"songs":result,"total":total,"page":page,"page_size":page_size}}

@app.get("/api/songs/{song_id}")
def get_song(song_id:int,db:Session=Depends(get_db)):
    song=db.query(Song).filter(Song.id==song_id).first()
    if not song: raise HTTPException(404)
    d=song.to_dict()
    d["tracks"]=[t.to_dict() for t in song.tracks]
    return {"code":0,"data":d}

@app.post("/api/songs")
def create_song(body:SongCreate,db:Session=Depends(get_db)):
    song=Song(title=body.title,artist=body.artist,cover_url=body.cover_url,bpm=body.bpm)
    db.add(song);db.commit();db.refresh(song)
    (STORAGE_DIR/str(song.id)).mkdir(parents=True,exist_ok=True)
    return {"code":0,"data":song.to_dict()}

@app.put("/api/songs/{song_id}")
def update_song(song_id:int,body:SongUpdate,db:Session=Depends(get_db)):
    song=db.query(Song).filter(Song.id==song_id).first()
    if not song: raise HTTPException(404)
    if body.title is not None: song.title=body.title
    if body.artist is not None: song.artist=body.artist
    if body.cover_url is not None: song.cover_url=body.cover_url
    if body.bpm is not None: song.bpm=body.bpm
    db.commit();db.refresh(song)
    return {"code":0,"data":song.to_dict()}

@app.delete("/api/songs/{song_id}")
def delete_song(song_id:int,db:Session=Depends(get_db)):
    song=db.query(Song).filter(Song.id==song_id).first()
    if not song: raise HTTPException(404)
    sd=STORAGE_DIR/str(song_id)
    if sd.exists(): shutil.rmtree(sd)
    od=ORIGINAL_DIR/str(song_id)
    if od.exists(): shutil.rmtree(od)
    db.delete(song);db.commit()
    return {"code":0,"message":"deleted"}

@app.post("/api/songs/{song_id}/tracks")
def upload_track(song_id:int,file:UploadFile=File(...),name:str=Form(...),db:Session=Depends(get_db)):
    if name not in TRACK_NAMES: raise HTTPException(400)
    song=db.query(Song).filter(Song.id==song_id).first()
    if not song: raise HTTPException(404)
    old=db.query(Track).filter(Track.song_id==song_id,Track.name==name).first()
    if old:
        op=Path(old.file_path)
        if op.exists(): op.unlink()
        db.delete(old)
    song_dir=STORAGE_DIR/str(song_id)
    song_dir.mkdir(parents=True,exist_ok=True)
    ext=Path(file.filename).suffix if file.filename else ".mp3"
    fp=song_dir/(name+ext)
    with open(fp,"wb") as f: f.write(file.file.read())
    track=Track(song_id=song_id,name=name,file_path=str(fp),file_size=fp.stat().st_size)
    db.add(track);db.commit();db.refresh(track)
    return {"code":0,"data":track.to_dict()}

@app.get("/api/tracks/{track_id}/download")
def download_track(track_id:int,db:Session=Depends(get_db)):
    track=db.query(Track).filter(Track.id==track_id).first()
    if not track: raise HTTPException(404)
    fp=Path(track.file_path)
    if not fp.exists(): raise HTTPException(404)
    ext=fp.suffix.lower()
    mime="audio/mpeg" if ext==".mp3" else "audio/mp4"
    return FileResponse(str(fp),media_type=mime,filename=f"{track.song.title}_{track.name}{fp.suffix}")

@app.get("/api/songs/{song_id}/download")
def download_song_zip(song_id:int,db:Session=Depends(get_db)):
    import zipfile,io
    song=db.query(Song).filter(Song.id==song_id).first()
    if not song: raise HTTPException(404)
    if not song.tracks: raise HTTPException(404)
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for t in song.tracks:
            fp=Path(t.file_path)
            if fp.exists(): zf.write(fp,fp.name)
    buf.seek(0)
    return FileResponse(buf,media_type="application/zip",filename=f"{song.title or song.id}_stems.zip")

@app.post("/api/songs/{song_id}/original")
def upload_original(song_id:int,file:UploadFile=File(...),db:Session=Depends(get_db)):
    song=db.query(Song).filter(Song.id==song_id).first()
    if not song: raise HTTPException(404)
    od=ORIGINAL_DIR/str(song_id)
    od.mkdir(parents=True,exist_ok=True)
    ext=Path(file.filename).suffix if file.filename else ".mp3"
    fp=od/f"original{ext}"
    with open(fp,"wb") as f: f.write(file.file.read())
    return {"code":0,"message":"ok","data":{"path":str(fp)}}

@app.get("/api/songs/{song_id}/original/download")
def download_original(song_id:int,db:Session=Depends(get_db)):
    song=db.query(Song).filter(Song.id==song_id).first()
    if not song: raise HTTPException(404)
    od=ORIGINAL_DIR/str(song_id)
    if not od.exists(): raise HTTPException(404)
    files=list(od.glob("original.*"))
    if not files: raise HTTPException(404)
    return FileResponse(str(files[0]),media_type="audio/mpeg",filename=song.title+files[0].suffix)

@app.post("/api/songs/{song_id}/status")
def update_status(song_id:int,status:str=Form(...),bpm:float=Form(0.0),db:Session=Depends(get_db)):
    song=db.query(Song).filter(Song.id==song_id).first()
    if not song: raise HTTPException(404)
    song.status=status
    if bpm>0: song.bpm=bpm
    db.commit()
    return {"code":0}

@app.get("/api/stats")
def get_stats(db:Session=Depends(get_db)):
    sc=db.query(Song).count()
    tc=db.query(Track).count()
    ts=sum((Path(t.file_path).stat().st_size for t in db.query(Track).all() if Path(t.file_path).exists()),0)
    return {"code":0,"data":{"song_count":sc,"track_count":tc,"total_size_mb":round(ts/1024/1024,2)}}
''')

print("SERVER FIXED - run: systemctl restart stems")
