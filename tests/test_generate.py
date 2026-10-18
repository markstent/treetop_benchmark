"""Unit tests for the pure parts of generate.py (no network)."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate  # noqa: E402

DOC = "<!DOCTYPE html>\n<html><head></head><body>hi</body></html>"


class ExtractHtmlTests(unittest.TestCase):
    def test_clean_document_is_unchanged(self):
        html, before, after = generate.extract_html(DOC)
        self.assertEqual(html, DOC)
        self.assertEqual((before, after), (0, 0))

    def test_strips_markdown_fence(self):
        raw = "```html\n" + DOC + "\n```"
        html, before, after = generate.extract_html(raw)
        self.assertEqual(html, DOC)
        self.assertGreater(before, 0)
        self.assertGreater(after, 0)

    def test_strips_prose_before_and_after(self):
        raw = "Sure! Here is the file:\n\n" + DOC + "\n\nLet me know if you want changes."
        html, _, _ = generate.extract_html(raw)
        self.assertEqual(html, DOC)

    def test_accepts_html_tag_without_doctype(self):
        raw = "```\n<html lang='en'><body></body></html>\n```"
        html, _, _ = generate.extract_html(raw)
        self.assertEqual(html, "<html lang='en'><body></body></html>")

    def test_doctype_is_case_insensitive(self):
        raw = "<!doctype HTML><html></html>"
        html, _, _ = generate.extract_html(raw)
        self.assertEqual(html, raw)

    def test_uses_last_closing_tag(self):
        raw = DOC + "\n<!-- mentions </html> again -->\n</html>"
        html, _, _ = generate.extract_html(raw)
        self.assertTrue(html.endswith("</html>"))
        self.assertEqual(html, raw)

    def test_missing_start_raises(self):
        with self.assertRaises(generate.ExtractionError):
            generate.extract_html("just some text</html>")

    def test_missing_end_raises(self):
        with self.assertRaises(generate.ExtractionError):
            generate.extract_html("<!DOCTYPE html><html><body>cut off")

    def test_output_ends_with_newline(self):
        html, _, _ = generate.extract_html(DOC)
        self.assertTrue(generate.finalize_html(html).endswith("\n"))
        self.assertEqual(generate.finalize_html(html).count("\n"), DOC.count("\n") + 1)


class LabelTests(unittest.TestCase):
    def test_openrouter_id_to_label(self):
        self.assertEqual(generate.default_label("openai/gpt-6-astra"), "GPT_6_Astra")

    def test_claude_id_keeps_version_dots(self):
        self.assertEqual(generate.default_label("anthropic/claude-sonnet-5.5"), "Claude_Sonnet_5.5")

    def test_variant_suffix_is_kept(self):
        self.assertEqual(generate.default_label("anthropic/claude-opus-5.5:batch"), "Claude_Opus_5.5_Batch")

    def test_bare_model_id(self):
        self.assertEqual(generate.default_label("gpt-6-sol-pro"), "GPT_6_Sol_Pro")

    def test_user_label_spaces_become_underscores(self):
        self.assertEqual(generate.clean_label("GPT6 Astra High"), "GPT6_Astra_High")

    def test_user_label_rejects_path_characters(self):
        with self.assertRaises(ValueError):
            generate.clean_label("../evil")

    def test_output_stem_with_and_without_effort(self):
        self.assertEqual(generate.output_stem("Claude_Opus_5.5", None), "Treetop_village_Claude_Opus_5.5")
        self.assertEqual(generate.output_stem("Claude_Opus_5.5", "high"), "Treetop_village_Claude_Opus_5.5_High")


class EnvFileTests(unittest.TestCase):
    def test_parses_and_does_not_override_existing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text(
                "# comment\n"
                "OPENROUTER_API_KEY=sk-or-abc\n"
                "export LITELLM_API_KEY='quoted'\n"
                "LITELLM_BASE_URL=\"http://x:4000\"\n"
                "BAD LINE\n"
                "ALREADY=from-file\n"
            )
            env = {"ALREADY": "from-env"}
            generate.load_env_file(p, env)
            self.assertEqual(env["OPENROUTER_API_KEY"], "sk-or-abc")
            self.assertEqual(env["LITELLM_API_KEY"], "quoted")
            self.assertEqual(env["LITELLM_BASE_URL"], "http://x:4000")
            self.assertEqual(env["ALREADY"], "from-env")

    def test_missing_file_is_fine(self):
        env = {}
        generate.load_env_file(Path("/nonexistent/.env"), env)
        self.assertEqual(env, {})


class ProviderTests(unittest.TestCase):
    def test_openrouter_defaults(self):
        p = generate.resolve_provider("openrouter", None, {"OPENROUTER_API_KEY": "k"})
        self.assertEqual(p.base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(p.api_key, "k")
        self.assertEqual(p.reasoning_payload("high"), {"reasoning": {"effort": "high"}})
        self.assertIn("usage", p.stream_payload())

    def test_litellm_defaults_and_overrides(self):
        p = generate.resolve_provider("litellm", None, {"LITELLM_API_KEY": "k"})
        self.assertEqual(p.base_url, "http://localhost:4000")
        p = generate.resolve_provider("litellm", None, {"LITELLM_MASTER_KEY": "m", "LITELLM_BASE_URL": "http://h:1/"})
        self.assertEqual(p.api_key, "m")
        self.assertEqual(p.base_url, "http://h:1")
        p = generate.resolve_provider("litellm", "http://o:2", {"LITELLM_API_KEY": "k"})
        self.assertEqual(p.base_url, "http://o:2")
        self.assertEqual(p.reasoning_payload("high"), {"reasoning_effort": "high"})
        self.assertIn("stream_options", p.stream_payload())

    def test_missing_key_raises(self):
        with self.assertRaises(generate.ConfigError):
            generate.resolve_provider("openrouter", None, {})


class ManifestTests(unittest.TestCase):
    def test_label_from_stem(self):
        self.assertEqual(generate.label_from_stem("Treetop_village_Claude_Opus_5.5_Max"), "Claude Opus 5.5 Max")
        self.assertEqual(generate.label_from_stem("Other_thing"), "Other thing")

    def test_upsert_replaces_in_place_or_appends(self):
        entries = [{"file": "a.html", "label": "A"}, {"file": "b.html", "label": "B"}]
        out = generate.upsert_manifest_entry(entries, {"file": "a.html", "label": "A2", "note": "x"})
        self.assertEqual([e["file"] for e in out], ["a.html", "b.html"])
        self.assertEqual(out[0]["label"], "A2")
        out = generate.upsert_manifest_entry(entries, {"file": "c.html", "label": "C"})
        self.assertEqual([e["file"] for e in out], ["a.html", "b.html", "c.html"])
        self.assertEqual(len(entries), 2, "input list must not be mutated")

    def test_sync_adds_missing_and_drops_stale_but_keeps_existing(self):
        entries = [{"file": "Treetop_village_Kept.html", "label": "Custom", "note": "hand-written"},
                   {"file": "Treetop_village_Gone.html", "label": "Gone"}]
        files = ["Treetop_village_Kept.html", "Treetop_village_New_One.html"]
        out, added, removed = generate.sync_manifest(entries, files)
        self.assertEqual(added, ["Treetop_village_New_One.html"])
        self.assertEqual(removed, ["Treetop_village_Gone.html"])
        self.assertEqual(out[0], entries[0])
        self.assertEqual(out[1], {"file": "Treetop_village_New_One.html", "label": "New One"})

    def test_load_and_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "models.json"
            self.assertEqual(generate.load_manifest(p), [])
            generate.save_manifest(p, [{"file": "x.html", "label": "X"}])
            self.assertEqual(generate.load_manifest(p), [{"file": "x.html", "label": "X"}])
            self.assertTrue(p.read_text().endswith("\n"))

    def test_load_ignores_entries_without_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "models.json"
            p.write_text('{"models": [{"label": "no file"}, {"file": "ok.html"}, "junk"]}')
            self.assertEqual(generate.load_manifest(p), [{"file": "ok.html"}])


class CliTests(unittest.TestCase):
    def test_sync_manifest_needs_no_model(self):
        args = generate.parse_args(["--sync-manifest"])
        self.assertTrue(args.sync_manifest)
        self.assertIsNone(args.model)

    def test_litellm_is_default_provider(self):
        args = generate.parse_args(["some-model"])
        self.assertEqual(args.provider, "litellm")
        self.assertIsNone(args.reasoning)
        self.assertFalse(args.force)


class SseTests(unittest.TestCase):
    def test_parses_events_and_stops_at_done(self):
        body = io.BytesIO(
            b": OPENROUTER PROCESSING\n\n"
            b"data: {\"a\":1}\n\n"
            b"data: {\"a\":2}\n"
            b"\n"
            b"data: [DONE]\n\n"
            b"data: {\"a\":3}\n\n"
        )
        events = list(generate.iter_sse_json(body))
        self.assertEqual(events, [{"a": 1}, {"a": 2}])

    def test_collects_content_usage_and_finish(self):
        chunks = [
            {"choices": [{"delta": {"reasoning": "thinking..."}}]},
            {"choices": [{"delta": {"content": "<!DOCTYPE html>"}}]},
            {"choices": [{"delta": {"content": "<html></html>"}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost": 0.01}},
        ]
        result = generate.collect_stream(iter(chunks), on_progress=lambda n: None)
        self.assertEqual(result.text, "<!DOCTYPE html><html></html>")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.usage["completion_tokens"], 20)
        self.assertEqual(result.reasoning_chars, len("thinking..."))

    def test_error_chunk_raises(self):
        chunks = [{"error": {"message": "boom", "code": 402}}]
        with self.assertRaises(generate.ApiError):
            generate.collect_stream(iter(chunks), on_progress=lambda n: None)


if __name__ == "__main__":
    unittest.main()
