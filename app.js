const source = document.querySelector("#source");
const output = document.querySelector("#output");
const detected = document.querySelector("#detected");
const count = document.querySelector("#count");
const copyBtn = document.querySelector("#copy");
const clearBtn = document.querySelector("#clear");
const translateBtn = document.querySelector("#translate");
const statusEl = document.querySelector("#status");

const MAX = 12000;
let timer = 0;
let controller = null;
let lastSent = null;
let latestEnglish = "";

function setOutput(text, empty) {
  output.textContent = text;
  output.dataset.empty = empty ? "true" : "false";
  latestEnglish = empty ? "" : text;
}

function setStatus(message) {
  statusEl.textContent = message;
}

async function translate(manual) {
  const raw = source.value;
  const text = raw.trim();
  count.textContent = String(raw.length);
  count.style.color = raw.length > MAX ? "#9f2d16" : "";

  if (!text) {
    lastSent = "";
    detected.textContent = "Waiting";
    setOutput("English lands here.", true);
    setStatus("");
    return;
  }

  if (raw.length > MAX) {
    setStatus(`Keep it under ${MAX.toLocaleString()} characters.`);
    return;
  }

  if (!manual && text === lastSent) return;
  lastSent = text;

  if (!window.ToEnglishNative && location.protocol === "file:") {
    setStatus("Double-click start.bat so this page can translate.");
    return;
  }

  const request = new AbortController();
  controller = request;
  setStatus("Detecting language…");
  translateBtn.disabled = true;

  try {
    let data;
    if (window.ToEnglishNative) {
      data = await translateWithNative(text);
    } else {
      const response = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        signal: request.signal,
      });
      data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || "Translation failed.");
      }
    }
    if (request.signal.aborted || source.value.trim() !== text) return;
    detected.textContent = data.language || "Unknown";
    setOutput(data.english || "", !data.english);
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
  count.style.color = source.value.length > MAX ? "#9f2d16" : "";
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
  setOutput("English lands here.", true);
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
  if (!latestEnglish) return;
  await copyText(latestEnglish);
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
      document.querySelector("#phone").scrollIntoView({ behavior: "smooth" });
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

let nativeSeq = 0;
const nativeWaiters = new Map();

function translateWithNative(text) {
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
    window.ToEnglishNative.translate(id, text);
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

if (!window.ToEnglishNative) loadPhoneLink();
