"""CLI Interface for Irama Nusantara CLI Tool."""

import sys
import time
import threading
import argparse
from typing import Optional, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .client import IramaClient
from .player import MpvPlayer
from .downloader import YtDlpDownloader
from .models import Album


def safe_print(text: str = "", **kwargs) -> None:
    """Safely prints text with fallback for non-UTF8 terminals."""
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        ascii_text = (
            text.replace("🔍", "[SEARCH]")
            .replace("💿", "[ALBUM]")
            .replace("🎤", "[ARTIST]")
            .replace("📅", "[YEAR]")
            .replace("🆔", "[ID]")
            .replace("✓", "[v]")
            .replace("✗", "[x]")
            .replace("▶", ">")
            .replace("⏸", "||")
        )
        print(ascii_text, **kwargs)


class Spinner:
    """A lightweight terminal spinner running in a background thread."""

    UNICODE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    ASCII_FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, message: str = "Loading...", delay: float = 0.08):
        self.message = message
        self.delay = delay
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def _spin(self) -> None:
        idx = 0
        use_unicode = True
        while not self.stop_event.is_set():
            if use_unicode:
                frame = self.UNICODE_FRAMES[idx % len(self.UNICODE_FRAMES)]
                try:
                    sys.stdout.write(f"\r{self.message} {frame}")
                    sys.stdout.flush()
                except UnicodeEncodeError:
                    use_unicode = False
                    continue
            else:
                frame = self.ASCII_FRAMES[idx % len(self.ASCII_FRAMES)]
                sys.stdout.write(f"\r{self.message} {frame}")
                sys.stdout.flush()

            idx += 1
            time.sleep(self.delay)

        # Clear spinner line
        clear_len = max(len(self.message) + 10, 80)
        sys.stdout.write(f"\r{' ' * clear_len}\r")
        sys.stdout.flush()

    def start(self) -> None:
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.3)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def render_metadata_table(album: Album) -> None:
    """Pretty prints album and tracklist information."""
    safe_print("\n" + "=" * 76)
    safe_print(f"💿 ALBUM : {album.title}")
    safe_print(f"🎤 ARTIST: {album.artist}")
    safe_print(f"📅 YEAR  : {album.year} | LABEL: {album.label}")
    safe_print(f"🆔 ID    : {album.id}")
    safe_print("=" * 76)
    safe_print(f"{'No':<6} | {'Title':<40} | {'Duration':<8} | {'Stream Status'}")
    safe_print("-" * 76)

    for t in album.tracks:
        status = "✓ Ready" if t.is_playable else "✗ Unavailable"
        title_disp = (t.title[:37] + "...") if len(t.title) > 40 else t.title
        safe_print(f"{t.track_number:<6} | {title_disp:<40} | {t.duration:<8} | {status}")

    safe_print("=" * 76)


def render_search_results_table(albums: List[Album]) -> None:
    """Pretty prints search results in a numbered table."""
    safe_print("\n" + "=" * 76)
    safe_print(f"🔍 HASIL PENCARIAN ({len(albums)} album ditemukan)")
    safe_print("=" * 76)
    safe_print(f"{'No':<4} | {'ID':<6} | {'Judul Album':<32} | {'Artis':<18} | {'Tahun'}")
    safe_print("-" * 76)

    for idx, alb in enumerate(albums, start=1):
        title_disp = (alb.title[:29] + "...") if len(alb.title) > 32 else alb.title
        artist_disp = (alb.artist[:15] + "...") if len(alb.artist) > 18 else alb.artist
        safe_print(f"{idx:<4} | {alb.id:<6} | {title_disp:<32} | {artist_disp:<18} | {alb.year}")

    safe_print("=" * 76)


def select_album_from_search(albums: List[Album]) -> Optional[Album]:
    """Prompts user to select an album from search results."""
    while True:
        try:
            choice = input(f"\nPilih nomor album [1..{len(albums)}] (atau 'q' untuk keluar): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nDibatalkan.")
            return None

        if choice in ("q", "quit", "exit"):
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(albums):
                return albums[idx]
            print(f"[!] Nomor tidak valid. Pilih antara 1 dan {len(albums)}.")
        else:
            print("[!] Masukan tidak dikenali.")


def interactive_menu(album: Album, player: MpvPlayer, downloader: YtDlpDownloader) -> None:
    """Runs interactive CLI loop after showing tracklist."""
    while True:
        print("\nChoose Action:")
        print("  [A]         Play entire album sequentially in MPV")
        print(f"  [1..{len(album.tracks)}]   Play specific track")
        print("  [D]         Download entire album via yt-dlp")
        print("  [Q]         Quit")

        try:
            choice = input("\nAction: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice == "a":
            player.play(album.playable_tracks, album)
            break
        elif choice == "d":
            downloader.download_album(album)
            break
        elif choice == "q":
            print("Goodbye.")
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(album.tracks):
                selected_track = album.tracks[idx]
                player.play([selected_track], album)
            else:
                print(f"[!] Invalid track index. Choose between 1 and {len(album.tracks)}.")
        else:
            print("[!] Unrecognized input.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="irama-player",
        description="Irama Nusantara Album Streamer & Downloader CLI",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("album_id", nargs="?", help="Release/Album ID (e.g. 7073)")
    parser.add_argument("--search", "-s", help="Search albums by title (e.g. 'koes plus')")
    parser.add_argument("--cookie", help="Browser session cookie for Cloudflare / Auth bypass")
    parser.add_argument("--no-cache", action="store_true", help="Bypass and disable local SQLite caching")
    parser.add_argument("--refresh-cache", action="store_true", help="Force refresh cache from API")
    parser.add_argument("--play-all", action="store_true", help="Directly stream entire album via MPV")
    parser.add_argument("--track", type=int, help="Track index (1..N) to stream immediately")
    parser.add_argument("--download-all", action="store_true", help="Download all tracks with yt-dlp")
    parser.add_argument("--output-dir", default="./downloads", help="Directory destination for downloaded audio")
    return parser


def parse_cli_args(argv: Optional[list] = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[1:]

    # Handle 'search <query>' subcommand syntax
    if argv and argv[0] == "search":
        query_tokens = []
        option_tokens = []
        i = 1
        while i < len(argv):
            if argv[i].startswith("-"):
                option_tokens.extend(argv[i:])
                break
            query_tokens.append(argv[i])
            i += 1
        query = " ".join(query_tokens).strip()
        transformed = ["--search", query] + option_tokens
        return build_parser().parse_args(transformed)

    return build_parser().parse_args(argv)


def main(argv: Optional[list] = None) -> None:
    args = parse_cli_args(argv)

    search_query = args.search
    album_id = args.album_id

    # If neither album_id nor search_query is supplied via CLI args, prompt interactively
    if not album_id and not search_query:
        try:
            user_input = input("Enter Irama Nusantara Album ID or search query (e.g. 7073 or 'search koes plus'): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return

        if not user_input:
            print("[!] Input cannot be empty.")
            return

        if user_input.lower().startswith("search "):
            search_query = user_input[7:].strip()
        elif user_input.isdigit():
            album_id = user_input
        else:
            search_query = user_input

    client = IramaClient(
        session_cookie=args.cookie,
        enable_cache=not args.no_cache,
        refresh_cache=args.refresh_cache,
    )
    player = MpvPlayer()
    downloader = YtDlpDownloader(download_dir=args.output_dir)

    # 1. Search flow
    if search_query:
        try:
            with Spinner(f"[*] Mencari album dengan kata kunci: '{search_query}'..."):
                results = client.search_records(search_query)
        except Exception as e:
            print(f"\n[!] Error saat mencari: {e}", file=sys.stderr)
            sys.exit(1)

        if not results:
            print(f"[!] Tidak ada album yang ditemukan untuk kata kunci '{search_query}'.")
            return

        render_search_results_table(results)
        selected_album = select_album_from_search(results)
        if not selected_album:
            return

        album = selected_album
        # If tracks are not loaded in search results, fetch the complete album
        if not album.tracks:
            try:
                with Spinner(f"[*] Mengambil detail trek untuk album '{album.title}' (ID: {album.id})..."):
                    album = client.fetch_album(album.id)
            except Exception as e:
                print(f"\n[!] Error: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        # 2. Direct Album ID flow
        try:
            with Spinner(f"[*] Mengambil data album ID {album_id} dari Irama Nusantara..."):
                album = client.fetch_album(album_id)
        except Exception as e:
            print(f"\n[!] Error: {e}", file=sys.stderr)
            sys.exit(1)

    render_metadata_table(album)

    if not album.tracks:
        print("[!] No tracks available in this record.")
        return

    # Direct CLI actions
    if args.play_all:
        player.play(album.playable_tracks, album)
        return
    elif args.track:
        idx = args.track - 1
        if 0 <= idx < len(album.tracks):
            player.play([album.tracks[idx]], album)
        else:
            print(f"[!] Track number must be between 1 and {len(album.tracks)}.")
            sys.exit(1)
        return
    elif args.download_all:
        downloader.download_album(album)
        return

    # Interactive flow
    interactive_menu(album, player, downloader)


if __name__ == "__main__":
    main()
