import unittest
from irama.client import IramaClient

class TestClientParsing(unittest.TestCase):
    def test_strapi_v4_parsing(self):
        mock_v4 = {
            "data": {
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
                            "track_number": "A2",
                            "title": "Lagu Kenangan",
                            "duration": "02:45",
                            "audio_url": "/uploads/records/7073/A2.mp3"
                        }
                    ]
                }
            }
        }

        album = IramaClient._parse_album_json(mock_v4, "7073")
        self.assertEqual(album.id, "7073")
        self.assertEqual(album.title, "Senandung Malam Minggu")
        self.assertEqual(album.artist, "Titiek Puspa & Mus Mualim")
        self.assertEqual(album.year, "1968")
        self.assertEqual(album.label, "Remaco")
        self.assertEqual(len(album.tracks), 2)
        self.assertEqual(album.tracks[0].track_number, "A1")
        self.assertEqual(album.tracks[1].audio_url, "https://core.iramanusantara.org/uploads/records/7073/A2.mp3")

    def test_strapi_v3_parsing(self):
        mock_v3 = {
            "id": 5001,
            "title": "Tembang Lawas",
            "artist": "Mus Mualim",
            "year": "1972",
            "label": "Lokananta",
            "tracks": [
                {
                    "title": "Intro",
                    "track_no": 1,
                    "url": "https://media.iramanusantara.org/5001/01.mp3"
                }
            ]
        }
        album = IramaClient._parse_album_json(mock_v3, "5001")
        self.assertEqual(album.id, "5001")
        self.assertEqual(album.title, "Tembang Lawas")
        self.assertEqual(len(album.tracks), 1)
        self.assertEqual(album.tracks[0].track_number, "01")
        self.assertEqual(album.tracks[0].audio_url, "https://media.iramanusantara.org/5001/01.mp3")

if __name__ == "__main__":
    unittest.main()
