"""
Unit tests for bridge/emulator_downloader.py logic and catalog.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "bridge"))
sys.path.insert(0, str(PROJECT_ROOT / "shared"))

import emulator_downloader
from emulator_downloader import (
    EMULATOR_CATALOG,
    detect_backend,
    is_emulator_installed,
    get_catalog_with_status,
    install_emulator,
)


class EmulatorDownloaderTests(unittest.TestCase):
    def test_catalog_structure(self):
        self.assertGreater(len(EMULATOR_CATALOG), 5)
        for emu in EMULATOR_CATALOG:
            self.assertIn("id", emu)
            self.assertIn("name", emu)
            self.assertIn("systems", emu)
            self.assertIn("check_names", emu)
            self.assertTrue(len(emu["check_names"]) > 0)

    def test_detect_backend(self):
        backend, info = detect_backend()
        self.assertIn(backend, ["flatpak", "winget", "none"])

    def test_is_emulator_installed_via_which(self):
        test_emu = {"check_names": ["python3", "nonexistent_binary_xyz_123"]}
        self.assertTrue(is_emulator_installed(test_emu))

        test_emu_none = {"check_names": ["nonexistent_binary_xyz_123_456"]}
        self.assertFalse(is_emulator_installed(test_emu_none))

    def test_get_catalog_with_status(self):
        catalog = get_catalog_with_status()
        self.assertEqual(len(catalog), len(EMULATOR_CATALOG))
        for item in catalog:
            self.assertIn("installed", item)
            self.assertIsInstance(item["installed"], bool)

    @patch("shutil.which", return_value="/usr/bin/flatpak")
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_install_emulator_flatpak_success(self, mock_popen, mock_run, mock_which):
        mock_proc = MagicMock()
        mock_proc.stdout = ["Downloading...\n", "Installing...\n"]
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        output_lines = []
        emu = {"name": "DuckStation", "flatpak_id": "org.duckstation.DuckStation"}
        ok, err = install_emulator(emu, on_output=output_lines.append)

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertIn("Downloading...\n", output_lines)


if __name__ == "__main__":
    unittest.main()
