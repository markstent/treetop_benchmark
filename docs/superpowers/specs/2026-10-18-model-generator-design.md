---
title: Treetop Benchmark Generator - Design
date: 2026-10-18
status: approved
---

# Treetop Benchmark Generator - Design

## Purpose

A single script, `generate.py`, that runs `prompt.txt` against any model through a LiteLLM proxy or OpenRouter and saves the result where the viewer expects it.
The point is consistency: every model gets the same input, the same parameters, and the same post-processing, so the files in `models/` are comparable.

## Behaviour

- `prompt.txt` is the only user message. No system prompt.
- Reasoning effort is off unless `--reasoning <level>` is passed. If set, the level is appended to the filename, matching the existing `Treetop_village_GPT6_Astra_High.html`.
- Responses are streamed so long outputs cannot time out, with a stall timeout between chunks.
- Post-processing keeps the span from the first `<!DOCTYPE html>` or `<html` to the last `</html>` and discards the rest.
  Trimmed character counts are reported and recorded.
- Output goes to `models/Treetop_village_<Label>[_<Effort>].html`. The label derives from the model id or comes from `--label`.
- The raw reply and `meta.json` (status, model, provider, timing, usage, cost, finish reason, trim counts, prompt hash) go to `runs/<stem>/`, which is gitignored.
- Failures that must not produce a model file: the reply hit the token limit, no complete HTML document was found, or the API returned an error.
  The raw reply is still saved and the script exits non-zero.
- Existing model files are not overwritten without `--force`.
- Transient failures (429, 5xx, network) are retried up to three times, but never after any content has been received.

## Providers

- `litellm` (default): base URL from `--base-url`, else `LITELLM_BASE_URL`, else `http://localhost:4000`. Key from `LITELLM_API_KEY` or `LITELLM_MASTER_KEY`. Reasoning is sent as `reasoning_effort`.
- `openrouter`: base URL `https://openrouter.ai/api/v1`. Key from `OPENROUTER_API_KEY`. Reasoning is sent as `reasoning: {effort}`, and usage accounting is requested so cost is recorded.
- Keys and URLs are read from the environment first, then from a gitignored `.env` at the project root.

## Non-goals

- No scoring, no batch orchestration, no model discovery. One model per invocation.
- No third-party dependencies, matching `server.py`.

## Testing

- `tests/test_generate.py` covers extraction, labelling, env parsing, provider resolution, SSE parsing, and stream collection.
- End-to-end behaviour was verified against a local fake streaming server for the success, truncation, no-HTML, retry, overwrite-guard, and missing-key paths.
