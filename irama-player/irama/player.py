"""MPV Player integration, JSON IPC Socket control, and playlist management."""

import os
import sys
import json
import shutil
import tempfile
import threading
import time
import subprocess
from typing import List, Optional

from .config import WEB_REFERER, DEFAULT_USER_AGENT
from .models import Album, Track


def is_mpv_available() -> bool:
    return shutil.which("mpv") is not None


def get_default_ipc_path() -> str:
    """Returns platform-specific MPV IPC server path."""
    if sys.platform.startswith("win"):
        return r"\\.\pipe\irama-mpv"
    return "/tmp/irama-mpv.sock"


def cleanup_ipc(ipc_path: str) -> None:
    """Safely cleans up socket or pipe if it exists on the filesystem."""
    if not sys.platform.startswith("win"):
        if os.path.exists(ipc_path):
            try:
                os.remove(ipc_path)
            except OSError:
                pass


def open_ipc_stream(path: str):
    """Opens a bidirectional stream to the MPV IPC server (named pipe or unix socket)."""
    if sys.platform.startswith("win"):
        return open(path, "r+b", buffering=0)
    else:
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(path)
        return sock.makefile("rwb", buffering=0)


def format_seconds(sec: Optional[float]) -> str:
    """Formats float seconds to MM:SS string."""
    if sec is None or sec < 0:
        return "--:--"
    m = int(sec) // 60
    s = int(sec) % 60
    return f"{m:02d}:{s:02d}"


def format_status_line(
    time_pos: Optional[float],
    duration: Optional[float],
    is_paused: bool,
    title: str,
    bar_width: int = 16,
    max_title_len: int = 36,
) -> str:
    """Builds a single-line progress status bar for terminal display."""
    symbol = "⏸" if is_paused else "▶"
    time_str = f"{format_seconds(time_pos)} / {format_seconds(duration)}"

    if duration and duration > 0 and time_pos is not None:
        fraction = min(max(time_pos / duration, 0.0), 1.0)
        filled = int(fraction * bar_width)
    else:
        filled = 0
    bar = "█" * filled + "░" * (bar_width - filled)

    disp_title = (title or "Unknown Track").strip()
    if len(disp_title) > max_title_len:
        disp_title = disp_title[: max_title_len - 3] + "..."

    return f"[{symbol} {time_str}] [{bar}] {disp_title}"


def safe_print(text: str = "", **kwargs) -> None:
    """Safely prints text with fallback for non-UTF8 terminals."""
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        ascii_text = (
            text.replace("▶", ">")
            .replace("⏸", "||")
            .replace("█", "#")
            .replace("░", "-")
        )
        print(ascii_text, **kwargs)


def safe_write_status(text: str) -> None:
    """Safely writes status line to stdout with terminal encoding fallback."""
    try:
        sys.stdout.write(f"\r{text:<79}")
        sys.stdout.flush()
    except UnicodeEncodeError:
        ascii_text = (
            text.replace("▶", ">")
            .replace("⏸", "||")
            .replace("█", "#")
            .replace("░", "-")
        )
        sys.stdout.write(f"\r{ascii_text:<79}")
        sys.stdout.flush()


class MpvIpcMonitor:
    """Background monitor thread communicating with MPV JSON IPC socket."""

    def __init__(
        self,
        ipc_path: str,
        initial_title: str = "Unknown Track",
        stream_opener=None,
    ):
        self.ipc_path = ipc_path
        self.initial_title = initial_title
        self.stream_opener = stream_opener or open_ipc_stream

        self.time_pos: Optional[float] = None
        self.duration: Optional[float] = None
        self.media_title: str = initial_title
        self.is_paused: bool = False

        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.stream = None

    def start(self) -> None:
        """Starts background monitor thread."""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stops background monitor thread and closes connection."""
        self.stop_event.set()
        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)
        # Flush a newline so subsequent terminal output starts on a fresh line
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _run(self) -> None:
        """Main thread loop with retry and graceful error handling."""
        deadline = time.time() + 3.0
        while time.time() < deadline and not self.stop_event.is_set():
            try:
                self.stream = self.stream_opener(self.ipc_path)
                break
            except (OSError, FileNotFoundError):
                time.sleep(0.1)

        if not self.stream:
            # Graceful degradation: IPC server not reachable, silently exit thread
            return

        try:
            # Send observe_property commands for required properties
            commands = [
                {"command": ["observe_property", 1, "time-pos"]},
                {"command": ["observe_property", 2, "duration"]},
                {"command": ["observe_property", 3, "media-title"]},
                {"command": ["observe_property", 4, "pause"]},
            ]
            for cmd in commands:
                msg = json.dumps(cmd) + "\n"
                self.stream.write(msg.encode("utf-8"))

            last_render = 0.0
            while not self.stop_event.is_set():
                line = self.stream.readline()
                if not line:
                    break
                self._handle_message(line)

                now = time.time()
                if now - last_render >= 0.15:
                    self._render()
                    last_render = now

        except (OSError, Exception):
            # Graceful degradation on connection break
            pass
        finally:
            if self.stream:
                try:
                    self.stream.close()
                except Exception:
                    pass

    def _handle_message(self, raw_line: bytes) -> None:
        """Parses and handles a single JSON IPC message from MPV."""
        try:
            msg = json.loads(raw_line.decode("utf-8", errors="replace").strip())
        except Exception:
            return

        if not isinstance(msg, dict):
            return

        if msg.get("event") == "property-change":
            name = msg.get("name")
            data = msg.get("data")
            if name == "time-pos":
                if data is not None and isinstance(data, (int, float)):
                    self.time_pos = float(data)
            elif name == "duration":
                if data is not None and isinstance(data, (int, float)):
                    self.duration = float(data)
            elif name == "media-title":
                if data and isinstance(data, str) and data.strip():
                    self.media_title = data.strip()
            elif name == "pause":
                if data is not None:
                    self.is_paused = bool(data)

    def _render(self) -> None:
        """Renders status line to terminal."""
        line = format_status_line(
            self.time_pos,
            self.duration,
            self.is_paused,
            self.media_title,
        )
        safe_write_status(line)


class MpvPlayer:
    def __init__(
        self,
        referer: str = WEB_REFERER,
        user_agent: str = DEFAULT_USER_AGENT,
        ipc_path: Optional[str] = None,
        ao: Optional[str] = None,
    ):
        self.referer = referer
        self.user_agent = user_agent
        self.ipc_path = ipc_path
        self.ao = ao

    def play(self, tracks: List[Track], album: Album) -> None:
        """Plays a single track or an entire album using mpv with IPC status monitoring."""
        if not is_mpv_available():
            raise FileNotFoundError(
                "'mpv' executable is not installed on this system.\n"
                "Install it via:\n"
                "  Linux: sudo apt install mpv\n"
                "  macOS: brew install mpv\n"
                "  Windows: winget install mpv.net"
            )

        playable = [t for t in tracks if t.is_playable]
        if not playable:
            raise ValueError("No playable audio streams found in the requested tracklist.")

        ipc_path = self.ipc_path or get_default_ipc_path()
        cleanup_ipc(ipc_path)

        http_headers = f"Referer: {self.referer}\r\nUser-Agent: {self.user_agent}"
        cmd = [
            "mpv",
            f"--input-ipc-server={ipc_path}",
            f"--http-header-fields={http_headers}",
            "--no-video",
            "--really-quiet",
        ]
        if self.ao:
            cmd.append(f"--ao={self.ao}")

        temp_playlist = None
        initial_title = f"{playable[0].artist} - {playable[0].title}"
        if len(playable) == 1:
            t = playable[0]
            cmd.append(f"--force-media-title={t.artist} - {t.title} ({album.title})")
            cmd.append(t.audio_url)
        else:
            # Generate on-the-fly M3U playlist with #EXTINF metadata
            with tempfile.NamedTemporaryFile("w", suffix=".m3u", delete=False, encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for t in playable:
                    f.write(f"#EXTINF:-1,{t.artist} - {t.title}\n")
                    f.write(f"{t.audio_url}\n")
                temp_playlist = f.name
            cmd.append(f"--playlist={temp_playlist}")

        monitor = MpvIpcMonitor(ipc_path, initial_title=initial_title)
        try:
            safe_print(f"\n[▶] Launching MPV ({len(playable)} track(s) in queue)...")
            safe_print("[*] MPV Controls: [Space]=Pause/Play | [< / >]=Prev/Next Track | [9/0]=Volume | [q]=Quit\n")

            # Start real-time IPC progress monitor in background
            monitor.start()

            subprocess.run(cmd, check=True)

        except KeyboardInterrupt:
            print("\n[*] Playback stopped by user.")
        except subprocess.CalledProcessError as e:
            if e.returncode == 2:
                print(
                    "\n[!] MPV keluar dengan kode error 2 (Audio device error).\n"
                    "    Penyebab: Lingkungan saat ini (seperti GitHub Codespaces / Docker / server headless)\n"
                    "    tidak memiliki sound card atau perangkat audio fisik yang terpasang.\n"
                    "    Solusi:\n"
                    "    1. Putar lagu langsung di komputer/laptop lokal (Windows/macOS/Linux Desktop)\n"
                    "       yang memiliki speaker.\n"
                    "    2. Di Codespaces/cloud, pilih opsi [D] untuk mengunduh lagu via yt-dlp, lalu putar\n"
                    "       file .mp3 langsung di audio player bawaan VS Code.\n"
                    "    3. Untuk menguji streaming & progress bar di lingkungan headless tanpa sound card,\n"
                    "       gunakan flag: --ao=null (contoh: irama-player 455 --play-all --ao=null)."
                )
            else:
                print(f"[!] MPV process exited with error code {e.returncode}")
        finally:
            monitor.stop()
            cleanup_ipc(ipc_path)
            if temp_playlist and os.path.exists(temp_playlist):
                try:
                    os.remove(temp_playlist)
                except OSError:
                    pass
