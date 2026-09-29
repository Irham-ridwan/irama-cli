"""API Client for Irama Nusantara Strapi Backend."""

from typing import Dict, Any, Optional, List
import requests

from .config import API_BASE_URL, WEB_REFERER, DEFAULT_USER_AGENT, REQUEST_TIMEOUT
from .models import Album, Track, format_track_number
from .cache import AlbumCache


class IramaClient:
    def __init__(
        self,
        session_cookie: Optional[str] = None,
        timeout=REQUEST_TIMEOUT,
        cache: Optional[AlbumCache] = None,
        enable_cache: bool = True,
        refresh_cache: bool = False,
    ):
        self.timeout = timeout
        self.enable_cache = enable_cache
        self.refresh_cache = refresh_cache
        if cache is not None:
            self.cache = cache
        elif enable_cache:
            self.cache = AlbumCache()
        else:
            self.cache = None

        self.session = requests.Session()
        self.headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": WEB_REFERER,
            "Origin": WEB_REFERER.rstrip("/"),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "id,en-US;q=0.9,en;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }
        self.session.headers.update(self.headers)
        if session_cookie:
            self.session.headers["Cookie"] = session_cookie

    def fetch_album(self, album_id: str, refresh: bool = False) -> Album:
        """Fetches and parses album by ID, utilizing local cache if available."""
        str_id = str(album_id).strip()

        # Check local SQLite cache first (unless bypassed or refreshing)
        if self.cache and self.enable_cache and not refresh and not self.refresh_cache:
            cached_data = self.cache.get(str_id)
            if cached_data:
                return self._parse_album_json(cached_data, str_id)

        url = f"{API_BASE_URL}/{str_id}"
        params = {"populate": "*"}
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)

            # Detect Cloudflare Challenge / Turnstile Block
            if response.status_code in (403, 503):
                server_hdr = response.headers.get("Server", "").lower()
                if "cloudflare" in server_hdr or "challenge" in response.text.lower():
                    raise PermissionError(
                        "Cloudflare Challenge/WAF detected!\n"
                        "Provide a valid browser session cookie with --cookie."
                    )
                response.raise_for_status()

            response.raise_for_status()
            raw_json = response.json()
            album = self._parse_album_json(raw_json, str_id)

            # Save to local SQLite cache
            if self.cache and self.enable_cache:
                self.cache.set(
                    album_id=album.id,
                    title=album.title,
                    artist=album.artist,
                    year=album.year,
                    payload=raw_json,
                )

            return album

        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Connection timed out after {self.timeout[1]}s. "
                "Irama Nusantara server TTFB is very slow or overloaded."
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API request failed: {e}")

    def search_records(self, query: str) -> List[Album]:
        """Searches albums with fallback across Strapi query parameters."""
        if not query or not query.strip():
            return []

        url = API_BASE_URL
        clean_q = query.strip()
        # Strapi v4 in production uses _q for full-text search across titles & artists,
        # or filters[record_title][$containsi]. Note that filters[title] causes a 500
        # error in Strapi because the database column is named 'record_title'.
        param_candidates = [
            {"_q": clean_q, "populate": "*"},
            {"filters[record_title][$containsi]": clean_q, "populate": "*"},
            {"filters[title][$containsi]": clean_q, "populate": "*"},
        ]

        last_error = None
        for params in param_candidates:
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)

                # Detect Cloudflare Challenge / Turnstile Block
                if response.status_code in (403, 503):
                    server_hdr = response.headers.get("Server", "").lower()
                    if "cloudflare" in server_hdr or "challenge" in response.text.lower():
                        raise PermissionError(
                            "Cloudflare Challenge/WAF detected!\n"
                            "Provide a valid browser session cookie with --cookie."
                        )
                    # If 500 error, Strapi rejected this parameter candidate; try next candidate
                    if response.status_code == 500:
                        continue
                    response.raise_for_status()

                if response.status_code == 200:
                    raw_json = response.json()
                    return self._parse_search_records_json(raw_json)
                elif response.status_code == 500:
                    continue
                else:
                    response.raise_for_status()

            except requests.exceptions.Timeout:
                raise TimeoutError(
                    f"Connection timed out after {self.timeout[1]}s. "
                    "Irama Nusantara server TTFB is very slow or overloaded."
                )
            except PermissionError:
                raise
            except requests.exceptions.RequestException as e:
                last_error = e
                continue

        if last_error:
            raise RuntimeError(f"API request failed: {last_error}")
        return []

    @classmethod
    def _parse_search_records_json(cls, raw_json: Any) -> List[Album]:
        """Parses Strapi v3/v4 search/collection response."""
        records = []
        items = []

        if isinstance(raw_json, dict):
            data_field = raw_json.get("data")
            if isinstance(data_field, list):
                items = data_field
            elif isinstance(data_field, dict):
                items = [data_field]
            elif "results" in raw_json and isinstance(raw_json["results"], list):
                items = raw_json["results"]
        elif isinstance(raw_json, list):
            items = raw_json

        for item in items:
            if not isinstance(item, dict):
                continue

            rec_id = str(item.get("id", "0"))
            if "attributes" in item:
                album_payload = {"data": item}
                album = cls._parse_album_json(album_payload, rec_id)
            else:
                album = cls._parse_album_json(item, rec_id)
            records.append(album)

        return records

    @staticmethod
    def _parse_album_json(raw_json: Dict[str, Any], fallback_id: str) -> Album:
        """Parses Strapi v3/v4 response format defensively."""
        if "data" in raw_json and isinstance(raw_json["data"], dict):
            data_node = raw_json["data"]
            attrs = data_node.get("attributes", data_node)
            record_id = str(data_node.get("id", fallback_id))
        else:
            attrs = raw_json
            record_id = str(raw_json.get("id", fallback_id))

        album_title = (
            attrs.get("record_title")
            or attrs.get("title")
            or attrs.get("album_title")
            or f"Record #{record_id}"
        )

        # Resolve Artist
        artist_raw = attrs.get("artist") or attrs.get("artists")
        artist_names = []
        if isinstance(artist_raw, str):
            artist_names.append(artist_raw)
        elif isinstance(artist_raw, list):
            for a in artist_raw:
                if isinstance(a, dict):
                    name = a.get("name_variation") or a.get("name") or a.get("artist_name")
                    if name:
                        artist_names.append(name)
                elif isinstance(a, str):
                    artist_names.append(a)
        elif isinstance(artist_raw, dict):
            artist_data = artist_raw.get("data")
            if isinstance(artist_data, dict):
                attrs_art = artist_data.get("attributes", {})
                name = attrs_art.get("name") or attrs_art.get("artist_name") or attrs_art.get("name_variation")
                if name:
                    artist_names.append(name)
            else:
                name = artist_raw.get("name") or artist_raw.get("artist_name")
                if name:
                    artist_names.append(name)

        # Fallback to credits if artist is not populated
        if not artist_names and "credits" in attrs and isinstance(attrs["credits"], list):
            for c in attrs["credits"]:
                if isinstance(c, dict) and c.get("artist_name"):
                    artist_names.append(c["artist_name"])
                    break

        artist_name = ", ".join(artist_names) if artist_names else "Various Artists"

        # Resolve Release Year
        release_year = str(
            attrs.get("tahun")
            or attrs.get("released")
            or attrs.get("release_year")
            or attrs.get("year")
            or "N/A"
        )

        # Resolve Label
        label_raw = attrs.get("labels") or attrs.get("label") or "N/A"
        label = "N/A"
        if isinstance(label_raw, str):
            label = label_raw
        elif isinstance(label_raw, dict):
            if "data" in label_raw and isinstance(label_raw["data"], list) and label_raw["data"]:
                first_label = label_raw["data"][0]
                label_attrs = first_label.get("attributes", first_label) if isinstance(first_label, dict) else {}
                label = label_attrs.get("label_name") or label_attrs.get("name") or "N/A"
            else:
                label = (
                    label_raw.get("label_name")
                    or label_raw.get("name")
                    or label_raw.get("attributes", {}).get("name")
                    or "N/A"
                )

        # Parse Tracklist
        raw_tracks = attrs.get("tracklists") or attrs.get("tracks") or []
        tracks = []

        for idx, t in enumerate(raw_tracks, start=1):
            if not isinstance(t, dict):
                continue

            audio_url = (
                t.get("audio_url")
                or t.get("file_url")
                or t.get("stream_url")
                or t.get("url")
            )

            if not audio_url and "file_track" in t and isinstance(t["file_track"], dict):
                file_data = t["file_track"].get("data")
                if isinstance(file_data, dict):
                    audio_url = file_data.get("attributes", {}).get("url")

            if not audio_url and "media" in t and isinstance(t["media"], dict):
                audio_url = t["media"].get("url")
            if not audio_url and "audio" in t and isinstance(t["audio"], dict):
                audio_data = t["audio"].get("data")
                if isinstance(audio_data, dict):
                    audio_url = audio_data.get("attributes", {}).get("url")
                else:
                    audio_url = t["audio"].get("url")

            if audio_url and audio_url.startswith("/"):
                audio_url = f"https://core.iramanusantara.org{audio_url}"

            title = t.get("title") or t.get("name") or t.get("track_title") or f"Track {idx}"
            raw_track_no = t.get("pos") or t.get("track_number") or t.get("track_no") or idx
            track_num = format_track_number(raw_track_no, fallback_index=idx)
            track_artist = t.get("artist") or artist_name

            dur_raw = t.get("duration") or t.get("length")
            if isinstance(dur_raw, (int, float)):
                m = int(dur_raw) // 60
                s = int(dur_raw) % 60
                duration = f"{m:02d}:{s:02d}"
            else:
                duration = str(dur_raw or "N/A")

            tracks.append(Track(
                index=idx,
                track_number=track_num,
                title=title,
                artist=track_artist,
                duration=duration,
                audio_url=audio_url
            ))

        return Album(
            id=record_id,
            title=album_title,
            artist=artist_name,
            year=release_year,
            label=str(label),
            tracks=tracks
        )
