"""Keep the translator running in the tray.

Copy text in Discord or any other app and a card stays on top with the
translation. Select text and press Ctrl+Alt+E to translate that
selection. Paste puts the translation back into the app you were using.

Hold the right Ctrl key, speak, and release. The words are cleaned up
and typed where the cursor already is. Press Ctrl+Alt+Space to keep
talking without holding the key. The tray icon can pause translation,
turn voice typing off, or stop launching with Windows.
"""

import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import winreg
from ctypes import wintypes

import server

def install_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


ROOT = install_dir()
SETTINGS_PATH = os.path.join(ROOT, "settings.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "ToEnglish"
MUTEX_NAME = "Local\\ToEnglishTranslator"

WM_CLIPBOARDUPDATE = 0x031D
WM_HOTKEY = 0x0312
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_C = 0x43
VK_V = 0x56
VK_E = 0x45
VK_SPACE = 0x20
VK_RCONTROL = 0xA3
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
WH_KEYBOARD_LL = 13
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
LLKHF_UP = 0x80
LLKHF_INJECTED = 0x10
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
ERROR_ALREADY_EXISTS = 183
HOTKEY_ID = 1
HOTKEY_VOICE_ID = 2

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

kernel32.SetLastError.argtypes = [wintypes.DWORD]
kernel32.GetLastError.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL

user32.RegisterClassExW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.AddClipboardFormatListener.argtypes = [wintypes.HWND]
user32.AddClipboardFormatListener.restype = wintypes.BOOL
user32.RemoveClipboardFormatListener.argtypes = [wintypes.HWND]
user32.RemoveClipboardFormatListener.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

if ctypes.sizeof(ctypes.c_void_p) == 8:
    get_window_long = user32.GetWindowLongPtrW
    set_window_long = user32.SetWindowLongPtrW
else:
    get_window_long = user32.GetWindowLongW
    set_window_long = user32.SetWindowLongW
get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
get_window_long.restype = ctypes.c_ssize_t
set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
set_window_long.restype = ctypes.c_ssize_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = (
            ("ki", KEYBDINPUT),
            ("mi", MOUSEINPUT),
            ("hi", HARDWAREINPUT),
        )

    _anonymous_ = ("_input",)
    _fields_ = (("type", wintypes.DWORD), ("_input", _INPUT))


user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


HOTKEY_CHOICES = (
    (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x45, "Ctrl+Alt+E"),
    (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x45, "Ctrl+Shift+E"),
    (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x54, "Ctrl+Alt+T"),
)

QUICK_LANGS = (
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("ru", "Russian"),
    ("bg", "Bulgarian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh-CN", "Mandarin"),
    ("zh-TW", "Chinese (Traditional)"),
    ("ar", "Arabic"),
    ("hi", "Hindi"),
    ("tr", "Turkish"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("uk", "Ukrainian"),
    ("vi", "Vietnamese"),
    ("th", "Thai"),
    ("id", "Indonesian"),
    ("el", "Greek"),
    ("he", "Hebrew"),
    ("sv", "Swedish"),
)


def pythonw_path():
    folder = os.path.dirname(os.path.abspath(sys.executable))
    candidate = os.path.join(folder, "pythonw.exe")
    if os.path.exists(candidate):
        return candidate
    return sys.executable


def startup_command():
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}"'
    script = os.path.join(ROOT, "always.py")
    return f'"{pythonw_path()}" "{script}"'


def ensure_packages():
    if getattr(sys, "frozen", False):
        return
    needed = []
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        needed.extend(["pystray", "pillow"])
    try:
        import sounddevice  # noqa: F401
        import numpy  # noqa: F401
        import faster_whisper  # noqa: F401
    except ImportError:
        needed.extend(["sounddevice", "numpy", "faster-whisper"])
    if needed:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *needed])


def relaunch_hidden():
    if getattr(sys, "frozen", False):
        return
    if os.path.basename(sys.executable).lower() == "pythonw.exe":
        return
    if "--console" in sys.argv:
        return
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [pythonw_path(), os.path.join(ROOT, "always.py")],
        cwd=ROOT,
        close_fds=True,
        creationflags=flags,
    )
    raise SystemExit(0)


def _language_setting(value, default, allow_auto=False):
    if not isinstance(value, str):
        return default
    value = value.strip()
    if allow_auto and value == "auto":
        return "auto"
    if value in server.LANGUAGE_NAMES:
        return value
    return default


def _point(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "paused": bool(data.get("paused", False)),
        "startup": bool(data.get("startup", True)),
        "welcomed": bool(data.get("welcomed", False)),
        "voice": bool(data.get("voice", True)),
        "voice_english": bool(data.get("voice_english", False)),
        "voice_welcomed": bool(data.get("voice_welcomed", False)),
        "source": _language_setting(data.get("source"), "auto", allow_auto=True),
        "target": _language_setting(data.get("target"), "en"),
        "popup_x": _point(data.get("popup_x")),
        "popup_y": _point(data.get("popup_y")),
    }


def patch_settings(**changes):
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw.update(changes)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
        json.dump(raw, handle)
    return load_settings()


def set_startup(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
            return
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass


def claim_single_instance():
    kernel32.SetLastError(0)
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        raise SystemExit(0)
    return handle


def looks_like_url_or_path(text):
    stripped = text.strip()
    if "\n" in stripped or len(stripped) > 400:
        return False
    lowered = stripped.lower()
    if lowered.startswith(("http://", "https://", "www.", "ftp://")):
        return True
    if re.match(r"^[a-zA-Z]:\\", stripped) or stripped.startswith("\\\\"):
        return True
    if " " not in stripped and re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", stripped):
        return True
    return False


def looks_like_secret(text):
    stripped = text.strip()
    if "\n" in stripped or any(ch.isspace() for ch in stripped):
        return False
    if any(ord(ch) > 127 for ch in stripped):
        return False
    return any(ch.isdigit() or not ch.isalnum() for ch in stripped)


def worth_auto(text):
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) < 2 and not any(ord(ch) > 127 for ch in stripped):
        return False
    if looks_like_url_or_path(stripped) or looks_like_secret(stripped):
        return False
    return any(ch.isalpha() for ch in stripped)


def open_clipboard():
    for _ in range(10):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def read_clipboard():
    if not open_clipboard():
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def write_clipboard(text):
    data = text.encode("utf-16-le") + b"\x00\x00"
    memory = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not memory:
        return False
    pointer = kernel32.GlobalLock(memory)
    if not pointer:
        return False
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(memory)
    if not open_clipboard():
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        if not user32.SetClipboardData(CF_UNICODETEXT, memory):
            return False
        memory = None
        return True
    finally:
        user32.CloseClipboard()


def key_held(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def send_key(vk, up=False):
    event = INPUT()
    event.type = INPUT_KEYBOARD
    event.ki.wVk = vk
    event.ki.wScan = user32.MapVirtualKeyW(vk, 0)
    event.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    event.ki.time = 0
    event.ki.dwExtraInfo = 0
    return user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) == 1


def release_modifiers():
    for vk in (
        VK_SHIFT, VK_CONTROL, VK_MENU,
        0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,
        0x5B, 0x5C, VK_E, 0x54,
    ):
        if key_held(vk):
            send_key(vk, up=True)


def prepare_shortcut_release():
    watched = (
        VK_SHIFT, VK_CONTROL, VK_MENU,
        0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,
        VK_E,
    )
    deadline = time.time() + 0.8
    while time.time() < deadline and any(key_held(vk) for vk in watched):
        time.sleep(0.02)
    release_modifiers()
    time.sleep(0.04)


def send_ctrl_chord(key):
    release_modifiers()
    time.sleep(0.03)
    ok = send_key(VK_CONTROL, up=False)
    time.sleep(0.02)
    ok = send_key(key, up=False) and ok
    time.sleep(0.03)
    ok = send_key(key, up=True) and ok
    ok = send_key(VK_CONTROL, up=True) and ok
    return ok


def send_ctrl_c():
    return send_ctrl_chord(VK_C)


def send_ctrl_v():
    return send_ctrl_chord(VK_V)


def language_choices(include_auto):
    rows = [("auto", "Detect language")] if include_auto else []
    rows.extend(QUICK_LANGS)
    quick_codes = {code for code, _name in QUICK_LANGS}
    quick_codes.add("iw")
    rest = sorted(
        (
            (code, name)
            for code, name in server.LANGUAGE_NAMES.items()
            if code not in quick_codes
        ),
        key=lambda item: item[1].lower(),
    )
    rows.extend(rest)
    choices = []
    seen_codes = set()
    seen_names = set()
    for code, name in rows:
        if code in seen_codes or name in seen_names:
            continue
        seen_codes.add(code)
        seen_names.add(name)
        choices.append((code, name))
    return choices


def focus_window(hwnd):
    if not hwnd or not user32.IsWindow(hwnd):
        return
    foreground = user32.GetForegroundWindow()
    if foreground == hwnd:
        return
    current = kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(current, foreground_thread, True)
    if target_thread and target_thread != foreground_thread:
        user32.AttachThreadInput(current, target_thread, True)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(current, foreground_thread, False)
    if target_thread and target_thread != foreground_thread:
        user32.AttachThreadInput(current, target_thread, False)


def work_area_at_cursor():
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    monitor = user32.MonitorFromPoint(point, 2)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return point.x, point.y, RECT(0, 0, 1280, 800)
    return point.x, point.y, info.rcWork


class TranslatorApp:
    def __init__(self, ui):
        self.ui = ui
        self.settings = load_settings()
        self.lock = threading.Lock()
        self.clip_lock = threading.Lock()
        self.hwnd = None
        self.proc = None
        self.gen = 0
        self.last_source = None
        self.own_text = None
        self.own_until = 0
        self.capturing = False
        self.debounce = None
        self.hotkey_label = "Ctrl+Alt+E"
        self.icon = None
        self.voice_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.voice_thread = None
        self.voice_kind = "ptt"
        self.voice_hwnd = None
        self.right_down = False
        self.ptt = False
        self.pending_stop = False
        self.last_tap = 0.0
        self.hold_timer = None
        self.hook = None
        self.hook_proc = None
        self.voice_hotkey = False
        self.last_text = ""
        self.last_hwnd = None

    @property
    def paused(self):
        return self.settings["paused"]

    def remember_own_clipboard(self, text, seconds=1.2):
        with self.lock:
            self.own_text = text
            self.own_until = time.time() + seconds

    def copy_english(self, text):
        self.remember_own_clipboard(text)
        with self.clip_lock:
            write_clipboard(text)

    def active_languages(self):
        fresh = load_settings()
        self.settings["source"] = fresh["source"]
        self.settings["target"] = fresh["target"]
        return fresh["source"], fresh["target"]

    def set_languages(self, source, target):
        source = source if source == "auto" or source in server.LANGUAGE_NAMES else "auto"
        target = target if target in server.LANGUAGE_NAMES else "en"
        self.settings = patch_settings(source=source, target=target)

    def consider(self, text, forced, hwnd=None):
        text = (text or "").replace("\r\n", "\n").strip()
        if not text:
            if forced:
                self.ui.show("Heads up", "Select some text first, then press the hotkey.", "", copy=False)
            return
        if not forced and (self.paused or not worth_auto(text)):
            with self.lock:
                self.gen += 1
            return
        if not forced and text == self.last_source:
            return
        if len(text) > server.MAX_CHARS:
            if forced:
                self.ui.show(
                    "Heads up",
                    f"Keep a selection under {server.MAX_CHARS:,} characters.",
                    "",
                    copy=False,
                )
            return
        self.last_text = text
        if hwnd:
            self.last_hwnd = hwnd
        with self.lock:
            self.gen += 1
            gen = self.gen
            self.last_source = text
        threading.Thread(
            target=self._translate,
            args=(text, forced, gen, hwnd or self.last_hwnd),
            daemon=True,
        ).start()

    def _translate(self, text, forced, gen, hwnd):
        try:
            source, target = self.active_languages()
            result = server.translate_text(text, source, target)
        except Exception:
            with self.lock:
                if self.last_source == text:
                    self.last_source = None
            if forced and gen == self.gen:
                self.ui.show(
                    "Heads up",
                    "Couldn't reach the translator. Check your connection and try again.",
                    "",
                    copy=False,
                )
            return
        if gen != self.gen:
            return
        translation = (result.get("translation") or result.get("english") or "").strip()
        if not translation:
            if forced:
                target_name = result.get("target") or "that language"
                self.ui.show("Heads up", f"No {target_name} translation came back.", "", copy=False)
            return
        if not forced and server.same_language(result.get("code"), target):
            return
        self.ui.show(
            result.get("target") or "Translation",
            translation,
            result.get("note") or "",
            original=text,
            paste=translation,
            hwnd=hwnd,
        )

    def on_clipboard(self):
        if self.capturing:
            return
        if self.debounce:
            self.debounce.cancel()
        self.debounce = threading.Timer(0.3, self._deliver_clipboard)
        self.debounce.daemon = True
        self.debounce.start()

    def _deliver_clipboard(self):
        if self.capturing:
            return
        with self.clip_lock:
            text = read_clipboard()
        if not text:
            return
        with self.lock:
            if text == self.own_text and time.time() < self.own_until:
                return
        self.consider(text, forced=False, hwnd=user32.GetForegroundWindow())

    def on_hotkey(self):
        threading.Thread(target=self._capture_selection, daemon=True).start()

    def _voice_busy(self):
        return self.voice_thread is not None and self.voice_thread.is_alive()

    def _voice_recording(self):
        return self._voice_busy() and not self.stop_event.is_set()

    def _on_right_ctrl(self, is_up):
        if not self.settings.get("voice", True):
            return False
        action = None
        with self.voice_lock:
            if not is_up:
                if self.right_down:
                    return True
                self.right_down = True
                if self._voice_recording() and self.voice_kind == "hands":
                    self.pending_stop = True
                    return True
                if self._voice_busy():
                    return True
                timer = threading.Timer(0.18, self._hold_fired)
                timer.daemon = True
                self.hold_timer = timer
                timer.start()
                return True
            self.right_down = False
            if self.hold_timer:
                self.hold_timer.cancel()
                self.hold_timer = None
            if self.ptt:
                self.ptt = False
                action = "stop"
            elif self.pending_stop:
                self.pending_stop = False
                action = "stop"
            else:
                now = time.time()
                if now - self.last_tap <= 0.4:
                    self.last_tap = 0.0
                    action = "hands"
                else:
                    self.last_tap = now
        if action == "stop":
            self.stop_event.set()
        elif action == "hands":
            self.request_start("hands")
        return True

    def _hold_fired(self):
        if not self.settings.get("voice", True):
            return
        with self.voice_lock:
            if not self.right_down or self.ptt or self._voice_busy():
                return
        self.request_start("ptt")

    def request_start(self, kind):
        with self.voice_lock:
            if self._voice_busy():
                return False
            if kind == "ptt" and not self.right_down:
                return False
            self.stop_event.clear()
            self.voice_kind = kind
            self.voice_hwnd = user32.GetForegroundWindow()
            if kind == "ptt":
                self.ptt = True
            hwnd = self.voice_hwnd
            self.voice_thread = threading.Thread(
                target=self._voice_session,
                args=(kind, hwnd),
                daemon=True,
                name="voice",
            )
            self.voice_thread.start()
            return True

    def on_voice_toggle(self):
        if not self.settings.get("voice", True):
            self.ui.show(
                "Voice",
                "Voice typing is off. Right-click the tray icon and turn it on.",
                "",
                copy=False,
            )
            return
        with self.voice_lock:
            recording = self._voice_recording()
        if recording:
            with self.voice_lock:
                self.ptt = False
                self.pending_stop = False
            self.stop_event.set()
            return
        self.request_start("hands")

    def paste_voice(self, text, hwnd):
        self.capturing = True
        try:
            with self.clip_lock:
                previous = read_clipboard()
                if not write_clipboard(text):
                    return False
                sequence = user32.GetClipboardSequenceNumber()
            self.remember_own_clipboard(text, seconds=2.5)
            focus_window(hwnd)
            time.sleep(0.06)
            pasted = send_ctrl_v()
            time.sleep(0.35)
            if pasted and previous is not None:
                with self.clip_lock:
                    if user32.GetClipboardSequenceNumber() == sequence:
                        self.remember_own_clipboard(previous, seconds=2.0)
                        write_clipboard(previous)
            return bool(pasted)
        finally:
            self.capturing = False

    def paste_into(self, text, hwnd):
        if not hwnd or not user32.IsWindow(hwnd):
            hwnd = user32.GetForegroundWindow()
        return self.paste_voice(text, hwnd)

    def _voice_session(self, kind, hwnd):
        try:
            import voice
        except Exception:
            self.ui.events.put(("pill", None))
            self.ui.show(
                "Voice",
                "Voice typing still needs its setup. Run start.bat and leave that window open until it finishes.",
                "",
                copy=False,
            )
            return
        if kind == "ptt":
            label = "Listening · release to type"
        elif self.voice_hotkey:
            label = "Listening · Ctrl+Alt+Space to finish"
        else:
            label = "Listening · tap right Ctrl to finish"
        self.ui.events.put(("pill", label))
        try:
            audio = voice.capture(self.stop_event)
            duration = (audio.size / voice.RATE) if audio is not None else 0
            if voice.too_quiet(audio):
                if duration >= 0.6:
                    self.ui.show("Voice", "Didn't catch that.", "", copy=False)
                return
            self.ui.events.put(("pill", "Writing" if voice.model_ready() else "Getting voice ready…"))
            heard = voice.transcribe(audio, english=bool(self.settings.get("voice_english")))
            text = voice.polish(heard)
            if not text:
                self.ui.show("Voice", "Didn't catch that.", "", copy=False)
                return
            if not self.paste_voice(text, hwnd):
                self.ui.show("Voice", "Couldn't type that into the box. Click it and try again.", "", copy=False)
        except voice.VoiceError as exc:
            self.ui.show("Voice", str(exc), "", copy=False)
        except Exception:
            self.ui.show(
                "Voice",
                "Couldn't turn that speech into text. Check your connection if this is the first time.",
                "",
                copy=False,
            )
        finally:
            self.ui.events.put(("pill", None))

    def toggle_voice(self, icon, _item):
        self.settings = patch_settings(voice=not self.settings.get("voice", True))
        if not self.settings["voice"]:
            self.stop_event.set()
        self._refresh_icon()
        icon.update_menu()

    def toggle_voice_english(self, icon, _item):
        self.settings = patch_settings(voice_english=not self.settings.get("voice_english", False))
        icon.update_menu()

    def _capture_selection(self):
        hwnd = user32.GetForegroundWindow()
        self.capturing = True
        try:
            prepare_shortcut_release()
            with self.clip_lock:
                previous = read_clipboard()
            before = user32.GetClipboardSequenceNumber()
            send_ctrl_c()
            selected = previous
            for _ in range(30):
                time.sleep(0.03)
                with self.clip_lock:
                    selected = read_clipboard()
                if user32.GetClipboardSequenceNumber() != before and selected != previous:
                    break
            if previous is not None and selected != previous:
                self.remember_own_clipboard(previous)
                with self.clip_lock:
                    write_clipboard(previous)
            text = (selected or "").strip()
            if not text or text == (previous or "").strip():
                self.ui.show(
                    "Heads up",
                    "Couldn't read the selection. Highlight the words, then press the hotkey again. You can also copy them with Ctrl+C.",
                    "",
                    copy=False,
                )
                return
            self.consider(text, forced=True, hwnd=hwnd)
        finally:
            self.capturing = False

    def toggle_paused(self, icon, _item):
        self.settings = patch_settings(paused=not self.paused)
        self._refresh_icon()
        icon.update_menu()

    def toggle_startup(self, icon, _item):
        enabled = not self.settings["startup"]
        set_startup(enabled)
        self.settings = patch_settings(startup=enabled)
        icon.update_menu()

    def open_page(self, _icon, _item):
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{server.PORT}")

    def open_phone(self, _icon, _item):
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{server.PORT}/#phone")

    def quit(self, icon, _item):
        icon.visible = False
        icon.stop()
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        self.ui.events.put(("quit", None))

    def _refresh_icon(self):
        if not self.icon:
            return
        voice = "Hold right Ctrl to dictate." if self.settings.get("voice", True) else "Voice typing is off."
        if self.paused:
            self.icon.title = f"Translator is paused. {voice}"
        else:
            self.icon.title = (
                f"Translator. {voice} Select text in Discord or any app and press {self.hotkey_label}."
            )

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_CLIPBOARDUPDATE:
                self.on_clipboard()
                return 0
            if msg == WM_HOTKEY:
                if wparam == HOTKEY_VOICE_ID:
                    self.on_voice_toggle()
                else:
                    self.on_hotkey()
                return 0
            if msg == WM_CLOSE:
                user32.RemoveClipboardFormatListener(hwnd)
                user32.UnregisterHotKey(hwnd, HOTKEY_ID)
                user32.UnregisterHotKey(hwnd, HOTKEY_VOICE_ID)
                if self.hook:
                    user32.UnhookWindowsHookEx(self.hook)
                    self.hook = None
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def listen(self):
        self.proc = WNDPROC(self._wndproc)
        instance = kernel32.GetModuleHandleW(None)
        window_class = WNDCLASSEXW()
        window_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        window_class.lpfnWndProc = self.proc
        window_class.hInstance = instance
        window_class.lpszClassName = "ToEnglishListener"
        user32.RegisterClassExW(ctypes.byref(window_class))
        self.hwnd = user32.CreateWindowExW(
            0,
            "ToEnglishListener",
            "To English",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            instance,
            None,
        )
        if not self.hwnd:
            print("To English could not listen for copied text.", flush=True)
            return
        user32.AddClipboardFormatListener(self.hwnd)
        for modifiers, key, label in HOTKEY_CHOICES:
            if user32.RegisterHotKey(self.hwnd, HOTKEY_ID, modifiers, key):
                self.hotkey_label = label
                break
        self.voice_hotkey = bool(user32.RegisterHotKey(
            self.hwnd,
            HOTKEY_VOICE_ID,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
            VK_SPACE,
        ))
        self.hook_proc = HOOKPROC(self._keyboard_hook)
        self.hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.hook_proc, None, 0)
        self._refresh_icon()
        print(f"ready {self.hotkey_label} voice={bool(self.hook)}", flush=True)
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def _keyboard_hook(self, n_code, w_param, l_param):
        if n_code >= 0:
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                injected = bool(info.flags & LLKHF_INJECTED)
                if not injected and info.vkCode == VK_RCONTROL:
                    is_up = bool(info.flags & LLKHF_UP) or w_param in (WM_KEYUP, WM_SYSKEYUP)
                    if self._on_right_ctrl(is_up):
                        return 1
            except Exception:
                pass
        return user32.CallNextHookEx(self.hook, n_code, w_param, l_param)


class PopupUI:
    def __init__(self):
        self.events = queue.Queue()
        self.root = None
        self.window = None
        self.pill = None
        self.pill_label = None
        self.app = None
        self.paste_text = ""
        self.paste_hwnd = None
        self.placed = False
        self.filling = False
        self._top_job = None

    def show(self, language, english, note, copy=True, original="", paste=None, hwnd=None):
        self.events.put(("popup", {
            "title": language,
            "body": english,
            "note": note or "",
            "copy": bool(copy),
            "original": original or "",
            "paste": paste,
            "hwnd": hwnd,
        }))

    def _build(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
        root = tk.Tk()
        root.withdraw()
        self.root = root
        root.after(80, self._poll)
        return root

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "quit":
                    self.root.quit()
                    return
                if kind == "pill":
                    self._pill(payload)
                    continue
                if kind == "popup":
                    self._popup(payload)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _pill(self, label):
        if not label:
            if self.pill is not None:
                try:
                    self.pill.destroy()
                except tk.TclError:
                    pass
                self.pill = None
                self.pill_label = None
            return
        if self.pill is None:
            win = tk.Toplevel(self.root)
            self.pill = win
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg="#1c1a17")
            self.pill_label = tk.Label(
                win,
                text=label,
                bg="#1c1a17",
                fg="#f4efe6",
                font=("Segoe UI", 10),
                padx=14,
                pady=8,
            )
            self.pill_label.pack()
        else:
            self.pill_label.configure(text=label)
        self.pill.update_idletasks()
        width = self.pill.winfo_reqwidth()
        height = self.pill.winfo_reqheight()
        _cursor_x, _cursor_y, area = work_area_at_cursor()
        x = area.left + max(0, (area.right - area.left - width) // 2)
        y = area.bottom - height - 28
        self.pill.geometry(f"{width}x{height}+{int(x)}+{int(y)}")
        self._no_activate(self.pill)
        self.pill.lift()

    def _popup(self, payload):
        if self.window is None or not self._window_ok():
            self._build_card()
            self.placed = False
        self._fill_card(payload)
        if not self.placed:
            self._place_card()
            self.placed = True
        else:
            self._fit_card()
        try:
            self.window.deiconify()
        except tk.TclError:
            return
        self._no_activate(self.window)
        self._force_top(self.window)
        self._keep_on_top()

    def _window_ok(self):
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def _build_card(self):
        win = tk.Toplevel(self.root)
        self.window = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#2a2622")
        win.withdraw()

        card = tk.Frame(win, bg="#1c1a17")
        card.pack(fill="both", expand=True, padx=1, pady=1)
        card.grid_columnconfigure(0, weight=1)
        self.card = card

        head = tk.Frame(card, bg="#1c1a17")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        self.head = head

        from_choices = language_choices(True)
        into_choices = language_choices(False)
        self.from_codes = {name: code for code, name in from_choices}
        self.into_codes = {name: code for code, name in into_choices}
        self.from_names = {code: name for code, name in from_choices}
        self.into_names = {code: name for code, name in into_choices}
        self.from_var = tk.StringVar(value=from_choices[0][1])
        self.into_var = tk.StringVar(value=into_choices[0][1])

        tk.Label(head, text="From", bg="#1c1a17", fg="#a3988c", font=("Segoe UI", 9, "bold")).pack(side="left")
        self.from_menu = tk.OptionMenu(head, self.from_var, *[name for _code, name in from_choices], command=self._on_language)
        self._style_menu(self.from_menu)
        self.from_menu.pack(side="left", padx=(6, 10))
        tk.Label(head, text="Into", bg="#1c1a17", fg="#a3988c", font=("Segoe UI", 9, "bold")).pack(side="left")
        self.into_menu = tk.OptionMenu(head, self.into_var, *[name for _code, name in into_choices], command=self._on_language)
        self._style_menu(self.into_menu)
        self.into_menu.pack(side="left", padx=(6, 0))

        close = tk.Button(
            head,
            text="×",
            command=self._hide_card,
            bd=0,
            bg="#1c1a17",
            fg="#a3988c",
            activebackground="#1c1a17",
            activeforeground="#f4efe6",
            font=("Segoe UI", 14),
            cursor="hand2",
            padx=6,
        )
        close.pack(side="right")

        self.original_label = tk.Label(card, text="Original", bg="#1c1a17", fg="#a3988c", font=("Segoe UI", 9, "bold"), anchor="w")
        self.original_label.grid(row=1, column=0, sticky="ew", padx=12, pady=(10, 0))
        self.original_box = self._text_box(card, 11, 3, "#cbbba8")
        self.original_box.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 0))

        self.translation_label = tk.Label(card, text="Translation", bg="#1c1a17", fg="#e38b74", font=("Segoe UI", 9, "bold"), anchor="w")
        self.translation_label.grid(row=3, column=0, sticky="ew", padx=12, pady=(10, 0))
        holder = tk.Frame(card, bg="#1c1a17")
        holder.grid(row=4, column=0, sticky="ew", padx=12, pady=(2, 0))
        self.translation_box = self._text_box(holder, 16, 7, "#f4efe6")
        scroll = tk.Scrollbar(holder, command=self.translation_box.yview)
        self.translation_box.configure(yscrollcommand=scroll.set)
        self.translation_box.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.note_label = tk.Label(card, text="", bg="#1c1a17", fg="#a3988c", font=("Segoe UI", 9), anchor="w", justify="left", wraplength=420)
        self.note_label.grid(row=5, column=0, sticky="ew", padx=12, pady=(6, 0))

        foot = tk.Frame(card, bg="#1c1a17")
        foot.grid(row=6, column=0, sticky="ew", padx=12, pady=(8, 12))
        self.foot = foot
        self.copy_button = tk.Button(
            foot,
            text="Copy",
            command=self._copy_translation,
            bd=0,
            bg="#2a2622",
            fg="#f4efe6",
            activebackground="#3a342c",
            activeforeground="#f4efe6",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=14,
            pady=6,
        )
        self.copy_button.pack(side="left")
        self.paste_button = tk.Button(
            foot,
            text="Paste",
            command=self._paste_translation,
            bd=0,
            bg="#f4efe6",
            fg="#141210",
            activebackground="#e7e0d6",
            activeforeground="#141210",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=16,
            pady=6,
        )
        self.paste_button.pack(side="right")

        drag = {"x": 0, "y": 0}

        def start_drag(event):
            drag["x"] = event.x_root
            drag["y"] = event.y_root

        def do_drag(event):
            win.geometry(f"+{win.winfo_x() + event.x_root - drag['x']}+{win.winfo_y() + event.y_root - drag['y']}")
            drag["x"] = event.x_root
            drag["y"] = event.y_root

        for widget in (head, self.original_label, self.translation_label):
            widget.bind("<Button-1>", start_drag)
            widget.bind("<B1-Motion>", do_drag)
            widget.bind("<ButtonRelease-1>", lambda _event: self._remember_place())

    def _style_menu(self, menu):
        menu.configure(
            bg="#2a2622",
            fg="#f4efe6",
            activebackground="#3a342c",
            activeforeground="#f4efe6",
            highlightthickness=0,
            relief="flat",
            font=("Segoe UI", 10),
            width=22,
        )
        menu["menu"].configure(bg="#2a2622", fg="#f4efe6", activebackground="#3a342c", activeforeground="#f4efe6", font=("Segoe UI", 10))

    def _text_box(self, parent, size, height, color):
        box = tk.Text(
            parent,
            height=height,
            width=42,
            wrap="word",
            bg="#1c1a17",
            fg=color,
            insertbackground=color,
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", size),
            padx=0,
            pady=0,
        )
        box.bind("<Key>", lambda _event: "break")
        box.bind("<MouseWheel>", lambda event, widget=box: self._wheel(widget, event))
        return box

    def _wheel(self, widget, event):
        widget.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _write_box(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")
        widget.configure(bg="#1c1a17")

    def _fill_card(self, payload):
        source, target = ("auto", "en")
        if self.app:
            source, target = self.app.active_languages()
        self.filling = True
        self.from_var.set(self.from_names.get(source, "Detect language"))
        self.into_var.set(self.into_names.get(target, "English"))
        self.filling = False

        original = (payload.get("original") or "").strip()
        body = payload.get("body") or ""
        note = payload.get("note") or ""
        self.paste_text = payload.get("paste") or ""
        self.paste_hwnd = payload.get("hwnd")
        self.translation_label.configure(text=payload.get("title") or "Translation")
        if original:
            shown = original if len(original) <= 1200 else original[:1200].rstrip() + "…"
            self._write_box(self.original_box, shown)
            self.original_label.grid()
            self.original_box.grid()
        else:
            self.original_label.grid_remove()
            self.original_box.grid_remove()
        shown_body = body if len(body) <= 4000 else body[:4000].rstrip() + "…"
        self._write_box(self.translation_box, shown_body)
        if note:
            self.note_label.configure(text=note)
            self.note_label.grid()
        else:
            self.note_label.grid_remove()
        if payload.get("copy"):
            self.copy_button.configure(text="Copy")
            self.copy_button.pack(side="left")
        else:
            self.copy_button.pack_forget()
        if self.paste_text:
            self.paste_button.configure(text="Paste")
            self.paste_button.pack(side="right")
        else:
            self.paste_button.pack_forget()
        if payload.get("copy") or self.paste_text:
            self.foot.grid()
        else:
            self.foot.grid_remove()

    def _on_language(self, _name=None):
        if self.filling or not self.app:
            return
        source = self.from_codes.get(self.from_var.get(), "auto")
        target = self.into_codes.get(self.into_var.get(), "en")
        self.app.set_languages(source, target)
        if self.app.last_text:
            self.app.consider(self.app.last_text, True, self.app.last_hwnd)

    def _copy_translation(self):
        text = self.translation_box.get("1.0", "end").strip()
        if not text or not self.app:
            return
        self.app.copy_english(text)
        self.copy_button.configure(text="Copied")

    def _paste_translation(self):
        if not self.paste_text or not self.app:
            return
        ok = self.app.paste_into(self.paste_text, self.paste_hwnd)
        self.paste_button.configure(text="Pasted" if ok else "Now press Ctrl+V")

    def _hide_card(self):
        if self._top_job and self.root:
            try:
                self.root.after_cancel(self._top_job)
            except tk.TclError:
                pass
            self._top_job = None
        if self.window:
            try:
                self.window.withdraw()
            except tk.TclError:
                pass

    def _remember_place(self):
        if not self.app or not self.window:
            return
        self.app.settings = patch_settings(popup_x=self.window.winfo_x(), popup_y=self.window.winfo_y())

    def _place_card(self):
        win = self.window
        win.update_idletasks()
        width = max(win.winfo_reqwidth(), 460)
        height = win.winfo_reqheight()
        _cursor_x, _cursor_y, area = work_area_at_cursor()
        saved_x = self.app.settings.get("popup_x") if self.app else None
        saved_y = self.app.settings.get("popup_y") if self.app else None
        if (
            isinstance(saved_x, int)
            and isinstance(saved_y, int)
            and area.left - 40 <= saved_x <= area.right - 80
            and area.top - 40 <= saved_y <= area.bottom - 40
        ):
            x, y = saved_x, saved_y
        else:
            x = area.right - width - 18
            y = area.top + 18
        if y + height > area.bottom:
            y = max(area.top + 8, area.bottom - height - 8)
        win.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")

    def _fit_card(self):
        win = self.window
        win.update_idletasks()
        width = max(win.winfo_width(), win.winfo_reqwidth(), 460)
        height = win.winfo_reqheight()
        win.geometry(f"{int(width)}x{int(height)}+{win.winfo_x()}+{win.winfo_y()}")

    def _force_top(self, win):
        try:
            win.attributes("-topmost", True)
            win.lift()
        except tk.TclError:
            return
        child = win.winfo_id()
        parent = user32.GetParent(child) or child
        user32.SetWindowPos(
            parent,
            wintypes.HWND(HWND_TOPMOST),
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def _keep_on_top(self):
        if self._top_job and self.root:
            try:
                self.root.after_cancel(self._top_job)
            except tk.TclError:
                pass
        def tick():
            self._top_job = None
            if not self.window or not self._window_ok():
                return
            try:
                if not self.window.winfo_viewable():
                    return
            except tk.TclError:
                return
            self._force_top(self.window)
            self._top_job = self.root.after(800, tick)
        self._top_job = self.root.after(800, tick)

    def _no_activate(self, win):
        child = win.winfo_id()
        parent = user32.GetParent(child)
        hwnd = parent or child
        style = get_window_long(hwnd, GWL_EXSTYLE)
        set_window_long(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)



def make_icon_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(159, 45, 22, 255))
    draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill=(255, 250, 243, 255))
    ink = (28, 22, 18, 255)
    draw.rectangle((18, 18, 46, 24), fill=ink)
    draw.rectangle((18, 29, 40, 35), fill=ink)
    draw.rectangle((18, 40, 46, 46), fill=ink)
    draw.rectangle((18, 18, 24, 46), fill=ink)
    return image


def build_menu(app):
    from pystray import Menu, MenuItem

    return Menu(
        MenuItem(
            lambda _item: "Hold right Ctrl to dictate" if app.settings.get("voice", True) else "Voice typing is off",
            None,
            enabled=False,
        ),
        MenuItem(
            "Voice typing",
            app.toggle_voice,
            checked=lambda _item: app.settings.get("voice", True),
        ),
        MenuItem(
            "Type speech in English",
            app.toggle_voice_english,
            checked=lambda _item: app.settings.get("voice_english", False),
        ),
        Menu.SEPARATOR,
        MenuItem(lambda _item: f"In any app: {app.hotkey_label}", None, enabled=False),
        MenuItem(
            "Translate text I copy",
            app.toggle_paused,
            checked=lambda _item: not app.paused,
        ),
        MenuItem(
            "Run when Windows starts",
            app.toggle_startup,
            checked=lambda _item: app.settings["startup"],
        ),
        MenuItem("Open translator page", app.open_page),
        MenuItem("Use on your phone", app.open_phone),
        Menu.SEPARATOR,
        MenuItem("Quit", app.quit),
    )


def run_icon(app):
    from pystray import Icon

    icon = Icon("To English", make_icon_image(), "To English", build_menu(app))
    app.icon = icon

    def setup(ready):
        ready.visible = True
        app._refresh_icon()
        if not app.settings.get("voice_welcomed"):
            ready.notify(
                "Hold the right Ctrl key and speak. The words are typed where your cursor is.",
                "Voice typing is on",
            )
            app.settings = patch_settings(voice_welcomed=True, welcomed=True)
        elif not app.settings["welcomed"]:
            ready.notify(
                f"Select text in Discord or any app and press {app.hotkey_label}.",
                "Translator is on",
            )
            app.settings = patch_settings(welcomed=True)

    icon.run(setup)


def preload_voice():
    try:
        import voice

        voice.get_model()
    except Exception:
        return


def main():
    os.chdir(ROOT)
    ensure_packages()
    relaunch_hidden()
    held_mutex = claim_single_instance()
    set_startup(load_settings()["startup"])
    server.start_background()

    ui = PopupUI()
    app = TranslatorApp(ui)
    ui.app = app
    threading.Thread(target=app.listen, daemon=True, name="clipboard").start()
    threading.Thread(target=run_icon, args=(app,), daemon=True, name="tray").start()
    threading.Thread(target=preload_voice, daemon=True, name="voice-model").start()
    ui._build().mainloop()


if __name__ == "__main__":
    main()
