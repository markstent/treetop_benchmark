"use strict";

const stage = document.getElementById("stage");
const template = document.getElementById("panel-template");
const emptyState = document.getElementById("empty-state");
const modeSingleBtn = document.getElementById("mode-single");
const modeCompareBtn = document.getElementById("mode-compare");

// Prompt slide-over
const promptBtn = document.getElementById("show-prompt");
const promptOverlay = document.getElementById("prompt-overlay");
const promptBody = document.getElementById("prompt-body");

let models = [];          // [{ file, label }]
let mode = "single";      // "single" | "compare"
let selections = [];      // chosen file per panel index, persisted across mode switches
let promptLoaded = false;

function modelUrl(file) {
  return "/models/" + encodeURIComponent(file);
}

// Pick sensible defaults: first model for panel 0, a different one for panel 1.
function defaultSelection(index) {
  if (models.length === 0) return "";
  if (index === 1 && models.length > 1) return models[1].file;
  return models[0].file;
}

function selectionFor(index) {
  const current = selections[index];
  if (current && models.some((m) => m.file === current)) return current;
  return defaultSelection(index);
}

function buildPanel(index) {
  const node = template.content.firstElementChild.cloneNode(true);
  const select = node.querySelector(".panel-select");
  const frame = node.querySelector(".panel-frame");
  const empty = node.querySelector(".panel-empty");
  const openLink = node.querySelector(".js-open");
  const reloadBtn = node.querySelector(".js-reload");

  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m.file;
    opt.textContent = m.label;
    select.appendChild(opt);
  }

  const load = (file) => {
    selections[index] = file;
    if (file) {
      frame.src = modelUrl(file);
      openLink.href = modelUrl(file);
      frame.hidden = false;
      empty.hidden = true;
    } else {
      frame.removeAttribute("src");
      frame.hidden = true;
      empty.hidden = false;
    }
  };

  const chosen = selectionFor(index);
  select.value = chosen;
  load(chosen);

  select.addEventListener("change", () => load(select.value));
  reloadBtn.addEventListener("click", () => {
    if (!frame.src) return;
    // Re-assign to force a clean reload of the model's scene.
    const src = frame.src;
    frame.src = "about:blank";
    requestAnimationFrame(() => { frame.src = src; });
  });

  return node;
}

function render() {
  if (models.length === 0) {
    stage.hidden = true;
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;
  stage.hidden = false;

  const count = mode === "compare" ? 2 : 1;
  stage.className = "stage " + mode;
  stage.replaceChildren();
  for (let i = 0; i < count; i++) {
    stage.appendChild(buildPanel(i));
  }
}

function setMode(next) {
  if (next === mode) return;
  mode = next;
  const compare = mode === "compare";
  modeCompareBtn.classList.toggle("is-active", compare);
  modeSingleBtn.classList.toggle("is-active", !compare);
  modeCompareBtn.setAttribute("aria-selected", String(compare));
  modeSingleBtn.setAttribute("aria-selected", String(!compare));
  render();
}

// ---- Prompt slide-over ----
async function openPrompt() {
  promptOverlay.hidden = false;
  if (!promptLoaded) {
    try {
      const res = await fetch("/api/prompt");
      promptBody.textContent = res.ok
        ? await res.text()
        : "Could not load prompt.txt";
      promptLoaded = res.ok;
    } catch (err) {
      promptBody.textContent = "Could not load prompt.txt";
    }
  }
}

function closePrompt() {
  promptOverlay.hidden = true;
}

// ---- Wiring ----
modeSingleBtn.addEventListener("click", () => setMode("single"));
modeCompareBtn.addEventListener("click", () => setMode("compare"));
promptBtn.addEventListener("click", openPrompt);
promptOverlay.addEventListener("click", (e) => {
  if (e.target.hasAttribute("data-close")) closePrompt();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !promptOverlay.hidden) closePrompt();
});

async function init() {
  try {
    const res = await fetch("/api/models");
    const data = await res.json();
    models = Array.isArray(data.models) ? data.models : [];
  } catch (err) {
    models = [];
  }
  selections = [defaultSelection(0), defaultSelection(1)];
  render();
}

init();
