# Treetop Benchmark Viewer

A small local web app to browse and visually compare the model-generated 3D treetop-village HTML files produced for the Treetop benchmark.

Each model run is a single, self-contained HTML file (three.js, fully procedural) living in `models/`.
The viewer loads any one of them full-screen, or puts two side by side so you can judge quality by eye.

## Run it

```bash
python3 server.py           # then open http://localhost:8777/
python3 server.py 9000      # use a different port
```

The server has no third-party dependencies - Python 3 standard library only.

## Use it

- **Single** mode: pick one model, view it full-height.
- **Compare** mode: two panels side by side, each with its own model picker. Stacks vertically on a narrow window.
- Each panel has **reload** (restart the scene / re-seed) and **open in new tab** (true full-window test).
- **Prompt** reveals the benchmark prompt (`prompt.txt`) so the criteria are one click away while judging.

## Add a model

Drop a self-contained `.html` file into `models/` and refresh the page.
The server reads the folder live, so nothing else is needed.
The filename becomes the display label: `Treetop_village_GPT6_Astra_High.html` shows as **"GPT6 Astra High"**.

## Layout

```
server.py            # zero-dependency local server
web/                 # frontend (index.html, style.css, app.js)
models/              # model HTML files go here
prompt.txt           # the benchmark prompt
docs/                # design spec
```

Each model renders in its own `<iframe>`, keeping every three.js scene fully isolated from the others and from the app shell.
