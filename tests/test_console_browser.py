"""
Unit tests for bridge/ui/pages/games/console_browser.py logic.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "bridge"))

import sync_library
from bridge.ui.pages.games.console_browser import ConsoleBrowserPage


class ConsoleBrowserLogicTests(unittest.TestCase):
    def test_can_keep_separate(self):
        page = MagicMock(spec=ConsoleBrowserPage)
        # Playlist not excepted -> can keep separate
        rows = [{"is_playlist": True, "excepted": False}]
        self.assertTrue(ConsoleBrowserPage._can_keep_separate(page, rows))

        # Playlist already excepted -> cannot keep separate again
        rows = [{"is_playlist": True, "excepted": True}]
        self.assertFalse(ConsoleBrowserPage._can_keep_separate(page, rows))

        # Plain disc file -> cannot keep separate
        rows = [{"is_playlist": False, "excepted": False}]
        self.assertFalse(ConsoleBrowserPage._can_keep_separate(page, rows))

    def test_can_merge_together(self):
        page = MagicMock(spec=ConsoleBrowserPage)
        # Excepted playlist -> can merge
        rows = [{"excepted": True, "parent_playlist": None, "shortname": "psx"}]
        self.assertTrue(ConsoleBrowserPage._can_merge_together(page, rows))

        # Disc with parent playlist -> can merge
        rows = [{"excepted": True, "parent_playlist": "psx/Game.m3u", "shortname": "psx"}]
        self.assertTrue(ConsoleBrowserPage._can_merge_together(page, rows))

        # 2+ disc files in the same console -> can merge into new playlist
        rows = [
            {"excepted": False, "parent_playlist": None, "shortname": "psx"},
            {"excepted": False, "parent_playlist": None, "shortname": "psx"},
        ]
        self.assertTrue(ConsoleBrowserPage._can_merge_together(page, rows))

        # 2 disc files in DIFFERENT consoles -> cannot merge
        rows = [
            {"excepted": False, "parent_playlist": None, "shortname": "psx"},
            {"excepted": False, "parent_playlist": None, "shortname": "snes"},
        ]
        self.assertFalse(ConsoleBrowserPage._can_merge_together(page, rows))

    def test_scan_worker_maps_parent_playlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            roms_dir = Path(tmp)
            psx = roms_dir / "Playstation 1"
            gt2 = psx / "Gran Turismo 2"
            gt2.mkdir(parents=True)
            (gt2 / "Gran Turismo 2.m3u").write_text("Arcade.bin\nSimulation.bin\n", encoding="utf-8")
            (gt2 / "Arcade.bin").write_bytes(b"x")
            (gt2 / "Simulation.bin").write_bytes(b"x")

            exception_key = "psx/Gran Turismo 2/Gran Turismo 2.m3u"
            with patch.object(sync_library, "load_dedupe_exceptions", return_value={exception_key}):
                page = MagicMock(spec=ConsoleBrowserPage)
                rows, status, error, shortname_to_folder = ConsoleBrowserPage._scan_worker(page, roms_dir)

                self.assertFalse(error)
                self.assertIn("psx", shortname_to_folder)

                # There should be 3 rows: Arcade.bin, Simulation.bin, and the hidden Gran Turismo 2.m3u
                arcade_row = next(r for r in rows if r["name"] == "Arcade")
                self.assertEqual(arcade_row["parent_playlist"], exception_key)
                self.assertTrue(arcade_row["excepted"])
                self.assertFalse(arcade_row["hidden_from_iisu"])

                sim_row = next(r for r in rows if r["name"] == "Simulation")
                self.assertEqual(sim_row["parent_playlist"], exception_key)
                self.assertTrue(sim_row["excepted"])

                m3u_row = next(r for r in rows if r["name"] == "Gran Turismo 2")
                self.assertTrue(m3u_row["hidden_from_iisu"])
                self.assertTrue(m3u_row["excepted"])


if __name__ == "__main__":
    unittest.main()
