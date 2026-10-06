"""Keep To English running, and translate text from any app.

Copy text anywhere, and a small popup shows the English when the
language is not already English. Select text and press Ctrl+Alt+E
to translate that selection on purpose. The tray icon can pause this
or turn off launching with Windows.
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

ROOT = os.path.dirname(os.path.abspath(__file__))
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
VK_CONTROL = 0x11
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
ERROR_ALREADY_EXISTS = 183
HOTKEY_ID = 1

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


def pythonw_path():
    folder = os.path.dirname(os.path.abspath(sys.executable))
    candidate = os.path.join(folder, "pythonw.exe")
    if os.path.exists(candidate):
        return candidate
    return sys.executable


def startup_command():
    script = os.path.join(ROOT, "always.py")
    return f'"{pythonw_path()}" "{script}"'


def ensure_packages():
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pystray", "pillow"])


def relaunch_hidden():
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


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        data = {}
    return {
        "paused": bool(data.get("paused", False)),
        "startup": bool(data.get("startup", True)),
        "welcomed": bool(data.get("welcomed", False)),
    }


def save_settings(settings):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
        json.dump(settings, handle)


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


def send_ctrl_c():
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_C, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


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

    @property
    def paused(self):
        return self.settings["paused"]

    def remember_own_clipboard(self, text):
        with self.lock:
            self.own_text = text
            self.own_until = time.time() + 1.2

    def copy_english(self, text):
        self.remember_own_clipboard(text)
        with self.clip_lock:
            write_clipboard(text)

    def consider(self, text, forced):
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
        with self.lock:
            self.gen += 1
            gen = self.gen
            self.last_source = text
        threading.Thread(target=self._translate, args=(text, forced, gen), daemon=True).start()

    def _translate(self, text, forced, gen):
        try:
            result = server.translate_to_english(text)
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
        english = (result.get("english") or "").strip()
        if not english:
            if forced:
                self.ui.show("Heads up", "No English translation came back.", "", copy=False)
            return
        if not forced and result.get("code") == "en":
            return
        self.ui.show(result.get("language") or "English", english, result.get("note") or "")

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
        self.consider(text, forced=False)

    def on_hotkey(self):
        threading.Thread(target=self._capture_selection, daemon=True).start()

    def _capture_selection(self):
        self.capturing = True
        try:
            with self.clip_lock:
                previous = read_clipboard()
            send_ctrl_c()
            selected = previous
            for _ in range(12):
                time.sleep(0.04)
                with self.clip_lock:
                    selected = read_clipboard()
                if selected and selected != previous:
                    break
            if previous is not None and selected != previous:
                self.remember_own_clipboard(previous)
                with self.clip_lock:
                    write_clipboard(previous)
            text = (selected or "").strip()
            if not text or text == (previous or "").strip():
                self.ui.show("Heads up", "Select some text first, then press the hotkey.", "", copy=False)
                return
            self.consider(text, forced=True)
        finally:
            self.capturing = False

    def toggle_paused(self, icon, _item):
        self.settings["paused"] = not self.settings["paused"]
        save_settings(self.settings)
        self._refresh_icon()
        icon.update_menu()

    def toggle_startup(self, icon, _item):
        self.settings["startup"] = not self.settings["startup"]
        set_startup(self.settings["startup"])
        save_settings(self.settings)
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
        if self.paused:
            self.icon.title = f"To English is paused. Select text and press {self.hotkey_label}."
        else:
            self.icon.title = f"To English translates text you copy. Select text and press {self.hotkey_label}."

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_CLIPBOARDUPDATE:
                self.on_clipboard()
                return 0
            if msg == WM_HOTKEY:
                self.on_hotkey()
                return 0
            if msg == WM_CLOSE:
                user32.RemoveClipboardFormatListener(hwnd)
                user32.UnregisterHotKey(hwnd, HOTKEY_ID)
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
        self._refresh_icon()
        print(f"ready {self.hotkey_label}", flush=True)
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))


class PopupUI:
    def __init__(self):
        self.events = queue.Queue()
        self.root = None
        self.window = None
        self.app = None

    def show(self, language, english, note, copy=True):
        self.events.put(("popup", (language, english, note, copy)))

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
                if kind == "popup":
                    self._popup(*payload)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _popup(self, language, english, note, copy):
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        win = tk.Toplevel(self.root)
        self.window = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#e3d4bc")

        card = tk.Frame(win, bg="#fffaf3")
        card.pack(fill="both", expand=True, padx=1, pady=1)

        head = tk.Frame(card, bg="#fffaf3")
        head.pack(fill="x", padx=12, pady=(10, 0))
        badge = tk.Frame(head, bg="#fff6f2", highlightbackground="#9f2d16", highlightthickness=1)
        badge.pack(side="left")
        tk.Label(
            badge,
            text=language.upper(),
            bg="#fff6f2",
            fg="#9f2d16",
            font=("Segoe UI", 8, "bold"),
        ).pack(padx=6, pady=2)
        close = tk.Button(
            head,
            text="×",
            command=win.destroy,
            bd=0,
            bg="#fffaf3",
            fg="#6e6256",
            activebackground="#fffaf3",
            activeforeground="#1c1612",
            font=("Segoe UI", 13),
            cursor="hand2",
            padx=4,
        )
        close.pack(side="right")

        shown = english if len(english) <= 900 else english[:900].rstrip() + "…"
        tk.Label(
            card,
            text=shown,
            bg="#fffaf3",
            fg="#1c1612",
            font=("Georgia", 13),
            wraplength=336,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 4))

        if note:
            tk.Label(
                card,
                text=note,
                bg="#fffaf3",
                fg="#6e6256",
                font=("Segoe UI", 9),
                wraplength=336,
                justify="left",
            ).pack(fill="x", padx=12, pady=(0, 4))

        if copy:
            foot = tk.Frame(card, bg="#fffaf3")
            foot.pack(fill="x", padx=12, pady=(2, 12))
            button = tk.Button(
                foot,
                text="Copy English",
                bd=0,
                bg="#1c1612",
                fg="#fffaf3",
                activebackground="#3a312a",
                activeforeground="#fffaf3",
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
                padx=10,
                pady=4,
            )

            def copy_english():
                self.app.copy_english(english)
                button.configure(text="Copied")

            button.configure(command=copy_english)
            button.pack(side="right")

        drag = {"x": 0, "y": 0}

        def start_drag(event):
            drag["x"] = event.x
            drag["y"] = event.y

        def do_drag(event):
            win.geometry(f"+{win.winfo_x() + event.x - drag['x']}+{win.winfo_y() + event.y - drag['y']}")

        head.bind("<Button-1>", start_drag)
        head.bind("<B1-Motion>", do_drag)

        win.update_idletasks()
        width = max(win.winfo_reqwidth(), 360)
        height = win.winfo_reqheight()
        cursor_x, cursor_y, area = work_area_at_cursor()
        x = cursor_x + 18
        y = cursor_y + 18
        if x + width > area.right:
            x = area.right - width - 12
        if y + height > area.bottom:
            y = cursor_y - height - 18
        x = max(area.left + 8, x)
        y = max(area.top + 8, y)
        win.geometry(f"{width}x{height}+{int(x)}+{int(y)}")
        self._no_activate(win)
        win.lift()
        self._arm_hide(win)

    def _no_activate(self, win):
        child = win.winfo_id()
        parent = user32.GetParent(child)
        hwnd = parent or child
        style = get_window_long(hwnd, GWL_EXSTYLE)
        set_window_long(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

    def _arm_hide(self, win):
        state = {"job": None}

        def arm():
            if state["job"]:
                win.after_cancel(state["job"])
            state["job"] = win.after(20000, win.destroy)

        def enter(_event):
            if state["job"]:
                win.after_cancel(state["job"])
                state["job"] = None

        def leave(_event):
            arm()

        win.bind("<Enter>", enter)
        win.bind("<Leave>", leave)
        arm()


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
        MenuItem(lambda _item: f"Hotkey: {app.hotkey_label}", None, enabled=False),
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
        if not app.settings["welcomed"]:
            ready.notify(
                f"Copy text in any app, or select it and press {app.hotkey_label}.",
                "To English is on",
            )
            app.settings["welcomed"] = True
            save_settings(app.settings)

    icon.run(setup)


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
    ui._build().mainloop()


if __name__ == "__main__":
    main()
