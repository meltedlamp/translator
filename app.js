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

  if (location.protocol === "file:") {
    setStatus("Double-click start.bat so this page can translate.");
    return;
  }

  const request = new AbortController();
  controller = request;
  setStatus("Detecting language…");
  translateBtn.disabled = true;

  try {
    const response = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: request.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Translation failed.");
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

const onThisPc = ["localhost", "127.0.0.1", "::1"].includes(location.hostname);
if (!onThisPc) {
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

loadPhoneLink();
