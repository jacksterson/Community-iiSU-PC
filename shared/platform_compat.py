"""
Cross-platform compatibility layer for running Community-iiSU-PC on Linux/POSIX.

Handles:
- Stripping Windows-specific subprocess flags (creationflags) on POSIX
- Defining subprocess.CREATE_NO_WINDOW / CREATE_NEW_CONSOLE if missing
- Mocking winreg on non-Windows platforms
- Providing POSIX-safe fallbacks for Windows-specific behaviors
"""

import os
import subprocess
import sys
import types

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

# 1. Define Windows-only subprocess constants on POSIX if not present
if not hasattr(subprocess, "CREATE_NO_WINDOW"):
    subprocess.CREATE_NO_WINDOW = 0x08000000
if not hasattr(subprocess, "CREATE_NEW_CONSOLE"):
    subprocess.CREATE_NEW_CONSOLE = 0x00000010
if not hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
    subprocess.CREATE_NEW_PROCESS_GROUP = 0x00000200
if not hasattr(subprocess, "DETACHED_PROCESS"):
    subprocess.DETACHED_PROCESS = 0x00000008

# 2. Patch subprocess.Popen on POSIX to transparently handle creationflags
if not IS_WINDOWS:
    _orig_popen_init = subprocess.Popen.__init__

    def _safe_popen_init(self, *args, **kwargs):
        if "creationflags" in kwargs:
            kwargs.pop("creationflags", None)
            if kwargs.get("start_new_session") is None:
                kwargs["start_new_session"] = True
        return _orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _safe_popen_init

# 3. Provide mock winreg module on POSIX so imports succeed
if not IS_WINDOWS and "winreg" not in sys.modules:
    mock_winreg = types.ModuleType("winreg")
    mock_winreg.HKEY_CURRENT_USER = 1
    mock_winreg.HKEY_LOCAL_MACHINE = 2
    mock_winreg.HKEY_CLASSES_ROOT = 3
    mock_winreg.KEY_READ = 1
    mock_winreg.KEY_WRITE = 2
    mock_winreg.KEY_ALL_ACCESS = 3

    class _MockKey:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def _mock_open_key(*args, **kwargs):
        raise OSError("winreg is not available on non-Windows platforms")

    mock_winreg.OpenKey = _mock_open_key
    mock_winreg.QueryValueEx = lambda *args, **kwargs: ("", 0)
    mock_winreg.EnumValue = lambda *args, **kwargs: ("", "", 0)
    mock_winreg.EnumKey = lambda *args, **kwargs: ""
    mock_winreg.CloseKey = lambda *args, **kwargs: None

    sys.modules["winreg"] = mock_winreg
