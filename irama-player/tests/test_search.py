import unittest
from unittest.mock import MagicMock, patch
import requests

from irama.client import IramaClient
from irama.cli import parse_cli_args
from irama.config import API_BASE_URL, WEB_REFERER, DEFAULT_USER_AGENT


class TestSearchRecords(unittest.TestCase):
    def setUp(self):
        self.client = IramaClient()

    def test_search_empty_query_returns_empty_list(self):
        self.assertEqual(self.client.search_records(""), [])
        self.assertEqual(self.client.search_records("   "), [])

    @patch("requests.Session.get")
    def test_search_records_strapi_v4(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": 7073,
                    "attributes": {
                        "title": "Senandung Malam Minggu",
                        "release_year": "1968",
                        "artist": {
                            "data": {
                                "attributes": {
                                    "name": "Titiek Puspa & Mus Mualim"
                                }
                            }
                        },
                        "label": {"name": "Remaco"},
                        "tracklists": [
                            {
                                "track_number": "A1",
                                "title": "Pantun Jenaka",
                                "duration": "03:15",
                                "audio_url": "https://media.iramanusantara.org/records/7073/A1.m3u8"
                            },
                            {
                                "track_number": "B1",
                                "title": "Lagu Kenangan",
                                "duration": "02:45",
                                "audio_url": "/uploads/records/7073/B1.mp3"
                            }
                        ]
                    }
                },
                {
                    "id": 7074,
                    "attributes": {
                        "title": "Volume 2",
                        "release_year": "1969",
                        "artist": "Koes Bersaudara",
                        "label": "Mesra",
                        "tracklists": []
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        results = self.client.search_records("malam")

        self.assertEqual(len(results), 2)
        
        # Album 1 verification
        alb1 = results[0]
        self.assertEqual(alb1.id, "7073")
        self.assertEqual(alb1.title, "Senandung Malam Minggu")
        self.assertEqual(alb1.artist, "Titiek Puspa & Mus Mualim")
        self.assertEqual(alb1.year, "1968")
        self.assertEqual(alb1.label, "Remaco")
        self.assertEqual(len(alb1.tracks), 2)
        # Vinyl track numbering check
        self.assertEqual(alb1.tracks[0].track_number, "A1")
        self.assertEqual(alb1.tracks[1].track_number, "B1")
        self.assertEqual(alb1.tracks[1].audio_url, "https://core.iramanusantara.org/uploads/records/7073/B1.mp3")

        # Album 2 verification
        alb2 = results[1]
        self.assertEqual(alb2.id, "7074")
        self.assertEqual(alb2.title, "Volume 2")
        self.assertEqual(alb2.artist, "Koes Bersaudara")
        self.assertEqual(len(alb2.tracks), 0)

        # Verify call params and headers
        mock_get.assert_called_once()
        call_args, call_kwargs = mock_get.call_args
        self.assertEqual(call_args[0], API_BASE_URL)
        self.assertEqual(
            call_kwargs["params"],
            {"_q": "malam", "populate": "*"}
        )
        self.assertEqual(self.client.session.headers["Referer"], WEB_REFERER)
        self.assertEqual(self.client.session.headers["User-Agent"], DEFAULT_USER_AGENT)

    @patch("requests.Session.get")
    def test_search_records_strapi_v3(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 5001,
                "title": "Tembang Lawas",
                "artist": "Mus Mualim",
                "year": "1972",
                "label": "Lokananta",
                "tracks": [
                    {
                        "title": "Intro",
                        "track_no": "A1",
                        "url": "https://media.iramanusantara.org/5001/01.mp3"
                    }
                ]
            }
        ]
        mock_get.return_value = mock_response

        results = self.client.search_records("tembang")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "5001")
        self.assertEqual(results[0].title, "Tembang Lawas")
        self.assertEqual(results[0].tracks[0].track_number, "A1")

    @patch("requests.Session.get")
    def test_search_records_empty_result(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        results = self.client.search_records("tidak_ada_album_ini")
        self.assertEqual(results, [])

    @patch("requests.Session.get")
    def test_search_timeout_handling(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        with self.assertRaises(TimeoutError):
            self.client.search_records("koes")

    @patch("requests.Session.get")
    def test_search_cloudflare_waf_detection(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {"Server": "cloudflare"}
        mock_response.text = "Just a moment... Cloudflare Turnstile Challenge"
        mock_get.return_value = mock_response

        with self.assertRaises(PermissionError) as ctx:
            self.client.search_records("koes")
        self.assertIn("Cloudflare", str(ctx.exception))

    def test_cli_subcommand_search_parsing(self):
        # 'search koes plus'
        args = parse_cli_args(["search", "koes plus"])
        self.assertEqual(args.search, "koes plus")
        self.assertIsNone(args.album_id)

        # 'search koes plus --play-all'
        args = parse_cli_args(["search", "koes", "plus", "--play-all"])
        self.assertEqual(args.search, "koes plus")
        self.assertTrue(args.play_all)

        # '--search "titiek puspa"'
        args = parse_cli_args(["--search", "titiek puspa"])
        self.assertEqual(args.search, "titiek puspa")

        # positional album_id
        args = parse_cli_args(["7073", "--play-all"])
        self.assertEqual(args.album_id, "7073")
        self.assertIsNone(args.search)
        self.assertTrue(args.play_all)

    @patch("builtins.print")
    def test_render_search_results_table(self, mock_print):
        from irama.models import Album
        from irama.cli import render_search_results_table
        alb = Album(id="7073", title="A Very Long Title That Exceeds The Limit For Truncation", artist="Very Long Artist Name", year="1970", label="Label", tracks=[])
        render_search_results_table([alb])
        self.assertTrue(mock_print.called)

    @patch("builtins.input", side_effect=["1"])
    def test_select_album_valid(self, mock_input):
        from irama.models import Album
        from irama.cli import select_album_from_search
        alb = Album(id="7073", title="Test", artist="Artist", year="1970", label="Label", tracks=[])
        selected = select_album_from_search([alb])
        self.assertEqual(selected, alb)

    @patch("builtins.input", side_effect=["q"])
    def test_select_album_quit(self, mock_input):
        from irama.models import Album
        from irama.cli import select_album_from_search
        alb = Album(id="7073", title="Test", artist="Artist", year="1970", label="Label", tracks=[])
        selected = select_album_from_search([alb])
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
