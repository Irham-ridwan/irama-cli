import os
import time
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import sqlite3

from irama.cache import AlbumCache, get_default_cache_dir, get_default_cache_db_path
from irama.client import IramaClient
from irama.cli import Spinner, parse_cli_args


class TestAlbumCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_cache.db")
        self.cache = AlbumCache(db_path=self.db_path, ttl_seconds=60)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_cache_paths(self):
        cache_dir = get_default_cache_dir()
        self.assertTrue(cache_dir.endswith("irama"))
        db_path = get_default_cache_db_path()
        self.assertTrue(db_path.endswith("cache.db"))

    def test_crud_operations(self):
        # 1. Cache miss on empty
        self.assertIsNone(self.cache.get("7073"))
        self.assertFalse(self.cache.is_cached("7073"))

        # 2. Set payload
        mock_payload = {
            "id": 7073,
            "title": "Senandung Malam Minggu",
            "artist": "Titiek Puspa",
            "year": "1968",
            "tracks": []
        }
        success = self.cache.set("7073", "Senandung Malam Minggu", "Titiek Puspa", "1968", mock_payload)
        self.assertTrue(success)

        # 3. Cache hit
        fetched = self.cache.get("7073")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], 7073)
        self.assertEqual(fetched["title"], "Senandung Malam Minggu")
        self.assertTrue(self.cache.is_cached("7073"))

        # 4. Upsert (update existing)
        mock_payload["title"] = "Updated Title"
        self.cache.set("7073", "Updated Title", "Titiek Puspa", "1968", mock_payload)
        updated = self.cache.get("7073")
        self.assertEqual(updated["title"], "Updated Title")

        # 5. Delete specific record
        self.assertTrue(self.cache.delete("7073"))
        self.assertIsNone(self.cache.get("7073"))

        # 6. Clear all
        self.cache.set("1", "A1", "Art", "1970", {"id": 1})
        self.cache.set("2", "A2", "Art", "1970", {"id": 2})
        self.assertTrue(self.cache.clear())
        self.assertIsNone(self.cache.get("1"))
        self.assertIsNone(self.cache.get("2"))

    def test_ttl_expiration(self):
        # Short TTL of 1 second
        short_cache = AlbumCache(db_path=self.db_path, ttl_seconds=1)
        short_cache.set("100", "Expiring Album", "Artist", "2000", {"id": 100})

        # Immediately available
        self.assertIsNotNone(short_cache.get("100"))

        # Advance time by mocking time.time
        future_time = time.time() + 2.0
        with patch("time.time", return_value=future_time):
            # Should be expired
            self.assertIsNone(short_cache.get("100"))
            self.assertFalse(short_cache.is_cached("100"))

    def test_graceful_degradation_corrupt_database(self):
        # Corrupt the database file with invalid binary data
        with open(self.db_path, "wb") as f:
            f.write(b"NOT A SQLITE DATABASE CORRUPTED DATA")

        # Operations should not crash the program
        corrupt_cache = AlbumCache(db_path=self.db_path)
        self.assertIsNone(corrupt_cache.get("123"))
        self.assertFalse(corrupt_cache.set("123", "Title", "Artist", "1970", {"id": 123}))
        self.assertFalse(corrupt_cache.delete("123"))
        self.assertFalse(corrupt_cache.clear())


class TestClientCacheIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "client_cache.db")
        self.cache = AlbumCache(db_path=self.db_path)
        self.client = IramaClient(cache=self.cache)

        self.mock_v4 = {
            "data": {
                "id": 7073,
                "attributes": {
                    "title": "Senandung Malam Minggu",
                    "release_year": "1968",
                    "artist": "Titiek Puspa",
                    "label": "Remaco",
                    "tracklists": [
                        {
                            "track_number": "A1",
                            "title": "Pantun Jenaka",
                            "duration": "03:15",
                            "audio_url": "https://example.com/A1.mp3"
                        }
                    ]
                }
            }
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("requests.Session.get")
    def test_fetch_album_caches_and_returns_without_network_on_second_call(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_v4
        mock_get.return_value = mock_response

        # First call: cache miss, makes network request
        album1 = self.client.fetch_album("7073")
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(album1.title, "Senandung Malam Minggu")
        self.assertTrue(self.cache.is_cached("7073"))

        # Second call: cache hit, zero network requests!
        album2 = self.client.fetch_album("7073")
        self.assertEqual(mock_get.call_count, 1)  # Still 1, no new network request
        self.assertEqual(album2.id, "7073")
        self.assertEqual(album2.title, "Senandung Malam Minggu")
        self.assertEqual(album2.tracks[0].title, "Pantun Jenaka")

    @patch("requests.Session.get")
    def test_fetch_album_refresh_bypasses_cache(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_v4
        mock_get.return_value = mock_response

        # Prepopulate cache
        self.client.fetch_album("7073")
        self.assertEqual(mock_get.call_count, 1)

        # Call with refresh=True
        self.client.fetch_album("7073", refresh=True)
        self.assertEqual(mock_get.call_count, 2)  # Triggered network call

    @patch("requests.Session.get")
    def test_fetch_album_no_cache_flag(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_v4
        mock_get.return_value = mock_response

        no_cache_client = IramaClient(cache=self.cache, enable_cache=False)
        no_cache_client.fetch_album("7073")
        self.assertEqual(mock_get.call_count, 1)
        # Should not write to cache
        self.assertFalse(self.cache.is_cached("7073"))


class TestSpinnerAndCLI(unittest.TestCase):
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_spinner_lifecycle(self, mock_flush, mock_write):
        spinner = Spinner(message="Testing...", delay=0.01)
        spinner.start()
        time.sleep(0.05)
        spinner.stop()
        self.assertFalse(spinner.thread.is_alive())

    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_spinner_context_manager(self, mock_flush, mock_write):
        with Spinner(message="Context test...", delay=0.01) as sp:
            time.sleep(0.05)
            self.assertTrue(sp.thread.is_alive())
        self.assertFalse(sp.thread.is_alive())

    def test_cli_cache_flags(self):
        args_no_cache = parse_cli_args(["7073", "--no-cache"])
        self.assertTrue(args_no_cache.no_cache)
        self.assertFalse(args_no_cache.refresh_cache)

        args_refresh = parse_cli_args(["7073", "--refresh-cache"])
        self.assertFalse(args_refresh.no_cache)
        self.assertTrue(args_refresh.refresh_cache)


if __name__ == "__main__":
    unittest.main()
