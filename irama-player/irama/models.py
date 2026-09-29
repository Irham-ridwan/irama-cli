"""Domain models for Irama Nusantara entities."""

from dataclasses import dataclass, field
from typing import List, Optional, Any


def sanitize_filename(name: str) -> str:
    """Strip illegal characters for filesystem safe paths."""
    cleaned = "".join(c for c in name if c.isalnum() or c in " ._--()[]").strip()
    return cleaned or "Unknown"


def format_track_number(track_no: Any, fallback_index: int = 1) -> str:
    """Format track number preserving vinyl codes like 'A1' and zero-padding digits."""
    if track_no is None:
        return f"{fallback_index:02d}"
    s = str(track_no).strip()
    if s.isdigit():
        return f"{int(s):02d}"
    return s


@dataclass
class Track:
    index: int
    track_number: str
    title: str
    artist: str
    duration: str
    audio_url: Optional[str]

    @property
    def is_playable(self) -> bool:
        return bool(self.audio_url and self.audio_url.strip())


@dataclass
class Album:
    id: str
    title: str
    artist: str
    year: str
    label: str
    tracks: List[Track] = field(default_factory=list)

    @property
    def safe_title(self) -> str:
        return sanitize_filename(self.title)

    @property
    def playable_tracks(self) -> List[Track]:
        return [t for t in self.tracks if t.is_playable]
