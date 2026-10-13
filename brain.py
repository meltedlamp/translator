"""On-device grammar brain.

The factory rules ship with the app. What the brain learns is written
beside the download, in brain.json, and stays on that device.
"""

import difflib
import json
import os
import re
import sys
import threading
import time

MAX_LESSONS = 1500
MAX_SPAN = 80

# Multi-word mistakes, longest first when applied.
PHRASES = (
    ("your welcome", "you're welcome"),
    ("could of", "could have"),
    ("should of", "should have"),
    ("would of", "would have"),
    ("must of", "must have"),
    ("more better", "better"),
    ("more easier", "easier"),
    ("more harder", "harder"),
    ("return back", "return"),
    ("revert back", "revert"),
    ("their is", "there is"),
    ("their are", "there are"),
    ("their was", "there was"),
    ("their were", "there were"),
    ("their going", "they're going"),
    ("their not", "they're not"),
    ("there going", "they're going"),
    ("there not", "they're not"),
    ("your going", "you're going"),
    ("your not", "you're not"),
    ("your the", "you're the"),
    ("your a", "you're a"),
    ("your an", "you're an"),
    ("its a", "it's a"),
    ("its the", "it's the"),
    ("its not", "it's not"),
    ("its been", "it's been"),
    ("eachother", "each other"),
    ("infront of", "in front of"),
    ("infront", "in front"),
    ("eventhough", "even though"),
    ("aswell", "as well"),
    ("atleast", "at least"),
)

WORDS = (
    ("dont", "don't"),
    ("doesnt", "doesn't"),
    ("didnt", "didn't"),
    ("cant", "can't"),
    ("wont", "won't"),
    ("isnt", "isn't"),
    ("arent", "aren't"),
    ("wasnt", "wasn't"),
    ("werent", "weren't"),
    ("hasnt", "hasn't"),
    ("havent", "haven't"),
    ("hadnt", "hadn't"),
    ("wouldnt", "wouldn't"),
    ("couldnt", "couldn't"),
    ("shouldnt", "shouldn't"),
    ("youre", "you're"),
    ("theyre", "they're"),
    ("im", "I'm"),
    ("ive", "I've"),
    ("youve", "you've"),
    ("theyve", "they've"),
    ("weve", "we've"),
    ("thats", "that's"),
    ("whats", "what's"),
    ("theres", "there's"),
    ("heres", "here's"),
    ("alot", "a lot"),
    ("noone", "no one"),
)
I_WORD = re.compile(r"(?<![\w.])i(?![\w.])")

AGREEMENT = (
    (re.compile(r"\b(he|she|it) don't\b", re.I), r"\1 doesn't"),
    (re.compile(r"\b(he|she|it) dont\b", re.I), r"\1 doesn't"),
    (re.compile(r"\b(we|they|you) was\b", re.I), r"\1 were"),
    (re.compile(r"\b(we|they|you) is\b", re.I), r"\1 are"),
    (re.compile(r"\b(we|they|you) has\b", re.I), r"\1 have"),
    (re.compile(r"\b(I|we|they|you) doesn't\b", re.I), r"\1 don't"),
)

DOUBLED = re.compile(
    r"\b(the|a|an|and|to|of|in|on|for)\s+\1\b",
    re.I,
)
ARTICLE = re.compile(r"\b(a|an)\s+([A-Za-z][A-Za-z']*)", re.I)
TAKES_AN = ("hour", "honest", "honor", "honour", "heir")
TAKES_A = {
    "one",
    "once",
    "university",
    "uniform",
    "union",
    "unique",
    "unit",
    "united",
    "user",
    "usual",
    "usually",
    "useful",
    "european",
    "euro",
    "eulogy",
    "utensil",
    "unicorn",
    "universal",
    "universe",
    "unanimous",
}

_lock = threading.Lock()


def brain_path():
    override = os.environ.get("TO_ENGLISH_BRAIN")
    if override:
        return override
    if getattr(sys, "frozen", False):
        folder = os.path.dirname(os.path.abspath(sys.executable))
    else:
        folder = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(folder, "brain.json")


def _empty():
    return {"version": 1, "lessons": {}}


def _load():
    try:
        with open(brain_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    lessons = data.get("lessons")
    if not isinstance(lessons, dict):
        lessons = {}
    clean = {}
    for key, item in lessons.items():
        if not isinstance(key, str) or not isinstance(item, dict):
            continue
        right = item.get("right")
        if not isinstance(right, str) or not right.strip():
            continue
        seen = item.get("seen")
        if not isinstance(seen, int) or seen < 1:
            seen = 1
        origin = item.get("from") if item.get("from") in ("text", "edit") else "text"
        clean[key] = {
            "right": right,
            "seen": seen,
            "from": origin,
            "at": item.get("at") if isinstance(item.get("at"), (int, float)) else 0,
        }
    return {"version": 1, "lessons": clean}


def _save(data):
    path = brain_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def ensure():
    """Create the brain beside the download if it is not there yet."""

    with _lock:
        if os.path.exists(brain_path()):
            return status()
        try:
            _save(_empty())
        except OSError:
            return status()
        return status()


def status():
    data = _load()
    lessons = data["lessons"]
    return {
        "lessons": len(lessons),
        "seen": sum(item["seen"] for item in lessons.values()),
        "where": brain_path(),
    }


def _match_case(sample, replacement):
    if not sample:
        return replacement
    if sample.isupper():
        return replacement.upper()
    letters = [char for char in sample if char.isalpha()]
    if letters and all(char.islower() for char in letters):
        return replacement
    sample_words = sample.split()
    repl_words = replacement.split()
    if (
        sample_words
        and len(sample_words) == len(repl_words)
        and all(word[:1].isupper() for word in sample_words if word[:1].isalpha())
    ):
        titled = []
        for word in repl_words:
            titled.append(word[:1].upper() + word[1:] if word else word)
        return " ".join(titled)
    if sample[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _canon_from_sample(sample, expanded):
    if sample.isupper():
        return expanded.lower()
    if sample[:1].isupper() and expanded[:1].isupper() and not expanded.startswith("I"):
        return expanded[:1].lower() + expanded[1:]
    return expanded


def _swap(pattern, repl, text, fixes, canonical=None):
    def replace(match):
        wrong = match.group(0)
        expanded = repl(match) if callable(repl) else match.expand(repl)
        right = expanded if callable(repl) else _match_case(wrong, expanded)
        if wrong == right:
            return wrong
        fixes.append(
            {
                "wrong": wrong,
                "right": right,
                "canonical": canonical if canonical is not None else _canon_from_sample(wrong, expanded),
            }
        )
        return right

    return pattern.sub(replace, text)


def _phrase_pattern(phrase):
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.I)


def _apply_phrases(text, fixes):
    for wrong, right in sorted(PHRASES, key=lambda item: len(item[0]), reverse=True):
        pattern = _phrase_pattern(wrong)

        def replace(match, right=right):
            sample = match.group(0)
            fixed = _match_case(sample, right)
            if sample == fixed:
                return sample
            fixes.append({"wrong": sample, "right": fixed, "canonical": right})
            return fixed

        text = pattern.sub(replace, text)
    return text


def _apply_words(text, fixes):
    for wrong, right in WORDS:
        text = _swap(_phrase_pattern(wrong), right, text, fixes, canonical=right)
    text = _swap(I_WORD, "I", text, fixes, canonical="I")
    return text


def _needs_an(word):
    if word.isupper() and 2 <= len(word) <= 6:
        return None
    lower = word.lower()
    if lower.startswith(TAKES_AN) or lower in {"heir", "heiress"}:
        return True
    if lower in TAKES_A:
        return False
    return lower[:1] in "aeiou"


def _apply_articles(text, fixes):
    def replace(match):
        article = match.group(1)
        word = match.group(2)
        needed = _needs_an(word)
        if needed is None:
            return match.group(0)
        want = "an" if needed else "a"
        if article.lower() == want:
            return match.group(0)
        fixed_article = _match_case(article, want)
        sample = match.group(0)
        right = fixed_article + " " + word
        fixes.append(
            {
                "wrong": sample,
                "right": right,
                "canonical": want + " " + word.lower(),
            }
        )
        return right

    return ARTICLE.sub(replace, text)


def _apply_agreement(text, fixes):
    for pattern, repl in AGREEMENT:
        text = _swap(pattern, repl, text, fixes)
    return text


def _apply_doubles(text, fixes):
    def replace(match):
        word = match.group(1)
        fixes.append(
            {
                "wrong": match.group(0),
                "right": word,
                "canonical": word.lower(),
            }
        )
        return word

    return DOUBLED.sub(replace, text)


def _apply_lessons(text, lessons, fixes):
    ordered = sorted(lessons.items(), key=lambda item: len(item[0]), reverse=True)
    for wrong, item in ordered:
        right = item["right"]
        pattern = _phrase_pattern(wrong)

        def replace(match, right=right, key=wrong):
            sample = match.group(0)
            fixed = _match_case(sample, right)
            if sample == fixed:
                return sample
            fixes.append({"wrong": sample, "right": fixed, "canonical": right, "lesson": key})
            return fixed

        text = pattern.sub(replace, text)
    return text


def _remember(fixes):
    if not fixes:
        return
    data = _load()
    lessons = data["lessons"]
    now = time.time()
    for fix in fixes:
        key = re.sub(r"\s+", " ", fix["wrong"].strip().lower())
        if fix.get("from") == "edit":
            right = re.sub(r"\s+", " ", fix["right"].strip())
        else:
            right = re.sub(r"\s+", " ", (fix.get("canonical") or fix["right"]).strip())
        if not key or not right or key == right.lower() or key == "i":
            continue
        if len(key) > MAX_SPAN or len(right) > MAX_SPAN:
            continue
        current = lessons.get(key)
        if current and current["from"] == "edit" and "lesson" not in fix:
            current["seen"] += 1
            current["at"] = now
            continue
        if current:
            current["seen"] += 1
            current["at"] = now
            if fix.get("from") == "edit":
                current["right"] = right
                current["from"] = "edit"
            continue
        lessons[key] = {
            "right": right,
            "seen": 1,
            "from": "edit" if fix.get("from") == "edit" else "text",
            "at": now,
        }
    if len(lessons) > MAX_LESSONS:
        ranked = sorted(lessons.items(), key=lambda item: (item[1]["seen"], item[1]["at"]))
        for key, _item in ranked[: len(lessons) - MAX_LESSONS]:
            lessons.pop(key, None)
    try:
        _save(data)
    except OSError:
        return


STRONG = {
    "the",
    "is",
    "are",
    "was",
    "were",
    "you",
    "i",
    "he",
    "she",
    "they",
    "we",
    "it",
    "don't",
    "dont",
    "it's",
    "its",
    "your",
    "you're",
    "youre",
    "this",
    "that",
}
ENGLISH_ERROR = re.compile(
    r"\b(?:dont|doesnt|didnt|youre|theyre|cant|wont|alot|couldnt|shouldnt|wouldnt|im)\b",
    re.I,
)


def looks_english(text):
    words = re.findall(r"[A-Za-z']+", text.lower())
    if any(word in STRONG for word in words):
        return True
    return bool(ENGLISH_ERROR.search(text or ""))


def study(text, remember=True, force=False):
    """Fix English grammar and, when asked, keep every mistake on this device."""

    if not isinstance(text, str) or not text.strip():
        return text or "", []
    if not re.search(r"[A-Za-z]", text):
        return text, []
    if not force and not looks_english(text):
        return text, []
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    with _lock:
        lessons = _load()["lessons"]
        fixes = []
        text = _apply_lessons(text, lessons, fixes)
        text = _apply_phrases(text, fixes)
        text = _apply_words(text, fixes)
        text = _apply_agreement(text, fixes)
        text = _apply_doubles(text, fixes)
        text = _apply_articles(text, fixes)
        if remember and fixes:
            _remember(fixes)
        public = [{"wrong": fix["wrong"], "right": fix["right"]} for fix in fixes]
        return text, _unique(public)


def _unique(fixes):
    seen = set()
    ordered = []
    for fix in fixes:
        key = (fix["wrong"].lower(), fix["right"])
        if key in seen:
            continue
        seen.add(key)
        ordered.append(fix)
    return ordered


def _attach_neighbor(before, after, prefix, suffix, wrong, right):
    if not _too_broad(wrong, right):
        return wrong, right
    lead = before[:prefix].rstrip()
    if lead:
        neighbor = lead.split()[-1]
        return f"{neighbor} {wrong}", f"{neighbor} {right}"
    trail = before[len(before) - suffix :].lstrip() if suffix else ""
    if trail:
        neighbor = trail.split()[0]
        return f"{wrong} {neighbor}", f"{right} {neighbor}"
    return wrong, right


def _too_broad(wrong, right):
    if " " in wrong or " " in right:
        return False
    folded_wrong = wrong.lower()
    folded_right = right.lower()
    grew = folded_right.startswith(folded_wrong) or folded_wrong.startswith(folded_right)
    return grew and abs(len(folded_wrong) - len(folded_right)) > 0 and len(folded_wrong) <= 4


def _related(wrong, right):
    folded_wrong = wrong.lower()
    folded_right = right.lower()
    if re.sub(r"[^a-z]", "", folded_wrong) == re.sub(r"[^a-z]", "", folded_right):
        return True
    if folded_wrong.startswith(folded_right) or folded_right.startswith(folded_wrong):
        if abs(len(folded_wrong) - len(folded_right)) <= 3:
            return True
    return difflib.SequenceMatcher(None, folded_wrong, folded_right).ratio() >= 0.72


def teach(before, after):
    """Learn one local edit. The lesson is the changed words, not the whole text."""

    if not isinstance(before, str) or not isinstance(after, str):
        return None
    before = before.replace("\u2019", "'").replace("\u2018", "'").strip()
    after = after.replace("\u2019", "'").replace("\u2018", "'").strip()
    if not before or not after or before == after:
        return None
    if len(before) > 12000 or len(after) > 12000:
        return None
    limit = min(len(before), len(after))
    prefix = 0
    while prefix < limit and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit - prefix and before[-1 - suffix] == after[-1 - suffix]:
        suffix += 1
    while prefix > 0 and before[prefix - 1] not in " \t\n":
        prefix -= 1
    while suffix > 0 and before[-suffix] not in " \t\n":
        suffix -= 1
    before_end = len(before) - suffix
    after_end = len(after) - suffix
    if before_end < prefix:
        before_end = prefix
    if after_end < prefix:
        after_end = prefix
    wrong = re.sub(r"\s+", " ", before[prefix:before_end].strip())
    right = re.sub(r"\s+", " ", after[prefix:after_end].strip())
    if not wrong or not right or wrong.lower() == right.lower():
        return None
    if len(wrong) > MAX_SPAN or len(right) > MAX_SPAN:
        return None
    if len(wrong.split()) > 8 or len(right.split()) > 8:
        return None
    if not re.search(r"[A-Za-z]", wrong) or not re.search(r"[A-Za-z]", right):
        return None
    if not _related(wrong, right):
        return None
    wrong, right = _attach_neighbor(before, after, prefix, suffix, wrong, right)
    if _too_broad(wrong, right):
        return None
    with _lock:
        _remember([{"wrong": wrong, "right": right, "from": "edit"}])
    return {"wrong": wrong, "right": right}


def snapshot(fixes):
    info = status()
    info["fixes"] = _unique(fixes or [])
    return info


def note_for(fixes):
    fixes = _unique(fixes or [])
    if not fixes:
        return ""
    if len(fixes) == 1:
        fix = fixes[0]
        return f"Brain kept “{fix['wrong']}” → “{fix['right']}” on this device."
    return f"Brain kept {len(fixes)} grammar fixes on this device."
