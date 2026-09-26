"""
Shared Win32 window-management helpers (ctypes, stdlib only) used by
launch_bridge.py, apply_display.py, and manager.py.

HWND is pointer-sized; without explicit argtypes/restype ctypes assumes
32-bit ints on some of these, which silently truncates handles on 64-bit
Windows and makes calls like SetForegroundWindow a no-op. Declaring them
properly here is what actually makes this work.
"""

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

try:
    import shared.platform_compat  # noqa: F401
except ImportError:
    pass

IS_WINDOWS = sys.platform == "win32" and hasattr(ctypes, "windll")


def _run_kwin_script(code: str, name: str = "iisu_kwin") -> bool:
    if sys.platform == "win32" or not shutil.which("qdbus"):
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(code)
        fpath = f.name
    try:
        res = subprocess.run(
            ["qdbus", "org.kde.KWin", "/Scripting", "loadScript", fpath, name],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode != 0:
            return False
        subprocess.run(["qdbus", "org.kde.KWin", "/Scripting", "start"], capture_output=True, timeout=2)
        subprocess.run(["qdbus", "org.kde.KWin", "/Scripting", "unloadScript", name], capture_output=True, timeout=2)
        return True
    except Exception:
        return False
    finally:
        try:
            os.unlink(fpath)
        except Exception:
            pass


def ensure_linux_kwin_rules() -> bool:
    """Configures KDE KWin window rules so the Android emulator maps directly
    into borderless fullscreen and the auxiliary Emulator toolbar is suppressed
    automatically from window creation, avoiding any border/toolbar flicker."""
    if sys.platform == "win32" or not shutil.which("qdbus"):
        return False
    from pathlib import Path
    import uuid

    kwin_rules_path = Path.home() / ".config" / "kwinrulesrc"
    try:
        content = kwin_rules_path.read_text(encoding="utf-8") if kwin_rules_path.exists() else ""
    except Exception:
        return False

    main_rule_id = str(uuid.uuid4())
    toolbar_rule_id = str(uuid.uuid4())
    toolbar_rule_id2 = str(uuid.uuid4())

    main_block = f"""
[{main_rule_id}]
Description=Community-iiSU-PC Main Window
fullscreen=true
fullscreenrule=2
noborder=true
noborderrule=2
title=Android Emulator
titlematch=2
types=1
wmclass=Emulator
wmclassmatch=1
"""
    toolbar_block = f"""
[{toolbar_rule_id}]
Description=Community-iiSU-PC Toolbar
minimize=true
minimizerule=2
opacityactive=0
opacityactiverule=2
opacityinactive=0
opacityinactiverule=2
skiptaskbar=true
skiptaskbarrule=2
skipswitcher=true
skipswitcherrule=2
types=4
typesrule=2
wmclass=Emulator
wmclassmatch=1

[{toolbar_rule_id2}]
Description=Community-iiSU-PC Toolbar Empty Title
minimize=true
minimizerule=2
opacityactive=0
opacityactiverule=2
opacityinactive=0
opacityinactiverule=2
skiptaskbar=true
skiptaskbarrule=2
skipswitcher=true
skipswitcherrule=2
title=
titlematch=1
wmclass=Emulator
wmclassmatch=1
"""
    # Remove any previous Community-iiSU-PC rules
    lines = content.splitlines()
    clean_lines = []
    skip_section = False
    for line in lines:
        if line.strip().startswith("[") and line.strip().endswith("]"):
            skip_section = False
        if "Community-iiSU-PC" in line:
            skip_section = True
            # remove preceding section header if possible
            if clean_lines and clean_lines[-1].strip().startswith("[") and clean_lines[-1].strip().endswith("]"):
                clean_lines.pop()
            continue
        if skip_section:
            continue
        clean_lines.append(line)

    existing_rules = []
    for line in clean_lines:
        if line.startswith("rules="):
            existing_rules = [r.strip() for r in line.split("=", 1)[1].split(",") if r.strip()]
    # Remove existing Community-iiSU-PC rule IDs if any
    existing_rules.extend([main_rule_id, toolbar_rule_id, toolbar_rule_id2])

    new_lines = []
    for line in clean_lines:
        if line.startswith("count="):
            new_lines.append(f"count={len(existing_rules)}")
        elif line.startswith("rules="):
            new_lines.append(f"rules={','.join(existing_rules)}")
        else:
            new_lines.append(line)
    new_content = "\n".join(new_lines).rstrip() + "\n" + main_block + toolbar_block + "\n"
    try:
        kwin_rules_path.write_text(new_content, encoding="utf-8")
        subprocess.run(["qdbus", "org.kde.KWin", "/KWin", "reconfigure"], capture_output=True, timeout=2)
        return True
    except Exception:
        return False


def _linux_find_window(substring: str) -> int | None:
    if shutil.which("xdotool"):
        try:
            for term in (substring, "Android Emulator", "iisuwin", "qemu"):
                res = subprocess.run(
                    ["xdotool", "search", "--onlyvisible", "--name", term],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0 and res.stdout.strip():
                    lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
                    if lines:
                        return int(lines[0])
        except Exception:
            pass

    if shutil.which("qdbus"):
        try:
            res = subprocess.run(["qdbus", "org.kde.KWin", "/KWin", "org.kde.KWin.supportInformation"], capture_output=True, timeout=2)
            if res.returncode == 0:
                return 1
        except Exception:
            pass

    try:
        res = subprocess.run(["pgrep", "-f", "qemu-system|emulator"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0 and res.stdout.strip():
            return int(res.stdout.splitlines()[0])
    except Exception:
        pass

    return None


def _linux_make_fullscreen(hwnd: int = 0) -> None:
    ensure_linux_kwin_rules()
    kwin_code = """
    var clients = workspace.windowList();
    for (var i = 0; i < clients.length; i++) {
        var c = clients[i];
        var cap = (c.caption || '').toLowerCase();
        var cls = (c.resourceClass || '').toLowerCase();
        if (cls === 'emulator' || cls.indexOf('qemu') !== -1) {
            if (c.normalWindow && (cap.indexOf('iisuwin') !== -1 || cap.indexOf('android emulator') !== -1)) {
                c.fullScreen = true;
                c.noBorder = true;
                workspace.activeWindow = c;
            } else {
                c.minimized = true;
                c.skipTaskbar = true;
                c.skipSwitcher = true;
                c.opacity = 0;
            }
        }
    }
    """
    _run_kwin_script(kwin_code, "iisu_make_fullscreen")

    if shutil.which("xdotool"):
        try:
            for term in ("iisuwin", "Android Emulator"):
                res = subprocess.run(["xdotool", "search", "--name", term], capture_output=True, text=True, timeout=2)
                if res.returncode == 0 and res.stdout.strip():
                    for win_id in res.stdout.splitlines():
                        win_id = win_id.strip()
                        if win_id:
                            subprocess.run(["xdotool", "windowactivate", win_id], capture_output=True, timeout=1)
                            subprocess.run(["xdotool", "windowstate", "--add", "FULLSCREEN", win_id], capture_output=True, timeout=1)
        except Exception:
            pass

    _linux_hide_emulator_toolbar()

    try:
        subprocess.run(
            ["adb", "shell", "settings", "put", "global", "policy_control", "immersive.full=*"],
            capture_output=True,
            timeout=3,
        )
    except Exception:
        pass


def _linux_force_foreground(hwnd: int = 0) -> None:
    kwin_code = """
    var clients = workspace.windowList();
    for (var i = 0; i < clients.length; i++) {
        var c = clients[i];
        var cap = (c.caption || '').toLowerCase();
        var cls = (c.resourceClass || '').toLowerCase();
        if (cap.indexOf('iisuwin') !== -1 || cap.indexOf('android emulator') !== -1 || cls.indexOf('qemu') !== -1 || cls.indexOf('emulator') !== -1) {
            workspace.activeWindow = c;
        }
    }
    """
    _run_kwin_script(kwin_code, "iisu_force_foreground")

    if shutil.which("xdotool"):
        try:
            if hwnd > 1:
                subprocess.run(["xdotool", "windowactivate", str(hwnd)], capture_output=True, timeout=1)
            else:
                for term in ("iisuwin", "Android Emulator"):
                    subprocess.run(["xdotool", "search", "--name", term, "windowactivate", "%@"], capture_output=True, timeout=1)
        except Exception:
            pass


def _linux_hide_emulator_toolbar() -> None:
    kwin_code = """
    var clients = workspace.windowList();
    for (var i = 0; i < clients.length; i++) {
        var c = clients[i];
        var cap = (c.caption || '').toLowerCase();
        var cls = (c.resourceClass || '').toLowerCase();
        if (cls === 'emulator' || cls.indexOf('qemu') !== -1) {
            if (!c.normalWindow || cap.indexOf('android emulator') === -1) {
                c.minimized = true;
                c.skipTaskbar = true;
                c.skipSwitcher = true;
                c.opacity = 0;
            }
        }
    }
    """
    _run_kwin_script(kwin_code, "iisu_hide_toolbar")

    if shutil.which("xdotool"):
        try:
            res = subprocess.run(["xdotool", "search", "--class", "Emulator"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                for wid in res.stdout.splitlines():
                    wid = wid.strip()
                    if not wid:
                        continue
                    name_res = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True, text=True, timeout=1)
                    name = name_res.stdout.strip()
                    if "Android Emulator" not in name and "iisuwin" not in name:
                        subprocess.run(["xdotool", "windowunmap", wid], capture_output=True, timeout=1)
                        subprocess.run(["xdotool", "windowminimize", wid], capture_output=True, timeout=1)
        except Exception:
            pass

if IS_WINDOWS:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    # LONG_PTR is pointer-sized (64-bit on x64 Windows); c_ssize_t matches that.
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetConsoleWindow.restype = wintypes.HWND
else:
    class _WinApiMockFunc:
        def __init__(self, name=""):
            self.argtypes = []
            self.restype = None
            self._name = name

        def __call__(self, *args, **kwargs):
            return 0

    class _WinApiMock:
        def __getattr__(self, name):
            val = _WinApiMockFunc(name)
            setattr(self, name, val)
            return val

    user32 = _WinApiMock()
    kernel32 = _WinApiMock()

    def WNDENUMPROC(f):
        return f

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WM_CLOSE = 0x0010
SW_HIDE = 0
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
HWND_TOP = 0
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020
SM_CXSCREEN = 0
SM_CYSCREEN = 1
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
WS_BORDERLESS_MASK = WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU


def minimize_own_console() -> None:
    """Minimizes this process's own console window, if it has one. Every
    entry point launched via `start "" python foo.py` from a .bat file
    (manager.py, setup_gui.py) gets a visible console alongside its real
    tkinter GUI, since python.exe, unlike pythonw.exe, is a console-
    subsystem executable; minimizing it out of the way instead of leaving
    it sitting on top keeps the actual GUI window the thing you see first.
    Minimized rather than hidden so the raw stdout/stderr it carries (a
    traceback the GUI itself failed to catch, say) is still one click away
    on the taskbar instead of silently gone. A no-op wherever there's no
    console to minimize (GetConsoleWindow returns NULL), which is exactly
    what happens on a second run of a script that already detached from
    its console, so this is always safe to call unconditionally."""
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        user32.ShowWindow(hwnd, SW_MINIMIZE)


def _find_window(predicate) -> int | None:
    found = {"hwnd": None}

    def callback(hwnd, _lparam):
        if predicate(hwnd):
            found["hwnd"] = hwnd
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found["hwnd"]


def _window_title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def list_visible_windows() -> set[int]:
    """Return handles for the currently visible, titled top-level windows.

    Native Windows apps may hand their UI to a different process than the one
    returned by Popen, so launch_bridge can snapshot this set before launch and
    identify the new top-level window afterward without relying on a PID.
    """
    windows: set[int] = set()

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and _window_title(hwnd):
            windows.add(int(hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return windows


def wait_for_new_visible_window(existing: set[int], timeout: float = 10.0) -> int | None:
    """Wait for a visible, titled top-level window not in `existing`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = list_visible_windows()
        new_windows = current - existing
        if new_windows:
            # EnumWindows order is not guaranteed, but a newly launched normal
            # desktop app ordinarily contributes a single new top-level window.
            return next(iter(new_windows))
        time.sleep(0.2)
    return None




def window_process_name(hwnd: int) -> str:
    """Return the executable filename that owns a top-level window, if available."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.rsplit("\\", 1)[-1]
    finally:
        kernel32.CloseHandle(handle)


def wait_for_new_visible_window_excluding_processes(
    existing: set[int],
    excluded_processes: set[str],
    timeout: float = 60.0,
    stable_seconds: float = 1.5,
) -> int | None:
    """Wait for a persistent new window whose owner is not a launcher process.

    This is intended for protocol launches such as Steam. Steam's own
    "Launching..." popup is a new visible HWND too, but it belongs to
    steam.exe/steamwebhelper.exe rather than to the launched game.
    """
    excluded = {name.casefold() for name in excluded_processes}
    deadline = time.time() + timeout
    first_seen: dict[int, float] = {}

    while time.time() < deadline:
        now = time.time()
        current = list_visible_windows()
        candidates = current - existing

        for hwnd in list(first_seen):
            if hwnd not in candidates or not user32.IsWindow(hwnd):
                first_seen.pop(hwnd, None)

        for hwnd in candidates:
            process_name = window_process_name(hwnd)
            if process_name and process_name.casefold() in excluded:
                continue
            first_seen.setdefault(hwnd, now)
            if now - first_seen[hwnd] >= stable_seconds:
                return hwnd

        time.sleep(0.2)
    return None


def wait_for_stable_new_visible_window(
    existing: set[int],
    timeout: float = 45.0,
    stable_seconds: float = 2.0,
    ignore_first_seconds: float = 1.0,
) -> int | None:
    """Wait for a *persistent* new top-level window.

    URI launchers such as Steam commonly create a short-lived "Launching..."
    popup before the real game window. Returning the first new HWND makes that
    popup look like the game: when it disappears, launch_bridge restores iiSU
    too early. A candidate must therefore remain visible/alive for
    `stable_seconds` before it is accepted.
    """
    deadline = time.time() + timeout
    started = time.time()
    first_seen: dict[int, float] = {}

    while time.time() < deadline:
        now = time.time()
        current = list_visible_windows()
        new_windows = current - existing

        # Forget candidates that vanished; a Steam launch popup normally lands here.
        for hwnd in list(first_seen):
            if hwnd not in new_windows or not user32.IsWindow(hwnd):
                first_seen.pop(hwnd, None)

        if now - started >= ignore_first_seconds:
            for hwnd in new_windows:
                first_seen.setdefault(hwnd, now)
                if now - first_seen[hwnd] >= stable_seconds:
                    return hwnd

        time.sleep(0.2)
    return None


def close_window(hwnd: int) -> bool:
    """Ask a top-level window to close normally, like clicking its X button."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    return bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


def wait_for_window_to_close(
    hwnd: int,
    poll_interval: float = 0.25,
    timeout: float | None = None,
) -> bool:
    """Wait for a top-level HWND to be destroyed.

    Returns True when the HWND closes. If timeout is provided, returns False
    when that many seconds elapse while the HWND is still valid.
    """
    deadline = time.monotonic() + timeout if timeout is not None else None

    while user32.IsWindow(hwnd):
        if deadline is not None and time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval)

    return True


def find_window_by_pid(pid: int) -> int | None:
    def matches(hwnd):
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        return owner_pid.value == pid and user32.IsWindowVisible(hwnd)

    return _find_window(matches)


def wait_for_visible_window_by_pid(
    pid: int,
    timeout: float = 5.0,
    stable_seconds: float = 0.5,
) -> int | None:
    """Wait for a visible window owned by `pid` to remain stable.

    Native games can destroy and recreate their top-level HWND during display
    mode or resolution changes. This lets launch_bridge reacquire the
    replacement window without adopting an unrelated application's HWND.
    """
    deadline = time.monotonic() + timeout
    candidate: int | None = None
    first_seen: float | None = None

    while time.monotonic() < deadline:
        hwnd = find_window_by_pid(pid)

        if hwnd is None or not user32.IsWindow(hwnd):
            candidate = None
            first_seen = None
        elif hwnd != candidate:
            candidate = hwnd
            first_seen = time.monotonic()
        elif first_seen is not None and time.monotonic() - first_seen >= stable_seconds:
            return hwnd

        time.sleep(0.2)

    return None


def find_window_by_title(substring: str) -> int | None:
    if not IS_WINDOWS:
        return _linux_find_window(substring)

    def matches(hwnd):
        return user32.IsWindowVisible(hwnd) and substring.lower() in _window_title(hwnd).lower()

    return _find_window(matches)


def find_window_by_exact_title(title: str) -> int | None:
    if not IS_WINDOWS:
        return _linux_find_window(title)

    def matches(hwnd):
        return user32.IsWindowVisible(hwnd) and _window_title(hwnd) == title

    return _find_window(matches)


def hide_emulator_toolbar() -> None:
    """The standalone Android Emulator's side toolbar (power/volume/rotate/
    settings icons) is a separate top-level window titled just "Emulator"
    docked at the edge of the main device window, not a panel inside it,
    and not something exposed via any emulator command-line flag or config.
    Since it's its own window, we can just hide it directly."""
    if not IS_WINDOWS:
        _linux_hide_emulator_toolbar()
        return

    hwnd = find_window_by_exact_title("Emulator")
    if hwnd is not None:
        user32.ShowWindow(hwnd, SW_HIDE)


class _DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_uint16),
        ("dmDriverVersion", ctypes.c_uint16),
        ("dmSize", ctypes.c_uint16),
        ("dmDriverExtra", ctypes.c_uint16),
        ("dmFields", ctypes.c_uint32),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_uint32),
        ("dmDisplayFixedOutput", ctypes.c_uint32),
        ("dmColor", ctypes.c_int16),
        ("dmDuplex", ctypes.c_int16),
        ("dmYResolution", ctypes.c_int16),
        ("dmTTOption", ctypes.c_int16),
        ("dmCollate", ctypes.c_int16),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_uint16),
        ("dmBitsPerPel", ctypes.c_uint32),
        ("dmPelsWidth", ctypes.c_uint32),
        ("dmPelsHeight", ctypes.c_uint32),
        ("dmDisplayFlags", ctypes.c_uint32),
        ("dmDisplayFrequency", ctypes.c_uint32),
    ]


_ENUM_CURRENT_SETTINGS = -1


def get_primary_monitor_mode() -> tuple[int, int, int]:
    """Returns (width, height, refresh_hz) for the current primary monitor,
    so the setup GUI can offer to match the AVD's display profile to it
    instead of the user guessing values by hand."""
    if not IS_WINDOWS:
        try:
            from PySide6.QtGui import QGuiApplication
            app = QGuiApplication.instance()
            if app is not None:
                screen = app.primaryScreen()
                if screen is not None:
                    geom = screen.geometry()
                    rate = int(screen.refreshRate()) or 60
                    return geom.width(), geom.height(), rate
        except Exception:
            pass
        return 1920, 1080, 60

    dm = _DEVMODE()
    dm.dmSize = ctypes.sizeof(_DEVMODE)
    user32.EnumDisplaySettingsW(None, _ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    refresh_hz = dm.dmDisplayFrequency if dm.dmDisplayFrequency > 1 else 60
    return dm.dmPelsWidth, dm.dmPelsHeight, refresh_hz


def force_foreground(hwnd: int, show_state: int = SW_RESTORE) -> None:
    """Windows normally blocks background processes from stealing focus;
    this uses the standard AttachThreadInput workaround to get around that."""
    if not IS_WINDOWS:
        _linux_force_foreground(hwnd)
        return

    current_thread_id = kernel32.GetCurrentThreadId()
    target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(target_thread_id, current_thread_id, True)
    user32.ShowWindow(hwnd, show_state)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    user32.AttachThreadInput(target_thread_id, current_thread_id, False)


def nudge_focus_with_click(hwnd: int) -> None:
    """SetForegroundWindow only makes the top-level window active; Qt apps
    like DuckStation track actual keyboard/controller input focus on their
    render widget separately, which only picks it up on a real click. This
    synthesizes that click at the window's center (moves the real cursor)."""
    if not IS_WINDOWS:
        return

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    user32.SetCursorPos(cx, cy)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)


def make_fullscreen(hwnd: int) -> None:
    """True borderless fullscreen: SW_MAXIMIZE alone doesn't work on windows
    (like the Android Emulator's) that clamp their own max size, and simply
    resizing via SetWindowPos still leaves the title bar/border eating into
    the screen. This strips the caption/border styles first, then resizes
    to the full screen, the standard "borderless fullscreen" technique."""
    if not IS_WINDOWS:
        _linux_make_fullscreen(hwnd)
        return

    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style & ~WS_BORDERLESS_MASK)

    width = user32.GetSystemMetrics(SM_CXSCREEN)
    height = user32.GetSystemMetrics(SM_CYSCREEN)
    user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, width, height, SWP_SHOWWINDOW | SWP_FRAMECHANGED)


def wait_for_window_by_pid(pid: int, timeout: float = 8.0) -> int | None:
    deadline = time.time() + timeout
    hwnd = find_window_by_pid(pid)
    while hwnd is None and time.time() < deadline:
        time.sleep(0.2)
        hwnd = find_window_by_pid(pid)
    return hwnd


def wait_for_window_by_title(substring: str, timeout: float = 60.0) -> int | None:
    deadline = time.time() + timeout
    hwnd = find_window_by_title(substring)
    while hwnd is None and time.time() < deadline:
        time.sleep(0.5)
        hwnd = find_window_by_title(substring)
    return hwnd
