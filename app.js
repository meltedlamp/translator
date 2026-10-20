const source = document.querySelector("#source");
const output = document.querySelector("#output");
const detected = document.querySelector("#detected");
const count = document.querySelector("#count");
const copyBtn = document.querySelector("#copy");
const clearBtn = document.querySelector("#clear");
const translateBtn = document.querySelector("#translate");
const statusEl = document.querySelector("#status");
const fromLang = document.querySelector("#from-lang");
const intoLang = document.querySelector("#into-lang");
const swapBtn = document.querySelector("#swap");
const brainEl = document.querySelector("#brain");

const MAX = 12000;
const GOOGLE = "https://translate.googleapis.com/translate_a/single";
const CHUNK = 3500;
const BRAIN_KEY = "translator-brain-lessons";
const onThisPc = ["localhost", "127.0.0.1", "::1"].includes(location.hostname);
const localDesk = Boolean(window.ToEnglishNative) || onThisPc || location.port === "8765";
const publicWeb = !localDesk;
let timer = 0;
let controller = null;
let lastSent = null;
let latestTranslation = "";

const sampleButtons = [...document.querySelectorAll("[data-sample]")];
const foreignSamples = sampleButtons.map((button) => ({
  label: button.textContent,
  text: button.dataset.sample,
}));
const englishSamples = [
  { label: "Station", text: "Where is the nearest train station?" },
  { label: "Cafe", text: "I would like a coffee and a slice of cake, please." },
  { label: "Cinema", text: "We're going to the cinema tonight. Don't be late." },
  { label: "Meeting", text: "Let's meet in front of the station tomorrow afternoon." },
  { label: "Friday", text: "Please send me this file before Friday." },
];

function fillFromLanguages() {
  const detect = fromLang.querySelector('option[value="auto"]');
  fromLang.replaceChildren(detect);
  intoLang.querySelectorAll("optgroup").forEach((group) => {
    fromLang.appendChild(group.cloneNode(true));
  });
  fromLang.value = "auto";
}

function sourceCode() {
  return fromLang.value || "auto";
}

function targetCode() {
  return intoLang.value || "en";
}

function targetName() {
  const option = intoLang.selectedOptions[0];
  return option ? option.textContent : "English";
}

function emptyLine() {
  return `${targetName()} lands here.`;
}

function languageName(code) {
  if (!code) return "Unknown";
  const options = [...fromLang.options, ...intoLang.options];
  const exact = options.find((option) => option.value === code);
  if (exact && exact.value !== "auto") return exact.textContent;
  const base = code.split("-")[0];
  const match = options.find((option) => option.value === base);
  return match && match.value !== "auto" ? match.textContent : code;
}

function sameLanguage(detected, target) {
  if (!detected || !target) return false;
  if (detected === target) return true;
  return !target.includes("-") && detected.split("-")[0] === target;
}

function splitText(text, limit = CHUNK) {
  if (text.length <= limit) return [text];
  const parts = [];
  let start = 0;
  while (start < text.length) {
    let end = Math.min(start + limit, text.length);
    if (end < text.length) {
      const breakAt = text.lastIndexOf("\n", end - 1);
      if (breakAt > start + Math.floor(limit / 4)) end = breakAt + 1;
    }
    parts.push(text.slice(start, end));
    start = end;
  }
  return parts;
}

async function translateChunk(text, sourceLang, target, signal) {
  const body = new URLSearchParams({
    client: "gtx",
    sl: sourceLang || "auto",
    tl: target || "en",
    dt: "t",
    dj: "1",
    q: text,
  });
  const response = await fetch(GOOGLE, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    signal,
  });
  if (!response.ok) {
    throw new Error("Could not reach the translator. Check your connection and try again.");
  }
  const data = await response.json();
  const translation = (data.sentences || [])
    .map((sentence) => sentence.trans || "")
    .join("");
  return {
    translation,
    code: data.src || "",
    confidence: typeof data.confidence === "number" ? data.confidence : null,
    weight: text.length,
  };
}

async function translateInBrowser(text, sourceLang, target, signal) {
  const pieces = [];
  for (const part of splitText(text)) {
    pieces.push(await translateChunk(part, sourceLang, target, signal));
  }
  const best = pieces.reduce((left, right) => (right.weight > left.weight ? right : left));
  const code = best.code;
  const confidence = best.confidence;
  const toName = targetName();
  let note = "";
  if (sameLanguage(code, target)) note = `This already looks like ${toName}.`;
  else if (sourceLang === "en" && code && !sameLanguage(code, "en")) {
    note = `That was read as ${languageName(code)}, not English.`;
  } else if (sourceLang === "auto" && confidence != null && confidence < 0.35) {
    note = "Low confidence. A very short line can be hard to place.";
  }
  return {
    translation: pieces.map((piece) => piece.translation).join("").trim(),
    language: languageName(code),
    code,
    target: toName,
    targetCode: target,
    confidence,
    note,
    brain: publicBrainStatus(),
  };
}

function publicBrain() {
  try {
    const data = JSON.parse(localStorage.getItem(BRAIN_KEY) || "{}");
    return data && typeof data === "object" && !Array.isArray(data) ? data : {};
  } catch {
    return {};
  }
}

function publicBrainStatus() {
  return { lessons: Object.keys(publicBrain()).length };
}

function storePublicBrain(lessons) {
  try {
    localStorage.setItem(BRAIN_KEY, JSON.stringify(lessons));
  } catch {
    /* The page still translates if storage is blocked. */
  }
  return { lessons: Object.keys(lessons).length };
}

function publicTeach(before, after) {
  if (!before || !after || before === after) return { ...publicBrainStatus(), lesson: null };
  const limit = Math.min(before.length, after.length);
  let prefix = 0;
  while (prefix < limit && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0;
  while (suffix < limit - prefix && before.at(-1 - suffix) === after.at(-1 - suffix)) suffix += 1;
  while (prefix > 0 && !" \t\n".includes(before[prefix - 1])) prefix -= 1;
  while (suffix > 0 && !" \t\n".includes(before.at(-suffix))) suffix -= 1;
  const wrong = before.slice(prefix, before.length - suffix).trim().replace(/\s+/g, " ");
  const right = after.slice(prefix, after.length - suffix).trim().replace(/\s+/g, " ");
  if (!wrong || !right || wrong.toLowerCase() === right.toLowerCase()) {
    return { ...publicBrainStatus(), lesson: null };
  }
  if (wrong.length > 80 || right.length > 80) return { ...publicBrainStatus(), lesson: null };
  const lessons = publicBrain();
  lessons[wrong.toLowerCase()] = { right, from: "edit" };
  const status = storePublicBrain(lessons);
  status.lesson = { wrong, right };
  return status;
}

function requestKey(text) {
  return `${sourceCode()}|${targetCode()}|${text}`;
}

let armedTranslation = "";

function setOutput(text, empty) {
  output.textContent = text;
  output.contentEditable = empty ? "false" : "true";
  output.dataset.empty = empty ? "true" : "false";
  latestTranslation = empty ? "" : text;
  armedTranslation = latestTranslation;
}

function brainPlace() {
  if (document.body.classList.contains("installed")) return "on this phone";
  if (document.body.classList.contains("public-web")) return "in this browser";
  if (document.body.classList.contains("on-phone")) return "on the computer you downloaded";
  return "in this folder";
}

function showBrain(data) {
  if (!brainEl) return;
  const count = data && Number.isFinite(Number(data.lessons)) ? Number(data.lessons) : 0;
  const lessons = count === 1 ? "1 lesson" : `${count} lessons`;
  brainEl.textContent = `Brain stays ${brainPlace()} · ${lessons}. It keeps learning from grammar in the text.`;
}

function readNativeBrain(method, args) {
  const native = window.ToEnglishNative;
  if (!native || typeof native[method] !== "function") return null;
  try {
    return JSON.parse(native[method](...args) || "{}");
  } catch {
    return null;
  }
}

async function loadBrain() {
  const native = readNativeBrain("brainStatus", []);
  if (native) {
    showBrain(native);
    return;
  }
  if (publicWeb) {
    showBrain(publicBrainStatus());
    return;
  }
  try {
    const response = await fetch("/api/brain");
    if (response.ok) showBrain(await response.json());
  } catch {
    /* The page still translates if the brain file cannot be read. */
  }
}

async function teachBrain(before, after) {
  const native = readNativeBrain("teach", [before, after]);
  if (native) return native;
  if (publicWeb) return publicTeach(before, after);
  const response = await fetch("/api/brain", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ before, after }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "The brain could not keep that edit.");
  return data;
}

function outputText() {
  return (output.innerText || "").replace(/\u00a0/g, " ").replace(/\r\n/g, "\n");
}

output.addEventListener("input", () => {
  if (output.dataset.empty === "true") return;
  latestTranslation = outputText();
});

output.addEventListener("blur", async () => {
  if (output.dataset.empty === "true") return;
  const now = outputText().trim();
  const before = armedTranslation.trim();
  if (!before || now === before) return;
  output.textContent = outputText().trim();
  armedTranslation = output.textContent;
  latestTranslation = armedTranslation;
  try {
    const data = await teachBrain(before, now);
    showBrain(data);
    if (data.lesson && data.lesson.wrong) {
      setStatus(`Brain learned “${data.lesson.wrong}” → “${data.lesson.right}” and kept it on this device.`);
    }
  } catch (error) {
    setStatus(error.message || "The brain could not keep that edit.");
  }
});

function showSamples() {
  const list = sourceCode() === "en" ? englishSamples : foreignSamples;
  sampleButtons.forEach((button, index) => {
    const sample = list[index];
    button.hidden = !sample;
    if (!sample) return;
    button.textContent = sample.label;
    button.dataset.sample = sample.text;
  });
}

function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* The page still works if storage is blocked. */
  }
}

function recall(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function setStatus(message) {
  statusEl.textContent = message;
}

function stampText(data) {
  const from = data.language || "Unknown";
  const to = data.target || targetName();
  return `${from} → ${to}`;
}

async function translate(manual) {
  const raw = source.value;
  const text = raw.trim();
  count.textContent = String(raw.length);
  count.style.color = raw.length > MAX ? "#ff8f78" : "";

  if (!text) {
    lastSent = "";
    detected.textContent = "Waiting";
    setOutput(emptyLine(), true);
    setStatus("");
    return;
  }

  if (raw.length > MAX) {
    setStatus(`Keep it under ${MAX.toLocaleString()} characters.`);
    return;
  }

  const sent = requestKey(text);
  if (!manual && sent === lastSent) return;
  lastSent = sent;

  if (!window.ToEnglishNative && location.protocol === "file:") {
    setStatus("Double-click start.bat so this page can translate.");
    return;
  }

  const request = new AbortController();
  controller = request;
  const from = sourceCode();
  const into = targetCode();
  setStatus("Translating…");
  translateBtn.disabled = true;

  try {
    let data;
    if (window.ToEnglishNative) {
      data = await translateWithNative(text, from, into);
    } else if (publicWeb) {
      data = await translateInBrowser(text, from, into, request.signal);
    } else {
      const response = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source: from, target: into }),
        signal: request.signal,
      });
      data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || "Translation failed.");
      }
    }
    if (request.signal.aborted || requestKey(source.value.trim()) !== sent) return;
    if (data.code) fromLang.dataset.detected = data.code;
    detected.textContent = stampText(data);
    const translation = data.translation || data.english || "";
    setOutput(translation, !translation);
    setStatus(data.note || "");
    if (data.brain) showBrain(data.brain);
  } catch (error) {
    if (error.name === "AbortError") return;
    setStatus(error.message || "Something went wrong.");
  } finally {
    if (controller === request) translateBtn.disabled = false;
  }
}

source.addEventListener("input", () => {
  count.textContent = String(source.value.length);
  count.style.color = source.value.length > MAX ? "#ff8f78" : "";
  window.clearTimeout(timer);
  if (controller) controller.abort();
  timer = window.setTimeout(() => translate(false), 450);
});

translateBtn.addEventListener("click", () => translate(true));

source.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    translate(true);
  }
});

clearBtn.addEventListener("click", () => {
  source.value = "";
  lastSent = "";
  if (controller) controller.abort();
  detected.textContent = "Waiting";
  setOutput(emptyLine(), true);
  setStatus("");
  count.textContent = "0";
  source.focus();
});

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, area.value.length);
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch {
      copied = false;
    }
    area.remove();
    return copied;
  }
}

copyBtn.addEventListener("click", async () => {
  if (!latestTranslation) return;
  await copyText(latestTranslation);
  const previous = copyBtn.textContent;
  copyBtn.textContent = "Copied";
  window.setTimeout(() => {
    copyBtn.textContent = previous;
  }, 1200);
});

document.querySelectorAll("[data-sample]").forEach((button) => {
  button.addEventListener("click", () => {
    source.value = button.dataset.sample;
    source.focus();
    translate(true);
  });
});

const speakBtn = document.querySelector("#speak");
let recorder = null;
let micStream = null;
let micChunks = [];

function insertAtCursor(text) {
  const start = source.selectionStart ?? source.value.length;
  const end = source.selectionEnd ?? start;
  const before = source.value.slice(0, start);
  const after = source.value.slice(end);
  const pad = before && !/\s$/.test(before) && text && !/^\s/.test(text) ? " " : "";
  const next = before + pad + text + after;
  source.value = next;
  const caret = (before + pad + text).length;
  source.selectionStart = source.selectionEnd = caret;
  source.dispatchEvent(new Event("input"));
  source.focus();
}

function stopSpeaking() {
  if (recorder && recorder.state === "recording") recorder.stop();
}

const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;

if (speakBtn && publicWeb && Speech) {
  let recognition = null;
  speakBtn.addEventListener("click", () => {
    if (recognition) {
      recognition.stop();
      return;
    }
    try {
      recognition = new Speech();
    } catch {
      setStatus("Couldn't turn that speech into text.");
      return;
    }
    recognition.lang = sourceCode() === "auto" ? navigator.language || "en-US" : sourceCode();
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const spoken = event.results[0]?.[0]?.transcript || "";
      if (spoken) insertAtCursor(spoken);
      setStatus("");
    };
    recognition.onerror = () => {
      setStatus("Couldn't turn that speech into text.");
    };
    recognition.onend = () => {
      recognition = null;
      speakBtn.textContent = "Speak";
      speakBtn.classList.remove("hearing");
      speakBtn.setAttribute("aria-pressed", "false");
    };
    recognition.start();
    speakBtn.textContent = "Stop";
    speakBtn.classList.add("hearing");
    speakBtn.setAttribute("aria-pressed", "true");
    setStatus("Listening… tap Stop when you're done.");
  });
} else if (speakBtn && !window.ToEnglishNative && window.isSecureContext && navigator.mediaDevices && window.MediaRecorder) {
  speakBtn.addEventListener("click", async () => {
    if (recorder && recorder.state === "recording") {
      stopSpeaking();
      return;
    }
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setStatus("Allow the microphone, or hold the right Ctrl key in any app.");
      return;
    }
    micChunks = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    recorder = mime ? new MediaRecorder(micStream, { mimeType: mime }) : new MediaRecorder(micStream);
    recorder.ondataavailable = (event) => {
      if (event.data.size) micChunks.push(event.data);
    };
    recorder.onstop = async () => {
      micStream.getTracks().forEach((track) => track.stop());
      speakBtn.textContent = "Speak";
      speakBtn.classList.remove("hearing");
      speakBtn.setAttribute("aria-pressed", "false");
      const blob = new Blob(micChunks, { type: recorder.mimeType || "audio/webm" });
      if (blob.size < 800) {
        setStatus("Didn't catch that.");
        return;
      }
      setStatus("Writing…");
      speakBtn.disabled = true;
      try {
        const response = await fetch("/api/dictate", {
          method: "POST",
          headers: { "Content-Type": blob.type || "application/octet-stream" },
          body: blob,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Couldn't turn that speech into text.");
        if (data.text) insertAtCursor(data.text);
        setStatus("");
      } catch (error) {
        setStatus(error.message || "Couldn't turn that speech into text.");
      } finally {
        speakBtn.disabled = false;
      }
    };
    recorder.start();
    speakBtn.textContent = "Stop";
    speakBtn.classList.add("hearing");
    speakBtn.setAttribute("aria-pressed", "true");
    setStatus("Listening… tap Stop when you're done.");
  });
} else if (speakBtn) {
  speakBtn.hidden = true;
}

const sideToggle = document.querySelector("#side-toggle");

function paintSide(on) {
  if (!sideToggle) return;
  const enabled = !!on;
  sideToggle.textContent = enabled ? "Side tab is on" : "Turn on the side tab";
  sideToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
}

window.onSideStatus = paintSide;

if (sideToggle && window.ToEnglishNative) {
  sideToggle.addEventListener("click", () => window.ToEnglishNative.openSideSetting());
}

if (window.ToEnglishNative) {
  document.body.classList.add("installed");
  document.querySelector(".voice")?.remove();
} else if (publicWeb) {
  document.body.classList.add("public-web");
} else if (!onThisPc) {
  document.body.classList.add("on-phone");
  source.blur();
}

const phoneUrl = document.querySelector("#phone-url");
const phoneQr = document.querySelector("#phone-qr");
const copyPhone = document.querySelector("#copy-phone");

async function loadPhoneLink() {
  if (!onThisPc) return;
  try {
    const response = await fetch("/api/phone");
    const data = await response.json();
    if (!data.url) {
      phoneUrl.textContent = "Connect this laptop to Wi-Fi, then refresh.";
      return;
    }
    phoneUrl.textContent = data.url;
    phoneUrl.href = data.url;
    phoneQr.src = "/phone-qr.png";
    phoneQr.alt = "QR code that opens To English on your phone";
    if (location.hash === "#phone") {
      const phone = document.querySelector("#phone");
      if (phone) phone.open = true;
      phone?.scrollIntoView({ behavior: "smooth" });
    }
  } catch {
    phoneUrl.textContent = "The phone address will show once the translator is running.";
  }
}

copyPhone.addEventListener("click", async () => {
  const address = phoneUrl.href;
  if (!address || address.endsWith("#phone")) return;
  await copyText(address);
  const previous = copyPhone.textContent;
  copyPhone.textContent = "Copied";
  window.setTimeout(() => {
    copyPhone.textContent = previous;
  }, 1200);
});

if (!window.ToEnglishNative) loadPhoneLink();

let nativeSeq = 0;
const nativeWaiters = new Map();

function translateWithNative(text, sourceCode, into) {
  return new Promise((resolve, reject) => {
    const id = String(++nativeSeq);
    const timer = window.setTimeout(() => {
      if (!nativeWaiters.has(id)) return;
      nativeWaiters.delete(id);
      reject(new Error("Could not reach the translator. Check your connection and try again."));
    }, 30000);
    nativeWaiters.set(id, (payload) => {
      window.clearTimeout(timer);
      let data;
      try {
        data = JSON.parse(payload);
      } catch {
        reject(new Error("Translation failed."));
        return;
      }
      if (data.error) {
        reject(new Error(data.error));
        return;
      }
      resolve(data);
    });
    try {
      window.ToEnglishNative.translate(id, text, sourceCode, into);
    } catch {
      window.ToEnglishNative.translate(id, text);
    }
  });
}

window.onToEnglishResult = (id, payload) => {
  const done = nativeWaiters.get(String(id));
  if (!done) return;
  nativeWaiters.delete(String(id));
  done(payload);
};

window.receiveSharedText = (text) => {
  if (!text) return;
  source.value = text;
  source.dispatchEvent(new Event("input"));
  translate(true);
};

function chooseLanguage(select, value) {
  if (!value) return false;
  const match = [...select.options].some((option) => option.value === value);
  if (match) select.value = value;
  return match;
}

function onLanguageChange() {
  remember("translator-source", sourceCode());
  remember("translator-target", targetCode());
  showSamples();
  saveSharedLanguages();
  if (!source.value.trim()) {
    setOutput(emptyLine(), true);
    detected.textContent = "Waiting";
    return;
  }
  if (controller) controller.abort();
  lastSent = null;
  translate(false);
}

function saveSharedLanguages() {
  if (window.ToEnglishNative && typeof window.ToEnglishNative.saveLanguages === "function") {
    window.ToEnglishNative.saveLanguages(sourceCode(), targetCode());
    return;
  }
  if (!localDesk) return;
  fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: sourceCode(), target: targetCode() }),
  }).catch(() => {});
}

async function loadSharedLanguages() {
  fillFromLanguages();
  const savedTarget = recall("translator-target");
  const savedSource = recall("translator-source");
  if (savedSource) chooseLanguage(fromLang, savedSource);
  if (savedTarget) chooseLanguage(intoLang, savedTarget);
  const nativeLangs = readNativeBrain("languageSettings", []);
  if (nativeLangs && nativeLangs.chosen) {
    chooseLanguage(fromLang, nativeLangs.source);
    chooseLanguage(intoLang, nativeLangs.target);
  }
  if (localDesk && !window.ToEnglishNative) {
    try {
      const response = await fetch("/api/settings");
      if (response.ok) {
        const data = await response.json();
        if (data.chosen) {
          chooseLanguage(fromLang, data.source);
          chooseLanguage(intoLang, data.target);
        }
      }
    } catch {
      /* The languages chosen on this device still apply. */
    }
  }
  showSamples();
  if (!source.value.trim()) setOutput(emptyLine(), true);
}

fromLang.addEventListener("change", onLanguageChange);
intoLang.addEventListener("change", onLanguageChange);
swapBtn.addEventListener("click", () => {
  let from = sourceCode();
  const into = targetCode();
  if (from === "auto") {
    from = fromLang.dataset.detected || "";
    if (!from || from === into) return;
  }
  if (!chooseLanguage(intoLang, from)) return;
  fromLang.value = into;
  onLanguageChange();
});

loadSharedLanguages();
loadBrain();

const holdMenu = document.querySelector("#hold-menu");
const holdTranslate = document.querySelector("#hold-translate");
let heldText = "";
let holdTimer = 0;

function phoneSurface() {
  return document.body.classList.contains("on-phone")
    || document.body.classList.contains("installed")
    || window.matchMedia("(pointer: coarse)").matches
    || window.matchMedia("(hover: none)").matches;
}

function selectedText() {
  const selection = window.getSelection?.();
  const anchor = selection?.anchorNode;
  const anchorEl = anchor?.nodeType === 1 ? anchor : anchor?.parentElement;
  if (anchorEl?.closest?.("#hold-menu")) return "";
  if (document.activeElement === source) {
    const start = source.selectionStart ?? 0;
    const end = source.selectionEnd ?? start;
    if (end > start) return source.value.slice(start, end).trim();
  }
  return selection?.toString().trim() || "";
}

function refreshHold() {
  if (!holdMenu || !phoneSurface()) return;
  const text = selectedText();
  if (!text) {
    holdMenu.hidden = true;
    return;
  }
  heldText = text;
  holdMenu.hidden = false;
}

function scheduleHold() {
  window.clearTimeout(holdTimer);
  holdTimer = window.setTimeout(refreshHold, 80);
}

document.addEventListener("selectionchange", scheduleHold);
source.addEventListener("touchend", scheduleHold);
source.addEventListener("mouseup", scheduleHold);
document.addEventListener("contextmenu", () => {
  if (phoneSurface()) scheduleHold();
});

if (holdTranslate) {
  holdTranslate.addEventListener("pointerdown", () => {
    const text = selectedText();
    if (text) heldText = text;
  });
  holdTranslate.addEventListener("mousedown", (event) => event.preventDefault());
  holdTranslate.addEventListener("touchstart", (event) => event.preventDefault(), { passive: false });
  holdTranslate.addEventListener("click", async () => {
    const text = (selectedText() || heldText).trim();
    holdMenu.hidden = true;
    if (!text) return;
    if (text.length > MAX) {
      setStatus(`Keep it under ${MAX.toLocaleString()} characters.`);
      return;
    }
    source.value = text;
    count.textContent = String(text.length);
    await translate(true);
    output.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}
