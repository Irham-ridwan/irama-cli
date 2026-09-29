"""Unit tests for Irama Nusantara Radio CLI streaming engine."""

import unittest
from unittest.mock import MagicMock, patch

from irama.radio import (
    RADIO_STATIONS,
    RadioStationInfo,
    resolve_station,
    tune_station,
    select_radio_station,
    render_radio_banner,
)
from irama.models import Album, Track
from irama.cli import parse_cli_args, main


class TestRadioModule(unittest.TestCase):
    def test_radio_preset_definitions(self):
        expected_presets = ["sunda", "keroncong", "melayu", "pop-rock", "jazz", "mix"]
        for preset in expected_presets:
            self.assertIn(preset, RADIO_STATIONS)
            st = RADIO_STATIONS[preset]
            self.assertTrue(len(st.name) > 0)
            self.assertTrue(len(st.description) > 0)
            self.assertTrue(len(st.queries) > 0)

    def test_resolve_station(self):
        # Direct preset
        st_sunda = resolve_station("sunda")
        self.assertEqual(st_sunda.key, "sunda")
        self.assertEqual(st_sunda.name, "Gelombang Pasundan")

        # Aliases
        self.assertEqual(resolve_station("pasundan").key, "sunda")
        self.assertEqual(resolve_station("1").key, "sunda")
        self.assertEqual(resolve_station("random").key, "mix")
        self.assertEqual(resolve_station("acak").key, "mix")
        self.assertEqual(resolve_station("pop").key, "pop-rock")

        # Custom query
        st_custom = resolve_station("tarling cirebon")
        self.assertEqual(st_custom.key, "custom")
        self.assertIn("tarling cirebon", st_custom.name)
        self.assertEqual(st_custom.queries, ["tarling cirebon"])

    def test_tune_station_preset(self):
        mock_client = MagicMock()
        # Mock search returning 2 shallow albums
        alb1_shallow = Album(id="101", title="Album 1", artist="Artist 1", year="1970", label="L1", tracks=[])
        alb2_shallow = Album(id="102", title="Album 2", artist="Artist 2", year="1972", label="L2", tracks=[])
        mock_client.search_records.return_value = [alb1_shallow, alb2_shallow]

        # Mock fetch_album returning albums with playable tracks
        t1 = Track(1, "A1", "Lagu 1", "Artist 1", "03:00", "https://s3.amazonaws.com/t1.mp3")
        t2 = Track(2, "A2", "Lagu 2", "Artist 1", "02:30", "https://s3.amazonaws.com/t2.mp3")
        t3 = Track(1, "B1", "Lagu 3", "Artist 2", "04:10", "https://s3.amazonaws.com/t3.mp3")
        alb1_full = Album(id="101", title="Album 1", artist="Artist 1", year="1970", label="L1", tracks=[t1, t2])
        alb2_full = Album(id="102", title="Album 2", artist="Artist 2", year="1972", label="L2", tracks=[t3])

        def fake_fetch(alb_id):
            return alb1_full if alb_id == "101" else alb2_full

        mock_client.fetch_album.side_effect = fake_fetch

        station_info, fetched_albums, tracks = tune_station(
            client=mock_client,
            station_key_or_query="sunda",
            limit_albums=2,
            shuffle=False
        )

        self.assertEqual(station_info.key, "sunda")
        self.assertEqual(len(fetched_albums), 2)
        self.assertEqual(len(tracks), 3)
        # Verify tracks contain audio urls and formatted titles
        self.assertTrue(all(t.is_playable for t in tracks))
        self.assertEqual(tracks[0].title, "Lagu 1 (Album 1)")
        self.assertEqual(tracks[1].title, "Lagu 2 (Album 1)")
        self.assertEqual(tracks[2].title, "Lagu 3 (Album 2)")

    def test_tune_station_shuffle(self):
        mock_client = MagicMock()
        tracks_mock = [
            Track(i, f"A{i}", f"Lagu {i}", "Artist", "03:00", f"https://s3.amazonaws.com/{i}.mp3")
            for i in range(1, 20)
        ]
        alb = Album(id="200", title="Big Album", artist="Artist", year="1975", label="L", tracks=tracks_mock)
        mock_client.search_records.return_value = [alb]
        mock_client.fetch_album.return_value = alb

        # Test deterministic random seed to verify shuffling occurs
        with patch("random.shuffle") as mock_shuffle:
            _, _, tracks = tune_station(mock_client, "jazz", limit_albums=1, shuffle=True)
            self.assertTrue(mock_shuffle.called)

    def test_tune_station_empty_results(self):
        mock_client = MagicMock()
        mock_client.search_records.return_value = []

        station_info, fetched_albums, tracks = tune_station(mock_client, "stasiun_tidak_ada")
        self.assertEqual(len(fetched_albums), 0)
        self.assertEqual(len(tracks), 0)

    @patch("builtins.input", side_effect=["1"])
    def test_select_radio_station_preset(self, mock_input):
        choice = select_radio_station()
        self.assertEqual(choice, "sunda")

    @patch("builtins.input", side_effect=["c", "tarling"])
    def test_select_radio_station_custom(self, mock_input):
        choice = select_radio_station()
        self.assertEqual(choice, "tarling")

    @patch("builtins.input", side_effect=["q"])
    def test_select_radio_station_quit(self, mock_input):
        choice = select_radio_station()
        self.assertIsNone(choice)

    @patch("builtins.print")
    def test_render_radio_banner(self, mock_print):
        st = RADIO_STATIONS["sunda"]
        alb = Album(id="1", title="Album Sunda", artist="Artis", year="1970", label="L", tracks=[])
        render_radio_banner(st, 24, [alb])
        printed = " ".join(str(call[0][0]) for call in mock_print.call_args_list if call[0])
        self.assertIn("GELOMBANG PASUNDAN", printed)
        self.assertIn("24 Lagu Terhimpun", printed)
        self.assertIn("Album Sunda", printed)


class TestRadioCliIntegration(unittest.TestCase):
    def test_cli_subcommand_radio_parsing(self):
        # 'radio'
        args = parse_cli_args(["radio"])
        self.assertTrue(args.radio)
        self.assertIsNone(args.radio_station)

        # 'radio sunda'
        args = parse_cli_args(["radio", "sunda"])
        self.assertTrue(args.radio)
        self.assertEqual(args.radio_station, "sunda")

        # 'radio keroncong --ao=null'
        args = parse_cli_args(["radio", "keroncong", "--ao=null"])
        self.assertTrue(args.radio)
        self.assertEqual(args.radio_station, "keroncong")
        self.assertEqual(args.ao, "null")

        # 'radio --random'
        args = parse_cli_args(["radio", "--random"])
        self.assertTrue(args.radio)
        self.assertTrue(args.random)

    @patch("irama.cli.tune_station")
    @patch("irama.cli.MpvPlayer.play")
    def test_main_radio_flow(self, mock_play, mock_tune):
        st_info = RADIO_STATIONS["sunda"]
        t = Track(1, "A1", "Lagu 1", "Artist", "03:00", "https://s3.amazonaws.com/1.mp3")
        alb = Album(id="1", title="Album Test", artist="Artist", year="1970", label="L", tracks=[t])
        mock_tune.return_value = (st_info, [alb], [t])

        main(["radio", "sunda", "--ao=null"])

        mock_tune.assert_called_once()
        mock_play.assert_called_once()
        passed_tracks, passed_album = mock_play.call_args[0]
        self.assertEqual(passed_tracks, [t])
        self.assertIn("Gelombang Pasundan", passed_album.title)


if __name__ == "__main__":
    unittest.main()
