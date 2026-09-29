import sys
import unittest
from unittest.mock import MagicMock, patch
import json

from irama.player import (
    MpvPlayer,
    MpvIpcMonitor,
    get_default_ipc_path,
    cleanup_ipc,
    format_seconds,
    format_status_line,
    safe_write_status,
)
from irama.models import Album, Track


class TestMpvPlayer(unittest.TestCase):
    def test_default_ipc_path(self):
        path = get_default_ipc_path()
        if sys.platform.startswith("win"):
            self.assertEqual(path, r"\\.\pipe\irama-mpv")
        else:
            self.assertEqual(path, "/tmp/irama-mpv.sock")

    def test_format_seconds(self):
        self.assertEqual(format_seconds(None), "--:--")
        self.assertEqual(format_seconds(-5), "--:--")
        self.assertEqual(format_seconds(0), "00:00")
        self.assertEqual(format_seconds(75), "01:15")
        self.assertEqual(format_seconds(225.8), "03:45")

    def test_format_status_line(self):
        # Playing
        line = format_status_line(84.0, 225.0, False, "Titiek Puspa - Pantun Jenaka", bar_width=16)
        self.assertIn("▶", line)
        self.assertIn("01:24 / 03:45", line)
        self.assertIn("█", line)
        self.assertIn("Titiek Puspa - Pantun Jenaka", line)

        # Paused
        paused_line = format_status_line(84.0, 225.0, True, "Titiek Puspa - Pantun Jenaka", bar_width=16)
        self.assertIn("⏸", paused_line)

        # Title truncation
        long_title = "A" * 60
        trunc_line = format_status_line(10.0, 100.0, False, long_title, max_title_len=30)
        self.assertIn("...", trunc_line)
        self.assertTrue(len(trunc_line) < 80)

        # None values / buffering
        buffering_line = format_status_line(None, None, False, "Buffering...")
        self.assertIn("--:-- / --:--", buffering_line)
        self.assertIn("░", buffering_line)

    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_safe_write_status_unicode_fallback(self, mock_flush, mock_write):
        # Normal write succeeds
        safe_write_status("test")
        mock_write.assert_called()

        # Simulate UnicodeEncodeError
        def raise_unicode_error(text):
            if "▶" in text:
                raise UnicodeEncodeError("charmap", "\u25b6", 1, 2, "character maps to <undefined>")

        mock_write.side_effect = raise_unicode_error
        # Should not raise exception
        safe_write_status("[▶ 01:24 / 03:45] [████░░░░] Title")

    def test_monitor_handle_message(self):
        monitor = MpvIpcMonitor(ipc_path="dummy-path")

        # Test time-pos
        msg_time = json.dumps({"event": "property-change", "name": "time-pos", "data": 42.5}).encode()
        monitor._handle_message(msg_time)
        self.assertEqual(monitor.time_pos, 42.5)

        # Test duration
        msg_dur = json.dumps({"event": "property-change", "name": "duration", "data": 180.0}).encode()
        monitor._handle_message(msg_dur)
        self.assertEqual(monitor.duration, 180.0)

        # Test media-title
        msg_title = json.dumps({"event": "property-change", "name": "media-title", "data": "New Track Title"}).encode()
        monitor._handle_message(msg_title)
        self.assertEqual(monitor.media_title, "New Track Title")

        # Test pause
        msg_pause = json.dumps({"event": "property-change", "name": "pause", "data": True}).encode()
        monitor._handle_message(msg_pause)
        self.assertTrue(monitor.is_paused)

        # Test malformed / invalid messages
        monitor._handle_message(b"not a valid json")
        monitor._handle_message(b'{"random": 123}')
        # Values should remain unchanged
        self.assertEqual(monitor.time_pos, 42.5)

    def test_monitor_thread_lifecycle_with_mock_stream(self):
        lines = [
            json.dumps({"event": "property-change", "name": "time-pos", "data": 10.0}).encode() + b"\n",
            json.dumps({"event": "property-change", "name": "duration", "data": 100.0}).encode() + b"\n",
            json.dumps({"event": "property-change", "name": "media-title", "data": "Mock Song"}).encode() + b"\n",
            b"",  # EOF
        ]

        class MockStream:
            def __init__(self):
                self._lines = list(lines)
                self.written = []

            def readline(self):
                if self._lines:
                    return self._lines.pop(0)
                return b""

            def write(self, data):
                self.written.append(data)

            def close(self):
                pass

        mock_stream = MockStream()
        opener = lambda path: mock_stream

        with patch("irama.player.safe_write_status"):
            monitor = MpvIpcMonitor(ipc_path="dummy-path", stream_opener=opener)
            monitor.start()
            # Wait briefly for thread to finish reading EOF
            monitor.thread.join(timeout=1.0)
            monitor.stop()

        self.assertEqual(monitor.time_pos, 10.0)
        self.assertEqual(monitor.duration, 100.0)
        self.assertEqual(monitor.media_title, "Mock Song")
        # Verify observe_property commands were sent
        written_text = b"".join(mock_stream.written).decode("utf-8")
        self.assertIn("observe_property", written_text)
        self.assertIn("time-pos", written_text)

    def test_monitor_graceful_degradation_on_connection_failure(self):
        def failing_opener(path):
            raise FileNotFoundError("Socket not found")

        monitor = MpvIpcMonitor(ipc_path="missing-socket", stream_opener=failing_opener)
        # Should not throw exception and terminate cleanly
        monitor.start()
        monitor.stop()
        self.assertFalse(monitor.thread.is_alive())

    @patch("irama.player.safe_print")
    @patch("irama.player.is_mpv_available", return_value=True)
    @patch("subprocess.run")
    def test_mpv_player_play_command_includes_ipc_args(self, mock_subprocess, mock_mpv_avail, mock_print):
        player = MpvPlayer(ipc_path="/custom/test-ipc.sock")
        track = Track(1, "01", "Lagu Test", "Artis", "03:00", "https://example.com/audio.mp3")
        album = Album(id="123", title="Album Test", artist="Artis", year="1970", label="Label", tracks=[track])

        player.play([track], album)

        mock_subprocess.assert_called_once()
        cmd = mock_subprocess.call_args[0][0]

        # Verify command contains MPV IPC arguments
        self.assertIn("mpv", cmd[0])
        self.assertIn("--input-ipc-server=/custom/test-ipc.sock", cmd)
        self.assertIn("--no-video", cmd)
        self.assertIn("--really-quiet", cmd)
        # Verify Referer and User-Agent are preserved
        header_arg = [arg for arg in cmd if arg.startswith("--http-header-fields=")][0]
        self.assertIn("Referer: https://www.iramanusantara.org/", header_arg)
        self.assertIn("User-Agent:", header_arg)


if __name__ == "__main__":
    unittest.main()
