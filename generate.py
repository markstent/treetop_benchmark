#!/usr/bin/env python3
"""Run the Treetop benchmark prompt against any model and save the result.

Every model is treated identically:

  * ``prompt.txt`` is sent verbatim as the single user message, with no
    system prompt.
  * Reasoning effort is off unless ``--reasoning`` is given.
  * The response is streamed, then reduced to the span from the first
    ``<!DOCTYPE html>`` (or ``<html``) to the last ``</html>``. Anything
    outside that span (markdown fences, chatter) is discarded and reported.
  * The HTML is written to ``models/Treetop_village_<Label>[_<Effort>].html``
    and an entry is added to ``models.json`` so it shows up in the viewer.
  * The untouched raw response and a metadata JSON go to ``runs/<stem>/``.

``python3 generate.py --sync-manifest`` rebuilds ``models.json`` from the
``models/`` folder: files without an entry are added with a derived label,
entries whose file is gone are removed, existing entries are kept as is.

Works with a LiteLLM proxy (default) or OpenRouter directly. Standard
library only.

Examples:

  python3 generate.py gpt-6-astra --reasoning high --label "GPT6 Astra"
  python3 generate.py claude-opus-5.5 --base-url http://localhost:4000
  python3 generate.py anthropic/claude-opus-5.5 --provider openrouter
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator

ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompt.txt"
MODELS_DIR = ROOT / "models"
MANIFEST_PATH = ROOT / "models.json"
RUNS_DIR = ROOT / "runs"
ENV_PATH = ROOT / ".env"

FILE_PREFIX = "Treetop_village_"
REASONING_LEVELS = ("minimal", "low", "medium", "high", "xhigh", "max")

DEFAULT_MAX_TOKENS = 100_000
CONNECT_TIMEOUT_S = 60
STALL_TIMEOUT_S = 600  # max silence between streamed chunks
MAX_ATTEMPTS = 3


class ConfigError(Exception):
    """Bad arguments, missing key, missing files."""


class ApiError(Exception):
    """The provider returned an error."""


class ExtractionError(Exception):
    """No complete HTML document could be found in the response."""


# --------------------------------------------------------------------------- #
# Environment and providers
# --------------------------------------------------------------------------- #

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env_file(path: Path, env: dict) -> None:
    """Load KEY=VALUE lines from ``path`` into ``env`` without overriding."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _ENV_LINE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env.setdefault(key, value)


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    extra_headers: dict = field(default_factory=dict)

    def reasoning_payload(self, effort: str) -> dict:
        if self.name == "openrouter":
            return {"reasoning": {"effort": effort}}
        return {"reasoning_effort": effort}

    def stream_payload(self) -> dict:
        if self.name == "openrouter":
            return {"stream": True, "usage": {"include": True}}
        return {"stream": True, "stream_options": {"include_usage": True}}


def resolve_provider(name: str, base_url: str | None, env: dict) -> Provider:
    if name == "openrouter":
        key = env.get("OPENROUTER_API_KEY")
        if not key:
            raise ConfigError(
                "OPENROUTER_API_KEY is not set. Export it or put it in .env at the project root."
            )
        return Provider(
            name="openrouter",
            base_url=(base_url or "https://openrouter.ai/api/v1").rstrip("/"),
            api_key=key,
            extra_headers={
                "HTTP-Referer": "https://github.com/markstent/treetop_benchmark",
                "X-Title": "Treetop Benchmark",
            },
        )
    if name == "litellm":
        key = env.get("LITELLM_API_KEY") or env.get("LITELLM_MASTER_KEY")
        if not key:
            raise ConfigError(
                "LITELLM_API_KEY (or LITELLM_MASTER_KEY) is not set. Export it or put it in .env."
            )
        base = base_url or env.get("LITELLM_BASE_URL") or env.get("LITELLM_PROXY_API_BASE")
        return Provider(
            name="litellm",
            base_url=(base or "http://localhost:4000").rstrip("/"),
            api_key=key,
        )
    raise ConfigError(f"Unknown provider '{name}'")


# --------------------------------------------------------------------------- #
# Naming
# --------------------------------------------------------------------------- #

_SAFE_LABEL = re.compile(r"^[A-Za-z0-9._-]+$")
_ACRONYMS = {"gpt", "glm", "llm", "ai", "xai", "qwq", "r1", "o1", "o3", "o4"}


def default_label(model_id: str) -> str:
    """``anthropic/claude-sonnet-5.5`` -> ``Claude_Sonnet_5.5``."""
    tail = model_id.rsplit("/", 1)[-1]
    parts = [p for p in re.split(r"[-:]", tail) if p]
    words = []
    for p in parts:
        if p.lower() in _ACRONYMS:
            words.append(p.upper())
        else:
            words.append(p[:1].upper() + p[1:])
    return "_".join(words)


def clean_label(label: str) -> str:
    cleaned = "_".join(label.split())
    if not cleaned or not _SAFE_LABEL.match(cleaned) or ".." in cleaned:
        raise ValueError(
            f"Label '{label}' may only contain letters, digits, spaces, '.', '_' and '-'"
        )
    return cleaned


def output_stem(label: str, reasoning: str | None) -> str:
    stem = FILE_PREFIX + label
    if reasoning:
        stem += "_" + reasoning[:1].upper() + reasoning[1:]
    return stem


def label_from_stem(stem: str) -> str:
    """``Treetop_village_Claude_Opus_5.5_Max`` -> ``Claude Opus 5.5 Max``."""
    if stem.startswith(FILE_PREFIX):
        stem = stem[len(FILE_PREFIX):]
    return stem.replace("_", " ").strip()


# --------------------------------------------------------------------------- #
# Manifest (models.json) - the static list the viewer reads
# --------------------------------------------------------------------------- #

def load_manifest(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    entries = data.get("models", []) if isinstance(data, dict) else []
    return [e for e in entries if isinstance(e, dict) and e.get("file")]


def save_manifest(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps({"models": entries}, indent=2) + "\n", encoding="utf-8")


def upsert_manifest_entry(entries: list[dict], entry: dict) -> list[dict]:
    """Replace the entry with the same file, or append; returns a new list."""
    out = [e for e in entries if e.get("file") != entry["file"]]
    idx = next((i for i, e in enumerate(entries) if e.get("file") == entry["file"]), len(out))
    out.insert(idx, entry)
    return out


def sync_manifest(entries: list[dict], files: list[str]) -> tuple[list[dict], list[str], list[str]]:
    """Reconcile entries with the model files on disk.

    Returns (entries, added_files, removed_files). Existing entries are kept
    untouched; new files get a derived label; entries for missing files go.
    """
    present = set(files)
    kept = [e for e in entries if e["file"] in present]
    removed = [e["file"] for e in entries if e["file"] not in present]
    known = {e["file"] for e in kept}
    added = sorted(f for f in files if f not in known)
    for f in added:
        kept.append({"file": f, "label": label_from_stem(Path(f).stem)})
    return kept, added, removed


# --------------------------------------------------------------------------- #
# Response handling
# --------------------------------------------------------------------------- #

_START = re.compile(r"<!doctype\s+html|<html[\s>]", re.IGNORECASE)
_END = "</html>"


def extract_html(text: str) -> tuple[str, int, int]:
    """Return (html, chars_trimmed_before, chars_trimmed_after)."""
    m = _START.search(text)
    if not m:
        raise ExtractionError("no '<!DOCTYPE html>' or '<html' found in the response")
    start = m.start()
    end_idx = text.lower().rfind(_END)
    if end_idx < start:
        raise ExtractionError("no closing '</html>' found in the response")
    end = end_idx + len(_END)
    return text[start:end], start, len(text) - end


def finalize_html(html: str) -> str:
    return html if html.endswith("\n") else html + "\n"


def iter_sse_json(body: Iterable[bytes]) -> Iterator[dict]:
    """Yield decoded JSON objects from an OpenAI-style SSE stream."""
    for raw in body:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line.startswith("data:"):
            continue  # comments, blank lines, keep-alives
        data = line[5:].strip()
        if data == "[DONE]":
            return
        if not data:
            continue
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


@dataclass
class StreamResult:
    text: str = ""
    finish_reason: str | None = None
    usage: dict | None = None
    reasoning_chars: int = 0
    response_id: str | None = None
    served_model: str | None = None
    served_provider: str | None = None


def collect_stream(chunks: Iterable[dict], on_progress: Callable[[int, int], None]) -> StreamResult:
    result = StreamResult()
    parts: list[str] = []
    chars = 0
    for chunk in chunks:
        if "error" in chunk:
            err = chunk["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise ApiError(f"stream error: {msg}")
        result.response_id = chunk.get("id") or result.response_id
        result.served_model = chunk.get("model") or result.served_model
        result.served_provider = chunk.get("provider") or result.served_provider
        if chunk.get("usage"):
            result.usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                parts.append(content)
                chars += len(content)
                on_progress(chars, result.reasoning_chars)
            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
            if reasoning:
                result.reasoning_chars += len(reasoning)
                on_progress(chars, result.reasoning_chars)
            if choice.get("finish_reason"):
                result.finish_reason = choice["finish_reason"]
    result.text = "".join(parts)
    return result


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def request_stream(provider: Provider, payload: dict, on_progress: Callable[[int, int], None]) -> StreamResult:
    """POST the chat request and collect the streamed reply, with retries."""
    url = provider.base_url + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        **provider.extra_headers,
    }
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        got_content = False
        try:
            with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT_S) as resp:
                resp.fp.raw._sock.settimeout(STALL_TIMEOUT_S)  # type: ignore[attr-defined]

                def progress(chars: int, reasoning_chars: int) -> None:
                    nonlocal got_content
                    got_content = True
                    on_progress(chars, reasoning_chars)

                return collect_stream(iter_sse_json(resp), progress)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:2000]
            last_error = ApiError(f"HTTP {e.code} from {url}: {detail}")
            retryable = e.code == 429 or e.code >= 500
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            last_error = ApiError(f"network error talking to {url}: {e}")
            retryable = True
        except ApiError as e:
            last_error = e
            retryable = not got_content

        if got_content or not retryable or attempt == MAX_ATTEMPTS:
            break
        wait = 5 * attempt
        print(f"  attempt {attempt} failed ({last_error}); retrying in {wait}s", file=sys.stderr)
        time.sleep(wait)

    assert last_error is not None
    raise last_error


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the Treetop benchmark prompt against a model and save the HTML.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples:")[1],
    )
    p.add_argument("model", nargs="?", help="model id as the provider knows it, e.g. claude-opus-5.5 "
                                             "on a LiteLLM proxy or anthropic/claude-opus-5.5 on OpenRouter")
    p.add_argument("--sync-manifest", action="store_true",
                   help="rebuild models.json from the models/ folder and exit (no model needed)")
    p.add_argument("--provider", choices=("litellm", "openrouter"), default="litellm")
    p.add_argument("--base-url", help="override the provider's base URL (…/v1)")
    p.add_argument("--reasoning", choices=REASONING_LEVELS,
                   help="reasoning effort; omitted means the provider default (off)")
    p.add_argument("--label", help="display label, e.g. 'GPT6 Astra'. Default is derived from the model id")
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                   help=f"completion token limit sent to the provider (default {DEFAULT_MAX_TOKENS})")
    p.add_argument("--force", action="store_true", help="overwrite an existing model file")
    return p.parse_args(argv)


def run_sync_manifest() -> int:
    files = sorted(p.name for p in MODELS_DIR.glob("*.html")) if MODELS_DIR.is_dir() else []
    entries, added, removed = sync_manifest(load_manifest(MANIFEST_PATH), files)
    save_manifest(MANIFEST_PATH, entries)
    print(f"models.json: {len(entries)} entries, {len(added)} added, {len(removed)} removed")
    for f in added:
        print(f"  + {f}")
    for f in removed:
        print(f"  - {f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.sync_manifest:
        return run_sync_manifest()
    if not args.model:
        raise ConfigError("a model id is required (or pass --sync-manifest)")

    env = dict(os.environ)
    load_env_file(ENV_PATH, env)
    provider = resolve_provider(args.provider, args.base_url, env)

    if not PROMPT_PATH.is_file():
        raise ConfigError(f"missing {PROMPT_PATH}")
    prompt = PROMPT_PATH.read_text(encoding="utf-8")

    label = clean_label(args.label) if args.label else default_label(args.model)
    stem = output_stem(label, args.reasoning)
    out_path = MODELS_DIR / f"{stem}.html"
    run_dir = RUNS_DIR / stem
    if out_path.exists() and not args.force:
        raise ConfigError(f"{out_path.relative_to(ROOT)} already exists; pass --force to overwrite")

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": args.max_tokens,
        **provider.stream_payload(),
    }
    if args.reasoning:
        payload.update(provider.reasoning_payload(args.reasoning))

    print(f"Treetop benchmark run")
    print(f"  provider:  {provider.name} ({provider.base_url})")
    print(f"  model:     {args.model}")
    print(f"  reasoning: {args.reasoning or 'provider default'}")
    print(f"  output:    {out_path.relative_to(ROOT)}", flush=True)

    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    last_print = [0.0]

    def on_progress(chars: int, reasoning_chars: int) -> None:
        now = time.monotonic()
        if now - last_print[0] >= 2:
            last_print[0] = now
            think = f"  (thinking {reasoning_chars:,})" if reasoning_chars else ""
            print(f"\r  streaming… {chars:>8,} chars{think}  {now - t0:6.0f}s", end="", flush=True)

    status = "ok"
    error: str | None = None
    result = StreamResult()
    try:
        result = request_stream(provider, payload, on_progress)
    except ApiError as e:
        status, error = "api_error", str(e)
    finally:
        print(flush=True)
    duration = time.monotonic() - t0

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "raw.txt").write_text(result.text, encoding="utf-8")

    html = ""
    trimmed_before = trimmed_after = 0
    if status == "ok":
        if result.finish_reason == "length":
            status, error = "truncated", (
                f"response hit the max_tokens limit ({args.max_tokens}); "
                "raise --max-tokens and rerun"
            )
        else:
            try:
                html, trimmed_before, trimmed_after = extract_html(result.text)
            except ExtractionError as e:
                status, error = "no_html", str(e)

    meta = {
        "status": status,
        "error": error,
        "model": args.model,
        "served_model": result.served_model,
        "served_provider": result.served_provider,
        "response_id": result.response_id,
        "provider": provider.name,
        "base_url": provider.base_url,
        "label": label,
        "reasoning": args.reasoning,
        "max_tokens": args.max_tokens,
        "started_at": started.isoformat(),
        "duration_s": round(duration, 1),
        "finish_reason": result.finish_reason,
        "usage": result.usage,
        "cost_usd": (result.usage or {}).get("cost"),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "raw_chars": len(result.text),
        "reasoning_chars": result.reasoning_chars,
        "html_chars": len(html),
        "trimmed_before": trimmed_before,
        "trimmed_after": trimmed_after,
        "output": str(out_path.relative_to(ROOT)) if status == "ok" else None,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    if status != "ok":
        print(f"FAILED ({status}): {error}", file=sys.stderr)
        print(f"  raw response kept in {run_dir.relative_to(ROOT)}/raw.txt", file=sys.stderr)
        return 2

    MODELS_DIR.mkdir(exist_ok=True)
    out_path.write_text(finalize_html(html), encoding="utf-8")

    manifest_entry = {
        "file": out_path.name,
        "label": label_from_stem(stem),
        "model": result.served_model or args.model,
        "provider": f"{provider.name} ({provider.base_url})",
        "effort": args.reasoning or "default",
        "date": started.date().isoformat(),
        "note": "As generated, no edits.",
    }
    save_manifest(MANIFEST_PATH, upsert_manifest_entry(load_manifest(MANIFEST_PATH), manifest_entry))

    usage = result.usage or {}
    print(f"Done in {duration:.0f}s")
    print(f"  wrote:     {out_path.relative_to(ROOT)}  ({len(html):,} chars, {html.count(chr(10)) + 1:,} lines)")
    if trimmed_before or trimmed_after:
        print(f"  trimmed:   {trimmed_before} chars before, {trimmed_after} after (fences or chatter)")
    if usage:
        print(f"  tokens:    {usage.get('prompt_tokens', '?')} in, {usage.get('completion_tokens', '?')} out"
              + (f", cost ${usage['cost']:.4f}" if isinstance(usage.get("cost"), (int, float)) else ""))
    print(f"  manifest:  models.json updated")
    print(f"  details:   {run_dir.relative_to(ROOT)}/meta.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
