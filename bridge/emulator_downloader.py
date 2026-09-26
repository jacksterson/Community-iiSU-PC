"""
Service for downloading and installing the primary PC emulators supported by iiSU.

On Linux:
  Uses Flatpak (user installation via Flathub, requiring no root/sudo privileges).
  Installs executables to ~/.local/share/flatpak/exports/bin which are directly
  discoverable by shutil.which and launch_bridge.

On Windows:
  Uses Winget (Windows Package Manager) to silently install emulators.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from shared.emulator_defaults import all_emulator_exe_names

# Main supported emulators catalog matching iiSU defaults
EMULATOR_CATALOG = [
    {
        "id": "retroarch",
        "name": "RetroArch",
        "systems": "NES, SNES, N64, GBA, GB/GBC, Genesis, etc.",
        "flatpak_id": "org.libretro.RetroArch",
        "winget_id": "Libretro.RetroArch",
        "check_names": ["retroarch", "org.libretro.RetroArch", "retroarch.exe"],
        "description": "Multi-system frontend covering 8-bit, 16-bit, and 32-bit consoles.",
    },
    {
        "id": "duckstation",
        "name": "DuckStation",
        "systems": "Sony PlayStation (PS1)",
        "flatpak_id": "org.duckstation.DuckStation",
        "winget_id": "DuckStation.DuckStation",
        "check_names": ["duckstation-qt", "org.duckstation.DuckStation", "duckstation-qt-x64-ReleaseLTCG.exe"],
        "description": "Fast and accurate PlayStation 1 emulator.",
    },
    {
        "id": "pcsx2",
        "name": "PCSX2",
        "systems": "Sony PlayStation 2 (PS2)",
        "flatpak_id": "net.pcsx2.PCSX2",
        "winget_id": "PCSX2.PCSX2",
        "check_names": ["pcsx2-qt", "pcsx2", "net.pcsx2.PCSX2", "pcsx2-qt.exe", "pcsx2.exe"],
        "description": "Open-source PlayStation 2 emulator.",
    },
    {
        "id": "dolphin",
        "name": "Dolphin",
        "systems": "Nintendo GameCube & Wii",
        "flatpak_id": "org.DolphinEmu.dolphin-emu",
        "winget_id": "DolphinEmulator.Dolphin",
        "check_names": ["dolphin-emu", "org.DolphinEmu.dolphin-emu", "Dolphin.exe", "DolphinQt2.exe"],
        "description": "GameCube and Wii emulator with high-definition rendering.",
    },
    {
        "id": "cemu",
        "name": "Cemu",
        "systems": "Nintendo Wii U",
        "flatpak_id": "info.cemu.Cemu",
        "winget_id": "Cemu.Cemu",
        "check_names": ["cemu", "Cemu", "info.cemu.Cemu", "Cemu.exe"],
        "description": "Highly optimized Nintendo Wii U emulator.",
    },
    {
        "id": "ppsspp",
        "name": "PPSSPP",
        "systems": "Sony PlayStation Portable (PSP)",
        "flatpak_id": "org.ppsspp.PPSSPP",
        "winget_id": "HenrikRydgard.PPSSPP",
        "check_names": ["PPSSPPSDL", "ppsspp", "org.ppsspp.PPSSPP", "PPSSPPWindows64.exe"],
        "description": "Fast PlayStation Portable emulator.",
    },
    {
        "id": "melonds",
        "name": "melonDS",
        "systems": "Nintendo DS",
        "flatpak_id": "net.kuribo64.melonDS",
        "winget_id": "melonDS.melonDS",
        "check_names": ["melonDS", "melonds", "net.kuribo64.melonDS", "melonDS.exe"],
        "description": "Fast and accurate Nintendo DS emulator.",
    },
    {
        "id": "azahar",
        "name": "Azahar",
        "systems": "Nintendo 3DS",
        "flatpak_id": "org.azahar_emu.Azahar",
        "winget_id": "",
        "check_names": ["azahar", "citra-qt", "org.azahar_emu.Azahar", "citra-qt.exe", "azahar.exe"],
        "description": "Actively maintained Nintendo 3DS emulator.",
    },
    {
        "id": "flycast",
        "name": "Flycast",
        "systems": "Sega Dreamcast",
        "flatpak_id": "org.flycast.Flycast",
        "winget_id": "Flyinghead.Flycast",
        "check_names": ["flycast", "org.flycast.Flycast", "flycast.exe"],
        "description": "Multi-platform Sega Dreamcast emulator.",
    },
    {
        "id": "rpcs3",
        "name": "RPCS3",
        "systems": "Sony PlayStation 3 (PS3)",
        "flatpak_id": "net.rpcs3.RPCS3",
        "winget_id": "RPCS3.RPCS3",
        "check_names": ["rpcs3", "net.rpcs3.RPCS3", "rpcs3.exe"],
        "description": "PlayStation 3 emulator and debugger.",
    },
    {
        "id": "xemu",
        "name": "xemu",
        "systems": "Microsoft Xbox (Original)",
        "flatpak_id": "app.xemu.xemu",
        "winget_id": "MBorgerson.xemu",
        "check_names": ["xemu", "app.xemu.xemu", "xemu.exe"],
        "description": "Original Xbox emulator.",
    },
]


def detect_backend() -> tuple[str, str]:
    """Detects available package manager backend for emulator downloads.
    Returns (backend_type, path_or_info), where backend_type is 'flatpak', 'winget', or 'none'.
    """
    if sys.platform != "win32":
        flatpak_path = shutil.which("flatpak")
        if flatpak_path:
            return "flatpak", flatpak_path
        return "none", "Flatpak is not installed. Install Flatpak to download emulators automatically."
    else:
        winget_path = shutil.which("winget")
        if winget_path:
            return "winget", winget_path
        return "none", "Winget (Windows Package Manager) is not available."


def is_emulator_installed(emu: dict, search_roots: list[Path] | None = None) -> bool:
    """Checks if an emulator is already installed on the system."""
    for name in emu["check_names"]:
        if shutil.which(name):
            return True

    # Also check user flatpak export dir explicitly on Linux in case PATH wasn't refreshed
    if sys.platform != "win32":
        user_flatpak_bin = Path.home() / ".local/share/flatpak/exports/bin"
        for name in emu["check_names"]:
            if (user_flatpak_bin / name).is_file():
                return True

    if search_roots:
        for root in search_roots:
            if not root.is_dir():
                continue
            for name in emu["check_names"]:
                if (root / name).is_file():
                    return True
    return False


def get_catalog_with_status(search_roots: list[Path] | None = None) -> list[dict]:
    """Returns the emulator catalog with live installed status."""
    catalog = []
    for item in EMULATOR_CATALOG:
        entry = dict(item)
        entry["installed"] = is_emulator_installed(entry, search_roots)
        catalog.append(entry)
    return catalog


def ensure_linux_flatpak_flathub() -> None:
    """Ensures flathub remote is configured for user flatpaks."""
    if sys.platform == "win32":
        return
    try:
        subprocess.run(
            ["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        pass


def install_emulator(emu: dict, on_output: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """Installs a single emulator using the detected backend.
    Streams lines to on_output callback if provided.
    Returns (success, error_message).
    """
    backend, info = detect_backend()
    if backend == "none":
        return False, info

    if backend == "flatpak":
        flatpak_id = emu.get("flatpak_id")
        if not flatpak_id:
            return False, f"No Flatpak package available for {emu['name']}."

        ensure_linux_flatpak_flathub()
        cmd = ["flatpak", "install", "-y", "--user", "--noninteractive", "flathub", flatpak_id]
        if on_output:
            on_output(f"> {' '.join(cmd)}\n")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                if on_output:
                    on_output(line)
            process.wait()
            if process.returncode == 0:
                return True, ""
            return False, f"Flatpak install failed with exit code {process.returncode}"
        except Exception as e:
            return False, str(e)

    elif backend == "winget":
        winget_id = emu.get("winget_id")
        if not winget_id:
            return False, f"No Winget package available for {emu['name']}."

        cmd = ["winget", "install", "--id", winget_id, "-e", "--silent", "--accept-package-agreements", "--accept-source-agreements"]
        if on_output:
            on_output(f"> {' '.join(cmd)}\n")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                if on_output:
                    on_output(line)
            process.wait()
            if process.returncode == 0:
                return True, ""
            return False, f"Winget install failed with exit code {process.returncode}"
        except Exception as e:
            return False, str(e)

    return False, f"Unsupported backend: {backend}"
