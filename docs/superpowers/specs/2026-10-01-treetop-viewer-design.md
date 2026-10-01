---
title: Treetop Benchmark Viewer - Design
date: 2026-10-01
status: approved-pending-review
---

# Treetop Benchmark Viewer - Design

## Purpose

A small local web app to browse and visually compare the model-generated 3D treetop-village HTML files produced for the Treetop benchmark (`prompt.txt`).
Each model run is a single, self-contained HTML file in `models/`.
The app lets the user load any one model full-screen, or put two models side by side, to judge quality by eye.

This is a **pure viewer**: no scoring, no ratings, no persistence.
Judgment happens in the user's head, not in the tool.

## Non-goals

- No scoring, rating, notes, or any saved state.
- No backend database.
- No build step, bundler, or npm/pip dependencies.
- No editing or generation of model files - the app only displays what is already in `models/`.

## Architecture

### Server (`server.py`)

- Zero third-party dependencies: Python 3 standard library only (`http.server`).
- Run with `python3 server.py`; it prints a `http://localhost:<port>` URL.
- Responsibilities:
  1. Serve the frontend static files from `web/`.
  2. Serve raw model HTML files from `models/` (so they can load inside iframes).
  3. Expose `GET /api/models` returning JSON describing the current contents of `models/`, read live on each request.
- Because the model list is read live, **adding a new `.html` to `models/` and refreshing the page is the only step** needed to make a new model appear.

#### `GET /api/models` response shape

```json
{
  "models": [
    { "file": "Treetop_village_GPT6_Astra_High.html", "label": "GPT6 Astra High" }
  ]
}
```

- Only files ending in `.html` are listed.
- Results sorted alphabetically by label.
- `label` is derived from the filename: strip a leading `Treetop_village_` prefix (if present) and the `.html` extension, then replace underscores with spaces. The raw `file` is what the iframe loads.

#### Routing

| Path                 | Behavior                                             |
|----------------------|------------------------------------------------------|
| `/`                  | serve `web/index.html`                               |
| `/style.css`, `/app.js` | serve the corresponding file from `web/`          |
| `/api/models`        | JSON model listing                                   |
| `/models/<file>`     | serve the raw model HTML from `models/`              |
| anything else        | 404                                                  |

- Path handling must prevent directory traversal (reject `..`, absolute paths); only serve known frontend files and files that resolve inside `web/` or `models/`.

### Frontend (`web/`)

- `index.html` - app shell markup.
- `style.css` - styling.
- `app.js` - fetches `/api/models`, builds the UI, handles mode switching and per-panel model selection.
- Plain vanilla JS, no framework. Served by `server.py`.

Each model renders inside its own `<iframe src="/models/<file>">`.
Iframes give each three.js scene a fully isolated document, window, and WebGL context, which is exactly what we want so scenes never interfere with each other or the shell.

## UI

### Top bar

- App title.
- **Single / Compare** mode toggle.
- **Show prompt** button - opens a slide-over panel displaying the contents of `prompt.txt` (fetched from the server) so the benchmark criteria are always one click away while judging. Dismissible.

### Single mode

- One model picker (dropdown).
- One large, full-height viewport (iframe) below.
- Small per-panel toolbar: model selector, **reload** iframe, **open in new tab**.

### Compare mode

- Two panels side by side, each independent:
  - its own model dropdown (defaulting to two different models when at least two exist),
  - its own **reload** and **open in new tab** controls.
- On a narrow viewport the two panels stack vertically.

### Controls per panel

- **Model selector:** switches which model file the iframe loads.
- **Reload:** reloads the iframe - useful to restart a 3D scene or re-trigger a random seed.
- **Open in new tab:** opens `/models/<file>` directly for true full-window testing.

## Look and feel

- Warm, clean dark shell fitting the storybook / forest-canopy theme of the benchmark.
- The shell chrome is deliberately minimal so the model scenes dominate the screen.
- Responsive down to a narrow window (panels stack).

## Edge cases

- **No models in folder:** show a friendly empty state explaining to drop `.html` files into `models/`.
- **Only one model:** compare mode still works; both panels can show the same model, or the second panel shows an empty/placeholder prompt to pick one.
- **Model fails to load / throws:** that is the model's own problem rendered inside its iframe; the shell stays functional. (The benchmark cares about which models error, so we do not hide iframe failures.)

## Testing

- Manual E2E in Chrome (the benchmark's target browser): start the server, confirm the existing model lists and renders in single mode, switch to compare mode with two panels, reload and open-in-new-tab work, show-prompt displays `prompt.txt`, and the layout stacks on a narrow window.
- Verify `/api/models` reflects a newly added file after a refresh with no server restart.
- Verify directory-traversal paths are rejected.

## File layout

```
Treetop_benchmark/
  prompt.txt
  models/
    *.html
  server.py          # new
  web/               # new
    index.html
    style.css
    app.js
  docs/superpowers/specs/2026-10-01-treetop-viewer-design.md
```

## Notes

- This directory is not currently a git repository, so the design doc is written but not committed. If desired, `git init` can be run before implementation so work is version-controlled.
