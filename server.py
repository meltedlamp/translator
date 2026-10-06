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
ROOT = os.path.dirname(os.path.abspath(__file__))
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


def translate_chunk(text):
    payload = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": "en",
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
    english = "".join(
        sentence["trans"]
        for sentence in data.get("sentences") or []
        if "trans" in sentence
    )
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None
    return {
        "english": english,
        "code": data.get("src") or "",
        "confidence": confidence,
        "weight": len(text),
    }


def translate_to_english(text):
    pieces = [translate_chunk(part) for part in split_text(text)]
    best = max(pieces, key=lambda piece: piece["weight"])
    code = best["code"]
    confidence = best["confidence"]
    note = ""
    if code == "en":
        note = "This already looks like English."
    elif confidence is not None and confidence < 0.35:
        note = "Low confidence. A very short line can be hard to place."
    return {
        "english": "".join(piece["english"] for piece in pieces).strip(),
        "language": language_name(code),
        "code": code,
        "confidence": confidence,
        "note": note,
    }


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
        if self.path.split("?", 1)[0] != "/api/translate":
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
        try:
            result = translate_to_english(text)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            self._json(
                502,
                {"error": "Could not reach the translator. Check your connection and try again."},
            )
            return
        if not result["english"]:
            self._json(502, {"error": "No English translation came back."})
            return
        self._json(200, result)

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
    if "--no-browser" not in sys.argv:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
