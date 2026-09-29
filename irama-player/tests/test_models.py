import unittest
from irama.models import Track, Album, format_track_number, sanitize_filename

class TestModels(unittest.TestCase):
    def test_format_track_number_vinyl(self):
        self.assertEqual(format_track_number("A1"), "A1")
        self.assertEqual(format_track_number("B2"), "B2")
        self.assertEqual(format_track_number(1), "01")
        self.assertEqual(format_track_number("9"), "09")
        self.assertEqual(format_track_number(None, 4), "04")

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Album: Titiek / Puspa?"), "Album Titiek  Puspa")
        self.assertEqual(sanitize_filename(""), "Unknown")

    def test_track_playable_status(self):
        t1 = Track(1, "01", "Lagu 1", "Artis", "03:00", "https://example.com/audio.mp3")
        t2 = Track(2, "02", "Lagu 2", "Artis", "03:00", None)
        t3 = Track(3, "03", "Lagu 3", "Artis", "03:00", "   ")

        self.assertTrue(t1.is_playable)
        self.assertFalse(t2.is_playable)
        self.assertFalse(t3.is_playable)

    def test_album_playable_tracks(self):
        t1 = Track(1, "01", "Lagu 1", "Artis", "03:00", "https://example.com/audio.mp3")
        t2 = Track(2, "02", "Lagu 2", "Artis", "03:00", None)
        album = Album(id="7073", title="Test Album", artist="Artis", year="1970", label="Remaco", tracks=[t1, t2])

        self.assertEqual(len(album.playable_tracks), 1)
        self.assertEqual(album.playable_tracks[0].title, "Lagu 1")

if __name__ == "__main__":
    unittest.main()
