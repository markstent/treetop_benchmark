"use strict";

// Everything here is static: the page fetches models.json, prompt.txt and
// docs/BENCHMARK.md with relative URLs, so it works from GitHub Pages
// (including a project sub-path) as well as from server.py locally.

const stage = document.getElementById("stage");
const template = document.getElementById("panel-template");
const emptyState = document.getElementById("empty-state");
const modeSingleBtn = document.getElementById("mode-single");
const modeCompareBtn = document.getElementById("mode-compare");

// Slide-overs
const promptBtn = document.getElementById("show-prompt");
const promptOverlay = document.getElementById("prompt-overlay");
const promptBody = document.getElementById("prompt-body");
const aboutBtn = document.getElementById("show-about");
const aboutOverlay = document.getElementById("about-overlay");
const aboutBody = document.getElementById("about-body");

const MANIFEST_URL = "models.json";
const PROMPT_URL = "prompt.txt";
const ABOUT_URL = "docs/BENCHMARK.md";

let models = [];          // manifest entries: { file, label, model, provider, effort, date, note }
let mode = "single";      // "single" | "compare"
let selections = [];      // chosen file per panel index, persisted across mode switches
let promptLoaded = false;
let aboutLoaded = false;

function modelUrl(file) {
  return "models/" + encodeURIComponent(file);
}

function modelByFile(file) {
  return models.find((m) => m.file === file) || null;
}

// Pick sensible defaults: first model for panel 0, a different one for panel 1.
function defaultSelection(index) {
  if (models.length === 0) return "";
  if (index === 1 && models.length > 1) return models[1].file;
  return models[0].file;
}

function selectionFor(index) {
  const current = selections[index];
  if (current && modelByFile(current)) return current;
  return defaultSelection(index);
}

// ---- Provenance popover ----
const INFO_FIELDS = [
  ["model", "Model"],
  ["provider", "Provider"],
  ["effort", "Effort"],
  ["date", "Run"],
];

function fillInfo(panel, entry) {
  const grid = panel.querySelector(".info-grid");
  const note = panel.querySelector(".info-note");
  grid.replaceChildren();
  if (!entry) { note.textContent = ""; return; }
  for (const [key, title] of INFO_FIELDS) {
    const value = entry[key];
    if (!value) continue;
    const dt = document.createElement("dt");
    dt.textContent = title;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    grid.append(dt, dd);
  }
  note.textContent = entry.note || "";
}

function buildPanel(index) {
  const node = template.content.firstElementChild.cloneNode(true);
  const select = node.querySelector(".panel-select");
  const frame = node.querySelector(".panel-frame");
  const empty = node.querySelector(".panel-empty");
  const openLink = node.querySelector(".js-open");
  const reloadBtn = node.querySelector(".js-reload");
  const infoBtn = node.querySelector(".js-info");
  const info = node.querySelector(".panel-info");

  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m.file;
    opt.textContent = m.label;
    select.appendChild(opt);
  }

  const load = (file) => {
    selections[index] = file;
    fillInfo(node, modelByFile(file));
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
  infoBtn.addEventListener("click", () => {
    const open = info.hidden;
    info.hidden = !open;
    infoBtn.setAttribute("aria-expanded", String(open));
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
  if (promptLoaded) return;
  try {
    const res = await fetch(PROMPT_URL);
    promptBody.textContent = res.ok ? await res.text() : "Could not load the prompt.";
    promptLoaded = res.ok;
  } catch (err) {
    promptBody.textContent = "Could not load the prompt.";
  }
}

function closePrompt() {
  promptOverlay.hidden = true;
}

// ---- About slide-over (docs/BENCHMARK.md rendered from Markdown) ----
async function openAbout() {
  aboutOverlay.hidden = false;
  if (aboutLoaded) return;
  try {
    const res = await fetch(ABOUT_URL);
    if (!res.ok) throw new Error(String(res.status));
    aboutBody.innerHTML = renderMarkdown(await res.text());
    aboutLoaded = true;
  } catch (err) {
    aboutBody.innerHTML = '<p class="doc-muted">Could not load the benchmark write-up.</p>';
  }
}

function closeAbout() {
  aboutOverlay.hidden = true;
}

// Minimal Markdown renderer covering what BENCHMARK.md uses: headings,
// paragraphs, bullet and numbered lists, pipe tables, fenced code, and
// inline code, bold, and links. Everything is HTML-escaped first.
function renderMarkdown(src) {
  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const slug = (t) => t.toLowerCase().replace(/[^a-z0-9 -]/g, "").trim().replace(/\s+/g, "-");

  const inline = (t) => {
    const codes = [];
    t = esc(t).replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return "\u0000" + (codes.length - 1) + "\u0000"; });
    t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, href) => {
      const external = /^https?:\/\//.test(href);
      const attrs = external ? ' target="_blank" rel="noopener"' : "";
      return `<a href="${href}"${attrs}>${label}</a>`;
    });
    return t.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[i]}</code>`);
  };

  const lines = src.split(/\r?\n/);
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (/^\s*$/.test(line)) { i++; continue; }

    if (line.startsWith("```")) {
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`);
      continue;
    }

    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      out.push(`<h${level} id="${slug(h[2])}">${inline(h[2])}</h${level}>`);
      i++;
      continue;
    }

    if (line.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
      const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const [head, , ...body] = rows;
      const th = cells(head).map((c) => `<th>${inline(c)}</th>`).join("");
      const tr = body.map((r) => `<tr>${cells(r).map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("");
      out.push(`<div class="doc-table"><table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`);
      continue;
    }

    const li = /^(\s*)(-|\d+\.)\s+(.*)$/.exec(line);
    if (li) {
      const tag = li[2] === "-" ? "ul" : "ol";
      const items = [];
      while (i < lines.length) {
        const m = /^(\s*)(-|\d+\.)\s+(.*)$/.exec(lines[i]);
        if (!m || (m[2] === "-") !== (tag === "ul")) break;
        items.push(`<li>${inline(m[3])}</li>`);
        i++;
      }
      out.push(`<${tag}>${items.join("")}</${tag}>`);
      continue;
    }

    // Paragraph: consecutive plain lines (the doc keeps one sentence per line).
    const buf = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|```|\||\s*(-|\d+\.)\s)/.test(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${inline(buf.join(" "))}</p>`);
  }
  return out.join("\n");
}

// ---- Wiring ----
modeSingleBtn.addEventListener("click", () => setMode("single"));
modeCompareBtn.addEventListener("click", () => setMode("compare"));
promptBtn.addEventListener("click", openPrompt);
aboutBtn.addEventListener("click", openAbout);
promptOverlay.addEventListener("click", (e) => {
  if (e.target.hasAttribute("data-close")) closePrompt();
});
aboutOverlay.addEventListener("click", (e) => {
  if (e.target.hasAttribute("data-close")) closeAbout();
});
// Links inside the About document: in-page anchors scroll the panel itself,
// and a link to the brief opens the Prompt panel instead of navigating away.
aboutBody.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a) return;
  const href = a.getAttribute("href");
  if (href.startsWith("#")) {
    const target = aboutBody.querySelector(href);
    if (target) { e.preventDefault(); target.scrollIntoView({ block: "start" }); }
  } else if (href === PROMPT_URL) {
    e.preventDefault();
    closeAbout();
    openPrompt();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!aboutOverlay.hidden) closeAbout();
  else if (!promptOverlay.hidden) closePrompt();
});

async function init() {
  try {
    const res = await fetch(MANIFEST_URL, { cache: "no-cache" });
    const data = await res.json();
    models = Array.isArray(data.models) ? data.models.filter((m) => m && m.file) : [];
    for (const m of models) if (!m.label) m.label = m.file.replace(/\.html$/i, "").replace(/_/g, " ");
    models.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: "base", numeric: true }));
  } catch (err) {
    models = [];
  }
  selections = [defaultSelection(0), defaultSelection(1)];
  render();
}

init();
