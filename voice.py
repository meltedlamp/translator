"""Turn speech into text that can be typed into the focused app.

Hold the right Ctrl key, speak, and release. Filler and spoken
self-corrections are cleaned up before the words are pasted.
"""

import io
import os
import re
import threading
import time

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

RATE = 16000
MODEL_SIZE = "base"

_model = None
_model_lock = threading.Lock()
_transcribe_lock = threading.Lock()


class VoiceError(Exception):
    pass


def model_ready():
    return _model is not None


def get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            threads = max(1, min(8, os.cpu_count() or 4))
            _model = WhisperModel(
                MODEL_SIZE,
                device="cpu",
                compute_type="int8",
                cpu_threads=threads,
            )
        return _model


FILLER_RE = re.compile(r"\b(?:um+|uh+|erm+|hmm+|ah+|eh+)\b[,.]?\s*", re.I)
RETRACTION_CUES = ("scratch that", "start over", "forget that", "never mind")
CORRECTION_RE = re.compile(r"\b(?:actually|i mean|no wait|wait no)\b", re.I)
SPOKEN = (
    ("new paragraph", "\n\n"),
    ("new line", "\n"),
    ("question mark", "?"),
    ("exclamation mark", "!"),
    ("exclamation point", "!"),
    ("full stop", "."),
    ("open parentheses", "("),
    ("close parentheses", ")"),
    ("open quote", '"'),
    ("close quote", '"'),
    ("comma", ","),
    ("period", "."),
    ("colon", ":"),
)
HALLUCINATIONS = {
    "thanks for watching",
    "thank you for watching",
    "thanks for listening",
    "subtitles by the amara.org community",
    "amara.org",
}


def drop_retractions(text):
    lowered = text.lower()
    cut = -1
    length = 0
    for cue in RETRACTION_CUES:
        index = lowered.rfind(cue)
        if index > cut:
            cut = index
            length = len(cue)
    if cut < 0:
        return text
    return text[cut + length :].strip(" ,.-")


def apply_corrections(text):
    parts = CORRECTION_RE.split(text)
    if len(parts) == 1:
        return text
    current = parts[0].strip(" ,")
    for replacement in parts[1:]:
        replacement = replacement.strip(" ,")
        if not replacement:
            continue
        if not current:
            current = replacement
            continue
        new_words = replacement.split()
        old_words = current.split()
        if len(new_words) < len(old_words):
            current = " ".join(old_words[: -len(new_words)] + new_words)
        else:
            current = replacement
    return current


def apply_spoken_punctuation(text):
    for phrase, mark in SPOKEN:
        text = re.sub(rf"\b{re.escape(phrase)}\b", mark, text, flags=re.I)
    return text


def tidy(text):
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    text = re.sub(r"\s+([)\]\"])", r"\1", text)
    text = re.sub(r"([(\[\"])\s+", r"\1", text)
    text = re.sub(r"([,.;:?!])([^\s\n])", r"\1 \2", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def capitalize(text):
    chars = list(text)
    cap = True
    for index, char in enumerate(chars):
        if char.isalpha():
            if cap:
                chars[index] = char.upper()
            cap = False
        elif char in ".!?" or char == "\n":
            cap = True
    text = "".join(chars)
    return re.sub(r"\bi\b", "I", text)


def finish(text):
    if not text or text.endswith((".", "!", "?", "\n", '"', ")", ":")):
        return text
    if len(re.findall(r"\w+", text)) >= 4:
        return text + "."
    return text


def polish(text):
    """Drop filler, keep the corrected thought, and add spoken punctuation."""

    cleaned = " ".join((text or "").replace("\r\n", "\n").split())
    if not cleaned:
        return ""
    lowered = cleaned.lower().strip(" .!")
    if lowered in HALLUCINATIONS or "amara.org" in lowered:
        return ""
    cleaned = drop_retractions(cleaned)
    cleaned = apply_corrections(cleaned)
    cleaned = FILLER_RE.sub("", cleaned)
    cleaned = apply_spoken_punctuation(cleaned)
    cleaned = tidy(cleaned)
    cleaned = capitalize(cleaned)
    return finish(cleaned)


def too_quiet(audio, rate=RATE):
    import numpy as np

    if audio is None or getattr(audio, "size", 0) < int(rate * 0.28):
        return True
    rms = float(np.sqrt(np.mean(np.square(audio))))
    return rms < 0.008


def capture(stop_event, max_seconds=90, rate=RATE):
    import numpy as np
    import sounddevice as sd

    frames = []

    def callback(indata, _count, _time_info, _status):
        frames.append(indata.copy())

    try:
        stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32", callback=callback)
    except Exception as exc:
        raise VoiceError("No microphone is available.") from exc
    with stream:
        deadline = time.time() + max_seconds
        while time.time() < deadline:
            if stop_event.is_set():
                break
            stop_event.wait(0.05)
    if not frames:
        return np.zeros(0, dtype="float32")
    return np.concatenate(frames, axis=0).reshape(-1)


def transcribe(audio, english=False):
    import numpy as np

    samples = np.asarray(audio, dtype="float32").reshape(-1)
    if samples.size == 0:
        return ""
    task = "translate" if english else "transcribe"
    with _transcribe_lock:
        model = get_model()
        try:
            return _transcribe(model, samples, task, vad_filter=True)
        except Exception:
            return _transcribe(model, samples, task, vad_filter=False)


def _transcribe(model, samples, task, vad_filter):
    segments, _info = model.transcribe(
        samples,
        task=task,
        vad_filter=vad_filter,
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        without_timestamps=True,
    )
    return " ".join(part.text.strip() for part in segments if part.text).strip()


def decode_audio(raw, rate=RATE):
    import av
    import numpy as np

    if not raw:
        raise VoiceError("Didn't catch that.")
    try:
        container = av.open(io.BytesIO(raw))
    except Exception as exc:
        raise VoiceError("Could not read that recording.") from exc
    stream = next((item for item in container.streams if item.type == "audio"), None)
    if stream is None:
        raise VoiceError("Could not read that recording.")
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
    pieces = []

    def take(converted):
        if converted is None:
            return
        if not isinstance(converted, list):
            converted = [converted]
        for item in converted:
            pieces.append(np.asarray(item.to_ndarray(), dtype="float32").reshape(-1))

    for frame in container.decode(stream):
        take(resampler.resample(frame))
    try:
        take(resampler.resample(None))
    except Exception:
        pass
    if not pieces:
        raise VoiceError("Didn't catch that.")
    return np.concatenate(pieces)


def dictate_bytes(raw):
    audio = decode_audio(raw)
    if too_quiet(audio):
        raise VoiceError("Didn't catch that. Try again.")
    text = polish(transcribe(audio, english=False))
    if not text:
        raise VoiceError("Didn't catch that. Try again.")
    return text
