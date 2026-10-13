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

const MAX = 12000;
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

function requestKey(text) {
  return `${sourceCode()}|${targetCode()}|${text}`;
}

function setOutput(text, empty) {
  output.textContent = text;
  output.dataset.empty = empty ? "true" : "false";
  latestTranslation = empty ? "" : text;
}

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

if (speakBtn && !window.ToEnglishNative && window.isSecureContext && navigator.mediaDevices && window.MediaRecorder) {
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

const onThisPc = ["localhost", "127.0.0.1", "::1"].includes(location.hostname);
if (window.ToEnglishNative) {
  document.body.classList.add("installed");
  document.querySelector(".voice")?.remove();
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
  fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: sourceCode(), target: targetCode() }),
  }).catch(() => {});
}

async function loadSharedLanguages() {
  fillFromLanguages();
  const savedMode = recall("translator-mode");
  const savedTarget = recall("translator-target");
  const savedSource = recall("translator-source");
  if (savedSource) chooseLanguage(fromLang, savedSource);
  if ((savedMode === "from-english" || savedMode === "any") && savedTarget) {
    chooseLanguage(intoLang, savedTarget);
  }
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
