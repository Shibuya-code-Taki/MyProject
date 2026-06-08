"""SQLAlchemy ORM models for Stems Pro."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base


class Song(Base):
    __tablename__ = "songs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    artist = Column(String(255), default="", index=True)
    cover_url = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tracks = relationship("Track", back_populates="song", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "cover_url": self.cover_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    song_id = Column(Integer, ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(32), nullable=False)  # vocals, drums, bass, guitar, piano, other
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, default=0)
    duration = Column(Float, default=0.0)

    song = relationship("Song", back_populates="tracks")

    def to_dict(self):
        return {
            "id": self.id,
            "song_id": self.song_id,
            "name": self.name,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "duration": self.duration,
        }
