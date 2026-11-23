"""Offline regression checks; no API keys or network required."""
import hashlib
import io
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from .extractor import compute_routing, normalize_image, read_jsonl
from .prepare_essayjudge import human_score, prepare
from .schemas import Task1ExtractionResult


class PipelineTests(unittest.TestCase):
    def test_field_order(self):
        self.assertEqual(list(Task1ExtractionResult.model_fields), [
            "visual_category", "title_and_units", "has_explicit_labels", "image_clarity",
            "extraction_notes", "structured_facts", "key_overview_points", "model_self_confidence"])

    def test_routing_matrix(self):
        for category, clarity, labels, confidence in itertools.product(
            ("chart_static", "chart_time_series", "map", "process", "mixed"),
            ("clear", "moderate", "blurry_or_cropped"), (False, True), (60, 84, 85, 100)):
            raw = Task1ExtractionResult(visual_category=category, image_clarity=clarity,
                has_explicit_labels=labels, model_self_confidence=confidence,
                title_and_units="", extraction_notes="", structured_facts=[dict(
                    fact_id="f_01", subject_or_stage="A", extracted_value_or_state="10",
                    item_confidence="high", needs_user_check=False)], key_overview_points=["A", "B"])
            cap = min(60 if clarity == "blurry_or_cropped" else 80 if clarity == "moderate" else 100,
                80 if category in ("map", "process", "mixed") else 100 if labels else 78)
            result = compute_routing(raw)
            self.assertEqual(result["overall_confidence"], min(confidence, cap))
            self.assertEqual(result["routing_status"] == "auto_verified",
                category.startswith("chart") and labels and clarity == "clear" and confidence >= 85)

    def test_normalization(self):
        for size, expected in (((2048, 1000), (1024, 500)), ((300, 150), (300, 150))):
            original = Image.new("RGBA", size, (30, 40, 50, 100))
            digest, data = normalize_image(original)
            self.assertEqual(digest, hashlib.sha256(data).hexdigest())
            self.assertEqual(normalize_image(original), (digest, data))
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size, expected)
                self.assertEqual(image.mode, "RGB")

    def test_dedup_and_silver_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (100, 100), "white").save(root / "chart.png")
            rows = [{"Image Path": "chart.png", "Essay": essay, "Question": "Biểu đồ",
                "Overall Score": score, "model_score": 100} for essay, score in (("low", 4), ("high", 8))]
            records = prepare({"train": rows}, root / "prepared", root)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["essay_count"], 2)
            self.assertEqual(records[0]["silver_reference_essay"], "high")
            self.assertEqual(read_jsonl(root / "prepared/unique_prompts.jsonl"), records)
            self.assertEqual(human_score({"scores": {"Overall Score": "7.5"}}), 7.5)
            self.assertIsNone(human_score({"Overall Score": "NaN"}))

    def test_html_escape_and_embedded_image(self):
        from .audit_consistency import render_card, write_report
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.jpg"
            Image.new("RGB", (100, 100), "white").save(image)
            prompt = dict(image_path=str(image), prompt="<script>bad()</script>",
                silver_reference_essay="Biểu đồ <unsafe>", silver_score=8, essay_count=2)
            extraction = dict(visual_category="chart_static", title_and_units="Units",
                extraction_notes="approximate", key_overview_points=["First", "Second"],
                structured_facts=[dict(fact_id="f_01", subject_or_stage="<A>",
                    extracted_value_or_state="10", item_confidence="medium", needs_user_check=True)])
            result = dict(extraction=extraction, image_hash="a"*64, routing_status="needs_user_check",
                overall_confidence=78, structural_cap=78, latency_ms=123)
            card = render_card(prompt, result, dict(verdict="consistent", discrepancy_notes="OK"))
            self.assertIn("data:image/jpeg;base64,", card)
            self.assertIn('class="check"', card)
            self.assertNotIn("<script>bad()", card)
            self.assertIn("&lt;script&gt;", card)
            path = root / "review.html"
            write_report(path, [card], "fixture")
            document = path.read_text(encoding="utf-8")
            self.assertIn("Biểu đồ", document)
            self.assertIn("#FEF9C3", document)
            self.assertIn("<!doctype html>", document)

    def test_retry_transient_only(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock, patch
        from .extractor import generate
        transient = RuntimeError("busy")
        transient.code = 429
        api = SimpleNamespace(models=SimpleNamespace(generate_content=Mock(side_effect=[transient, "ok"])))
        with patch("benchmarks.task1_extraction.extractor.asyncio.sleep", new_callable=AsyncMock) as sleep:
            result = asyncio.run(generate(api, "test", [], Task1ExtractionResult))
            self.assertEqual(result, "ok")
            self.assertEqual(sleep.await_count, 1)
        api.models.generate_content = Mock(side_effect=ValueError("invalid schema"))
        with self.assertRaises(ValueError):
            asyncio.run(generate(api, "test", [], Task1ExtractionResult))
        self.assertEqual(api.models.generate_content.call_count, 1)

    def test_checkpoint_resume_and_audit_integration(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock, patch
        from . import run_benchmark, audit_consistency
        from .extractor import VERSION
        from .schemas import BenchmarkRecord
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (100, 100), "white").save(root / "chart.png")
            records = prepare({"train": [dict(image="chart.png", essay="A is 10.", overall_score=8)]}, root / "data", root)
            args = SimpleNamespace(data_dir=root / "data", output_dir=root / "outputs",
                limit=5, concurrency=3, model="fixture-only")
            raw = Task1ExtractionResult(visual_category="chart_static", title_and_units="units",
                has_explicit_labels=True, image_clarity="clear", extraction_notes="fixture",
                structured_facts=[dict(fact_id="f_01", subject_or_stage="A", extracted_value_or_state="10",
                    item_confidence="high", needs_user_check=False)], key_overview_points=["A is highest", "A is 10"],
                model_self_confidence=95)
            result = BenchmarkRecord(image_hash=records[0]["image_hash"], model=args.model,
                pipeline_version=VERSION, extraction=raw, **compute_routing(raw), latency_ms=12,
                prompt_tokens=10, candidates_tokens=20)
            api = Mock()
            with patch.object(run_benchmark, "arguments", return_value=args), patch.object(run_benchmark, "client", return_value=api), patch.object(run_benchmark, "extract", new_callable=AsyncMock, return_value=result) as extract:
                asyncio.run(run_benchmark.main())
                asyncio.run(run_benchmark.main())
                self.assertEqual(extract.await_count, 1)
                self.assertEqual(len(read_jsonl(args.output_dir / "extraction_results.jsonl")), 1)
            response = SimpleNamespace(text=json.dumps(dict(verdict="consistent", discrepancy_notes="fixture")), usage_metadata=None)
            with patch.object(audit_consistency, "arguments", return_value=args), patch.object(audit_consistency, "client", return_value=api), patch.object(audit_consistency, "generate", new_callable=AsyncMock, return_value=response) as generate:
                asyncio.run(audit_consistency.main())
                asyncio.run(audit_consistency.main())
                self.assertEqual(generate.await_count, 1)
            self.assertTrue((args.output_dir / "review_report.html").is_file())

    def test_corrupt_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.jsonl"
            path.write_text('{"ok": true}\n{broken', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                read_jsonl(path)


if __name__ == "__main__":
    unittest.main()
