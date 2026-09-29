"""YT-DLP Downloader integration and audio tagging."""

import os
import shutil
import subprocess
from typing import Optional

from .config import WEB_REFERER, DEFAULT_USER_AGENT, DEFAULT_DOWNLOAD_DIR
from .models import Album, Track


def is_ytdlp_available() -> bool:
    return shutil.which("yt-dlp") is not None


class YtDlpDownloader:
    def __init__(self, download_dir: str = DEFAULT_DOWNLOAD_DIR, referer: str = WEB_REFERER, user_agent: str = DEFAULT_USER_AGENT):
        self.download_dir = download_dir
        self.referer = referer
        self.user_agent = user_agent

    def download_track(self, track: Track, album: Album, custom_dir: Optional[str] = None) -> bool:
        """Downloads single track with yt-dlp, tagging ID3 metadata."""
        if not is_ytdlp_available():
            raise FileNotFoundError(
                "'yt-dlp' is not installed.\n"
                "Install it via: pip install yt-dlp"
            )

        if not track.is_playable:
            print(f"[!] Track '{track.title}' has no valid audio stream URL.")
            return False

        target_base = custom_dir or self.download_dir
        album_dir = os.path.join(target_base, album.safe_title)
        os.makedirs(album_dir, exist_ok=True)

        output_tmpl = os.path.join(album_dir, f"{track.track_number}. %(title)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "--add-header", f"Referer: {self.referer}",
            "--add-header", f"User-Agent: {self.user_agent}",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--embed-metadata",
            "--parse-metadata", f"{album.artist}:%(meta_artist)s",
            "--parse-metadata", f"{album.title}:%(meta_album)s",
            "-o", output_tmpl,
            track.audio_url
        ]

        print(f"[*] Downloading: [{track.track_number}] {track.title} -> {album_dir}")
        try:
            subprocess.run(cmd, check=True)
            print(f"[✓] Download complete: {track.title}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[!] yt-dlp download failed for '{track.title}': {e}")
            return False

    def download_album(self, album: Album, custom_dir: Optional[str] = None) -> int:
        """Downloads all playable tracks in the album."""
        success_count = 0
        playable = album.playable_tracks
        print(f"\n[*] Starting batch download for {len(playable)} track(s)...")

        for t in playable:
            if self.download_track(t, album, custom_dir=custom_dir):
                success_count += 1

        print(f"\n[✓] Batch download finished: {success_count}/{len(playable)} succeeded.")
        return success_count
