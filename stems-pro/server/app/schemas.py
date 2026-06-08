"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TrackInfo(BaseModel):
    id: int
    name: str
    file_size: int = 0
    duration: float = 0.0
    download_url: str = ""

    class Config:
        from_attributes = True


class SongCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    artist: str = ""
    cover_url: str = ""


class SongUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    artist: Optional[str] = None
    cover_url: Optional[str] = None


class SongResponse(BaseModel):
    id: int
    title: str
    artist: str
    cover_url: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tracks: list[TrackInfo] = []

    class Config:
        from_attributes = True


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[dict | list] = None
