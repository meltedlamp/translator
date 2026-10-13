"""Local translator: detect any language and turn it into English."""

import io
import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
HOST = "0.0.0.0"


def bundle_root():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


ROOT = bundle_root()
GOOGLE = "https://translate.googleapis.com/translate_a/single"
MAX_CHARS = 12000
CHUNK = 3500

LANGUAGE_NAMES = {
    "af": "Afrikaans",
    "am": "Amharic",
    "ar": "Arabic",
    "az": "Azerbaijani",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "ca": "Catalan",
    "ceb": "Cebuano",
    "co": "Corsican",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "eo": "Esperanto",
    "es": "Spanish",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "fy": "Frisian",
    "ga": "Irish",
    "gd": "Scots Gaelic",
    "gl": "Galician",
    "gu": "Gujarati",
    "ha": "Hausa",
    "haw": "Hawaiian",
    "he": "Hebrew",
    "hi": "Hindi",
    "hmn": "Hmong",
    "hr": "Croatian",
    "ht": "Haitian Creole",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "ig": "Igbo",
    "is": "Icelandic",
    "it": "Italian",
    "iw": "Hebrew",
    "ja": "Japanese",
    "jv": "Javanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "ku": "Kurdish",
    "ky": "Kyrgyz",
    "la": "Latin",
    "lb": "Luxembourgish",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mg": "Malagasy",
    "mi": "Maori",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Myanmar",
    "ne": "Nepali",
    "nl": "Dutch",
    "no": "Norwegian",
    "ny": "Nyanja",
    "or": "Odia",
    "pa": "Punjabi",
    "pl": "Polish",
    "ps": "Pashto",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "rw": "Kinyarwanda",
    "sd": "Sindhi",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sm": "Samoan",
    "sn": "Shona",
    "so": "Somali",
    "sq": "Albanian",
    "sr": "Serbian",
    "st": "Sesotho",
    "su": "Sundanese",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "tg": "Tajik",
    "th": "Thai",
    "tk": "Turkmen",
    "tl": "Filipino",
    "tr": "Turkish",
    "tt": "Tatar",
    "ug": "Uyghur",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "xh": "Xhosa",
    "yi": "Yiddish",
    "yo": "Yoruba",
    "zh": "Chinese",
    "zh-CN": "Mandarin",
    "zh-TW": "Chinese (Traditional)",
    "zu": "Zulu",
}


def language_name(code):
    if not code:
        return "Unknown"
    if code in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[code]
    base = code.split("-")[0]
    return LANGUAGE_NAMES.get(base, code)


def split_text(text, limit=CHUNK):
    if len(text) <= limit:
        return [text]
    parts = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + limit, length)
        if end < length:
            break_at = text.rfind("\n", start, end)
            if break_at > start + limit // 4:
                end = break_at + 1
        parts.append(text[start:end])
        start = end
    return parts


def same_language(detected, target):
    if not detected or not target:
        return False
    if detected == target:
        return True
    if "-" not in target and detected.split("-")[0] == target:
        return True
    return False


def translate_chunk(text, source="auto", target="en"):
    payload = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": source or "auto",
            "tl": target or "en",
            "dt": "t",
            "dj": "1",
            "q": text,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        GOOGLE,
        data=payload,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    translation = "".join(
        sentence["trans"]
        for sentence in data.get("sentences") or []
        if "trans" in sentence
    )
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None
    return {
        "translation": translation,
        "code": data.get("src") or "",
        "confidence": confidence,
        "weight": len(text),
    }


def translate_text(text, source="auto", target="en"):
    source = source if source in LANGUAGE_NAMES or source == "auto" else "auto"
    target = target if target in LANGUAGE_NAMES else "en"
    pieces = [translate_chunk(part, source, target) for part in split_text(text)]
    best = max(pieces, key=lambda piece: piece["weight"])
    code = best["code"]
    confidence = best["confidence"]
    target_name = language_name(target)
    note = ""
    if same_language(code, target):
        note = f"This already looks like {target_name}."
    elif source == "en" and code and not same_language(code, "en"):
        note = f"That was read as {language_name(code)}, not English."
    elif source == "auto" and confidence is not None and confidence < 0.35:
        note = "Low confidence. A very short line can be hard to place."
    translation = "".join(piece["translation"] for piece in pieces).strip()
    result = {
        "translation": translation,
        "language": language_name(code),
        "code": code,
        "target": target_name,
        "targetCode": target,
        "confidence": confidence,
        "note": note,
    }
    if target == "en":
        result["english"] = translation
    return result


def translate_to_english(text):
    return translate_text(text, "auto", "en")


def lan_ip():
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        address = probe.getsockname()[0]
        probe.close()
    except OSError:
        return None
    if not address or address.startswith("127."):
        return None
    return address


def phone_url():
    address = lan_ip()
    if not address:
        return None
    return f"http://{address}:{PORT}"


def settings_path():
    if getattr(sys, "frozen", False):
        folder = os.path.dirname(os.path.abspath(sys.executable))
    else:
        folder = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(folder, "settings.json")


def read_settings_file():
    try:
        with open(settings_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def clean_language(value, default, allow_auto=False):
    if not isinstance(value, str):
        return default
    value = value.strip()
    if allow_auto and value == "auto":
        return "auto"
    if value in LANGUAGE_NAMES:
        return value
    return default


def language_settings():
    data = read_settings_file()
    return {
        "source": clean_language(data.get("source"), "auto", allow_auto=True),
        "target": clean_language(data.get("target"), "en"),
        "chosen": "source" in data or "target" in data,
    }


def store_language_settings(source, target):
    data = read_settings_file()
    data["source"] = clean_language(source, "auto", allow_auto=True)
    data["target"] = clean_language(target, "en")
    with open(settings_path(), "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    return language_settings()


def phone_qr_png(url):
    import qrcode

    image = qrcode.make(url, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class TranslatorServer(ThreadingHTTPServer):
    allow_reuse_address = True


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".webmanifest": "application/manifest+json; charset=utf-8",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if sys.stderr is None:
            return
        try:
            super().log_message(fmt, *args)
        except Exception:
            return

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/phone":
            self._json(200, {"url": phone_url()})
            return
        if path == "/api/settings":
            self._json(200, language_settings())
            return
        if path == "/phone-qr.png":
            url = phone_url()
            if not url:
                self._json(404, {"error": "This laptop is not on Wi-Fi."})
                return
            try:
                png = phone_qr_png(url)
            except Exception:
                self._json(500, {"error": "Could not make the phone code."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)
            return
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/dictate":
            self._dictate()
            return
        if path == "/api/settings":
            self._save_settings()
            return
        if path != "/api/translate":
            self._json(404, {"error": "Not found."})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 200_000:
            self._json(413, {"error": "That text is too long."})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "Send plain text to translate."})
            return
        text = body.get("text") if isinstance(body, dict) else ""
        if not isinstance(text, str):
            text = ""
        text = text.strip()
        if not text:
            self._json(400, {"error": "Enter some text to translate."})
            return
        if len(text) > MAX_CHARS:
            self._json(
                400,
                {"error": f"Keep it under {MAX_CHARS:,} characters."},
            )
            return
        target = body.get("target") if isinstance(body, dict) else "en"
        source = body.get("source") if isinstance(body, dict) else "auto"
        if not isinstance(target, str) or target.strip() not in LANGUAGE_NAMES:
            target = "en"
        else:
            target = target.strip()
        if not isinstance(source, str) or source.strip() not in ("auto", *LANGUAGE_NAMES):
            source = "auto"
        else:
            source = source.strip()
        try:
            result = translate_text(text, source, target)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            self._json(
                502,
                {"error": "Could not reach the translator. Check your connection and try again."},
            )
            return
        if not result["translation"]:
            self._json(502, {"error": f"No {result['target']} translation came back."})
            return
        self._json(200, result)

    def _save_settings(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 20_000:
            self._json(413, {"error": "That text is too long."})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "Send the languages as JSON."})
            return
        if not isinstance(body, dict):
            body = {}
        self._json(200, store_language_settings(body.get("source"), body.get("target")))

    def _dictate(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            self._json(400, {"error": "Didn't catch that."})
            return
        if length > 8_000_000:
            self._json(413, {"error": "That recording is too long."})
            return
        raw = self.rfile.read(length)
        try:
            import voice
        except Exception:
            self._json(
                502,
                {"error": "Voice typing still needs its setup. Run start.bat and leave that window open until it finishes."},
            )
            return
        try:
            text = voice.dictate_bytes(raw)
        except voice.VoiceError as exc:
            self._json(400, {"error": str(exc)})
            return
        except Exception:
            self._json(502, {"error": "Couldn't turn that speech into text."})
            return
        self._json(200, {"text": text})

    def _json(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_background():
    """Serve the translator page without opening a browser or blocking."""

    def run():
        try:
            httpd = TranslatorServer((HOST, PORT), Handler)
        except OSError:
            return
        httpd.serve_forever()

    threading.Thread(target=run, daemon=True, name="translator-page").start()


def main():
    try:
        server = TranslatorServer((HOST, PORT), Handler)
    except OSError:
        print(f"Port {PORT} is already in use. Close the other translator window and try again.")
        sys.exit(1)
    url = f"http://127.0.0.1:{PORT}"
    print(f"To English is running at {url}", flush=True)
    shared = phone_url()
    if shared:
        print(f"On your phone, open {shared}", flush=True)
    print("Close this window to stop it.", flush=True)
    if "--browser" in sys.argv:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
