"""Radio streaming engine for Irama Nusantara CLI.

Aggregates tracks across multiple albums based on preset genre stations
or custom queries, utilizing parallel fetching and smart shuffling.
"""

from dataclasses import dataclass
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from .client import IramaClient
from .models import Album, Track


@dataclass
class RadioStationInfo:
    key: str
    name: str
    description: str
    queries: List[str]


RADIO_STATIONS: Dict[str, RadioStationInfo] = {
    "sunda": RadioStationInfo(
        key="sunda",
        name="Gelombang Pasundan",
        description="Pop Sunda, Degung, Jaipong & Tembang Lawas",
        queries=["sunda", "jaipong", "degung"]
    ),
    "keroncong": RadioStationInfo(
        key="keroncong",
        name="Gelombang Keroncong",
        description="Keroncong Asli, Langgam Jawa & Stambul",
        queries=["keroncong", "langgam", "stambul"]
    ),
    "melayu": RadioStationInfo(
        key="melayu",
        name="Gelombang Orkes Melayu",
        description="Irama Melayu Klasik & Dangdut Awal",
        queries=["melayu", "dangdut"]
    ),
    "pop-rock": RadioStationInfo(
        key="pop-rock",
        name="Gelombang Pop & Rock Lawas",
        description="Koes Plus, Panbers, Dara Puspita & Bimbo",
        queries=["koes", "dara puspita", "panbers", "bimbo"]
    ),
    "jazz": RadioStationInfo(
        key="jazz",
        name="Gelombang Instrumental & Jazz",
        description="Jazz Nusantara, Gamelan & Orkes Simfoni",
        queries=["jazz", "instrumental", "gamelan"]
    ),
    "mix": RadioStationInfo(
        key="mix",
        name="Gelombang Campur (Nusantara Mix)",
        description="Sampling Acak Lintas Genre & Era",
        queries=["orkes", "pop", "irama", "nada", "suara"]
    ),
}

# Aliases for convenience
STATION_ALIASES = {
    "1": "sunda",
    "pasundan": "sunda",
    "2": "keroncong",
    "3": "melayu",
    "4": "pop-rock",
    "pop": "pop-rock",
    "rock": "pop-rock",
    "5": "jazz",
    "instrumental": "jazz",
    "6": "mix",
    "random": "mix",
    "acak": "mix",
    "campur": "mix",
}


def resolve_station(station_key_or_query: str) -> RadioStationInfo:
    """Resolves station key or creates custom RadioStationInfo for query."""
    clean = station_key_or_query.strip().lower()
    canonical_key = STATION_ALIASES.get(clean, clean)

    if canonical_key in RADIO_STATIONS:
        return RADIO_STATIONS[canonical_key]

    # Custom query station
    return RadioStationInfo(
        key="custom",
        name=f"Gelombang Kustom ('{station_key_or_query.strip()}')",
        description=f"Siaran berdasarkan kueri kustom: {station_key_or_query.strip()}",
        queries=[station_key_or_query.strip()]
    )


def tune_station(
    client: IramaClient,
    station_key_or_query: str,
    limit_albums: int = 6,
    shuffle: bool = True
) -> Tuple[RadioStationInfo, List[Album], List[Track]]:
    """Tunes into a radio station, fetching albums in parallel and gathering tracks."""
    station_info = resolve_station(station_key_or_query)

    # 1. Search candidate albums across station queries
    candidate_album_map: Dict[str, Album] = {}
    for q in station_info.queries:
        try:
            results = client.search_records(q)
            for alb in results:
                if alb.id not in candidate_album_map:
                    candidate_album_map[alb.id] = alb
        except Exception:
            continue

        if len(candidate_album_map) >= limit_albums * 3:
            break

    if not candidate_album_map:
        return station_info, [], []

    # Select up to limit_albums from candidates
    candidate_list = list(candidate_album_map.values())
    if shuffle:
        random.shuffle(candidate_list)
    selected_candidates = candidate_list[:limit_albums]

    # 2. Parallel fetch of full album details to retrieve audio streams
    fetched_albums: List[Album] = []
    max_workers = min(5, len(selected_candidates)) if selected_candidates else 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_album = {
            executor.submit(client.fetch_album, alb.id): alb
            for alb in selected_candidates
        }
        for future in as_completed(future_to_album):
            try:
                full_album = future.result()
                if full_album and full_album.playable_tracks:
                    fetched_albums.append(full_album)
            except Exception:
                continue

    # 3. Aggregate all playable tracks
    aggregated_tracks: List[Track] = []
    for alb in fetched_albums:
        for t in alb.playable_tracks:
            # Clone track with artist populated for radio M3U OSD display
            track_artist = t.artist if t.artist and t.artist != "Unknown" else alb.artist
            aggregated_tracks.append(Track(
                index=len(aggregated_tracks) + 1,
                track_number=t.track_number,
                title=f"{t.title} ({alb.title})",
                artist=track_artist,
                duration=t.duration,
                audio_url=t.audio_url
            ))

    # 4. Shuffle tracks for radio listening experience
    if shuffle:
        random.shuffle(aggregated_tracks)

    # Re-index tracks
    for idx, t in enumerate(aggregated_tracks, start=1):
        t.index = idx

    return station_info, fetched_albums, aggregated_tracks


def select_radio_station() -> Optional[str]:
    """Displays interactive radio station selection menu."""
    print("\n" + "=" * 76)
    print("📻 IRAMA NUSANTARA RADIO (PILIH GELOMBANG SIARAN)")
    print("=" * 76)
    print("  [1] 🎋 Gelombang Pasundan     : Pop Sunda, Degung, Jaipong & Tembang Lawas")
    print("  [2] 🎻 Gelombang Keroncong    : Keroncong Asli, Langgam Jawa & Stambul")
    print("  [3] 🌴 Gelombang Orkes Melayu : Irama Melayu Klasik & Dangdut Awal")
    print("  [4] 🎸 Gelombang Pop & Rock   : Koes Plus, Panbers, Dara Puspita & Bimbo")
    print("  [5] 🎷 Gelombang Instrumental : Jazz Nusantara, Gamelan & Orkes Simfoni")
    print("  [6] 🎲 Nusantara Mix / Acak   : Sampling Acak Lintas Genre & Era")
    print("  [C] 🔍 Frekuensi Kustom       : Masukkan kata kunci / genre bebas")
    print("  [Q] 🚪 Keluar")
    print("=" * 76)

    while True:
        try:
            choice = input("\nPilih gelombang [1..6 / C] (atau 'q' untuk keluar): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nDibatalkan.")
            return None

        if not choice:
            continue

        c_lower = choice.lower()
        if c_lower in ("q", "quit", "exit"):
            return None

        if c_lower in ("1", "sunda", "pasundan"):
            return "sunda"
        elif c_lower in ("2", "keroncong"):
            return "keroncong"
        elif c_lower in ("3", "melayu"):
            return "melayu"
        elif c_lower in ("4", "pop", "rock", "pop-rock"):
            return "pop-rock"
        elif c_lower in ("5", "jazz", "instrumental"):
            return "jazz"
        elif c_lower in ("6", "mix", "random", "acak"):
            return "mix"
        elif c_lower in ("c", "custom", "kustom"):
            try:
                custom_q = input("Masukkan kata kunci genre / daerah / artis (misal: 'bali', 'tarling'): ").strip()
            except (KeyboardInterrupt, EOFError):
                return None
            if custom_q:
                return custom_q
            print("[!] Kueri tidak boleh kosong.")
        else:
            # Direct text input can be treated as custom query
            return choice


def render_radio_banner(station_info: RadioStationInfo, total_tracks: int, albums: List[Album]) -> None:
    """Renders retro radio broadcast header in the terminal."""
    print("\n" + "=" * 76)
    print(f"📻 MENYIARKAN: {station_info.name.upper()} ({total_tracks} Lagu Terhimpun)")
    print(f"📡 Frekuensi: {station_info.description}")
    print("=" * 76)
    if albums:
        album_names = ", ".join(f"'{a.title}'" for a in albums[:4])
        if len(albums) > 4:
            album_names += f", dan {len(albums) - 4} album lainnya"
        print(f"💿 Sumber Album: {album_names}")
    print("-" * 76)
    print("🎛️  Kontrol: [>] Lagu Berikutnya | [<] Lagu Sebelumnya | [Space] Jeda | [q] Matikan")
    print("=" * 76 + "\n")
