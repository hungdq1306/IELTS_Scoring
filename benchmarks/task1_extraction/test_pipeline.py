"""Offline regression checks: no network/API calls, all gold examples synthetic."""
import asyncio
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from PIL import Image
from . import audit_consistency, run_benchmark
from .eval_gold import evaluate
from .extractor import VERSION, compute_routing, extract, generate, normalize_image, read_jsonl
from .prepare_essayjudge import prepare, human_score, load_official_dataset, export_gold_template, scan_categories
from .sanity_checks import run_sanity_checks
from .schemas import BenchmarkRecord, Task1ExtractionResult


def table(rows=None, columns=None, **changes):
    value = dict(table_id="t_01", panel_title="Test", unit="%", is_percentage_distribution=False,
        columns=columns or ["1990", "2000"], rows=rows if rows is not None else [row("A", [40, 50])])
    value.update(changes)
    return value


def row(name, values, **changes):
    value = dict(series_name=name, is_total_row=False, values=values,
        raw_labels=[str(v) for v in values], row_confidence="high", needs_user_check=False)
    value.update(changes)
    return value


def raw(**changes):
    value = dict(visual_category="chart_static", title_and_units="Test", has_explicit_labels=True,
        image_clarity="clear", numeric_tables=[table()], spatial_or_process_steps=[],
        extraction_notes="", key_overview_points=["First", "Second"], model_self_confidence=99)
    value.update(changes)
    return Task1ExtractionResult.model_validate(value)


def record(image_hash, model="fixture-only", extraction=None):
    extraction = extraction or raw()
    sanity = run_sanity_checks(extraction)
    return BenchmarkRecord(image_hash=image_hash, model=model, pipeline_version=VERSION,
        extraction=extraction, sanity_report=sanity, **compute_routing(extraction, sanity),
        latency_ms=12, prompt_tokens=10, candidates_tokens=20, t_load_ms=1, t_normalize_ms=1,
        t_extract_ms=12, t_sanity_ms=1, t_total_ms=15, attempt_count=1,
        total_tokens_including_retries=30, token_usage_complete=True, attempts=[])


class PipelineTests(unittest.TestCase):
    def test_field_order(self):
        self.assertEqual(list(Task1ExtractionResult.model_fields), ["visual_category", "title_and_units",
            "has_explicit_labels", "image_clarity", "numeric_tables", "spatial_or_process_steps",
            "extraction_notes", "key_overview_points", "model_self_confidence"])

    def test_caps(self):
        for category, maximum in (("chart_static", 100), ("map", 80), ("process", 80), ("mixed", 80)):
            for clarity, clarity_cap in (("clear", 100), ("moderate", 80), ("blurry_or_cropped", 60)):
                value = raw(visual_category=category, image_clarity=clarity, model_self_confidence=100,
                    has_explicit_labels=category not in ("map", "process"),
                    spatial_or_process_steps=[dict(element_id="s_01",zone_or_stage="Stage 1",verbatim_labels=["Input"],observed_change_or_action="Arrow to output",item_confidence="high",needs_user_check=True)] if category in ("map", "process") else [])
                result = compute_routing(value)
                self.assertEqual(result["overall_confidence"], min(maximum, clarity_cap))
        self.assertEqual(compute_routing(raw(has_explicit_labels=False))["overall_confidence"], 78)

    def test_travel_total_and_percentage_sanity(self):
        travel = raw(numeric_tables=[table(rows=[row("A",[680.5]), row("B",[280.2]),
            row("Total",[448.9],is_total_row=True)],columns=["1990"])])
        sanity = run_sanity_checks(travel)
        self.assertTrue(any(w.startswith("total_row_mismatch") for w in sanity.sanity_warnings))
        self.assertEqual(compute_routing(travel,sanity)["overall_confidence"],75)
        self.assertEqual(compute_routing(travel,sanity)["routing_status"],"needs_user_check")
        for rows,columns in (([row("A",[42]),row("B",[60])],["2008"]),([row("2008",[42,60])],["A","B"])):
            result = run_sanity_checks(raw(numeric_tables=[table(rows=rows,columns=columns,is_percentage_distribution=True)]))
            self.assertTrue(any("sum=102.0%" in w for w in result.sanity_warnings))

    def test_percentage_boundary_and_total_column(self):
        good=raw(numeric_tables=[table(rows=[row("A",[50]),row("B",[51.5])],columns=["2008"],is_percentage_distribution=True)])
        self.assertFalse(run_sanity_checks(good).sanity_warnings)
        bad=raw(numeric_tables=[table(rows=[row("A",[1,2,5])],columns=["X","Y","Total"])])
        self.assertTrue(any("total_column_mismatch" in w for w in run_sanity_checks(bad).sanity_warnings))
        # Percentages are not always a partition of 100: do not sum arbitrary rates.
        self.assertFalse(run_sanity_checks(raw(numeric_tables=[table(rows=[row("A",[20,40])])])).sanity_warnings)

    def test_grid_defects(self):
        for tables in ([],[table(rows=[])],[table(rows=[row("A",[1])])],
            [table(rows=[row("A",[None,2])])],[table(rows=[row("A",[1,2],raw_labels=["1"])])]):
            report=run_sanity_checks(raw(numeric_tables=tables))
            self.assertFalse(report.grid_shape_valid)
            self.assertTrue(any("incomplete_grid_shape" in w for w in report.sanity_warnings))

    def test_process_mechanism_guard(self):
        value=raw(visual_category="process",numeric_tables=[],has_explicit_labels=False,
            spatial_or_process_steps=[dict(element_id="s_01",zone_or_stage="Stage 1",verbatim_labels=["Water Filter"],observed_change_or_action="Water is pumped into a closed-loop system",item_confidence="high",needs_user_check=True)])
        self.assertEqual(len(run_sanity_checks(value).sanity_warnings),2)
        value.spatial_or_process_steps[0].observed_change_or_action="Arrow from Water Filter to Storage"
        self.assertFalse(run_sanity_checks(value).sanity_warnings)

    def test_normalization(self):
        for size,expected in (((2048,1000),(1024,500)),((300,150),(300,150))):
            original=Image.new("RGBA",size,(30,40,50,100))
            digest,data=normalize_image(original)
            self.assertEqual(digest,hashlib.sha256(data).hexdigest())
            self.assertEqual(normalize_image(original),(digest,data))
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size,expected)
                self.assertEqual(image.mode,"RGB")

    def test_dedup_silver_and_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);Image.new("RGB",(100,100),"white").save(root/"chart.png")
            rows=[dict(image="chart.png",Essay=essay,Question="Biểu đồ",Type="map",**{"Overall Score":score}) for essay,score in (("low",4),("high",8))]
            records=prepare({"train":rows},root/"data",root)
            self.assertEqual(records[0]["essay_count"],2)
            self.assertEqual(records[0]["silver_reference_essay"],"high")
            self.assertEqual(read_jsonl(root/"data/unique_prompts.jsonl"),records)
            self.assertEqual(scan_categories(records,root/"data")["category_counts"],{"map":1})
            self.assertEqual(human_score({"scores":{"Overall Score":"7.5"}}),7.5)
            self.assertEqual(human_score({"A(ground_truth)":2,"B(ground_truth)":4}),3)
            self.assertIsNone(human_score({"Overall Score":"NaN"}))

    def test_gold_template_balanced_draft_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            categories=["map","process","mixed","chart_static","chart_time_series"]
            records=[dict(image_hash=f"{i:064x}",image_path="image.jpg",prompt="Q",visual_category_hint=categories[i%5]) for i in range(25)]
            rows=export_gold_template(records,20,Path(directory))
            self.assertEqual(len({r.image_hash for r in rows}),20)
            self.assertEqual({r.visual_category for r in rows},set(categories))
            self.assertTrue(all(r.verification_status=="draft" and r.reviewed_by is None for r in rows))
            with self.assertRaises(FileExistsError):export_gold_template(records,20,Path(directory))

    def test_official_source_provenance(self):
        buffer=io.BytesIO();Image.new("RGB",(80,80),"white").save(buffer,format="PNG")
        csv_data=("graph,Question,Essay,Type,argument_clarity(ground_truth),coherence(ground_truth)\n"
            "https://raw.githubusercontent.com/jsu360/example/chart.png,Q,Low,map,2,3\n"
            "https://raw.githubusercontent.com/jsu360/example/chart.png,Q,High,map,4,5\n").encode("gb18030")
        def fetch(url):return b'{"sha":"pinned"}' if "/commits/" in url else csv_data if url.endswith("data.csv") else buffer.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch("benchmarks.task1_extraction.prepare_essayjudge.fetch_bytes",side_effect=fetch) as network:
                dataset=load_official_dataset(root);load_official_dataset(root)
                self.assertEqual(network.call_count,3)
            records=prepare(dataset,root,root)
            self.assertEqual(records[0]["silver_score"],4.5)
            meta=json.loads((root/"source/provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["revision"],"pinned")
            Path(meta["images"][0]["path"]).write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError,"checksum mismatch"):load_official_dataset(root)

    def test_retry_telemetry_and_no_double_count(self):
        failures=[]
        for code in (503,504,429):
            exc=RuntimeError("busy");exc.code=code;failures.append(exc)
        response=SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=10,candidates_token_count=4,total_token_count=15))
        api=SimpleNamespace(models=SimpleNamespace(generate_content=Mock(side_effect=[*failures,response])))
        telemetry={}
        with patch("benchmarks.task1_extraction.extractor.asyncio.sleep",new_callable=AsyncMock) as sleep, patch("benchmarks.task1_extraction.extractor.random.uniform",return_value=0):
            self.assertIs(asyncio.run(generate(api,"fixture",[],Task1ExtractionResult,telemetry)),response)
            self.assertEqual([call.args[0] for call in sleep.await_args_list],[2,4,8])
        self.assertEqual(telemetry["attempt_count"],4)
        self.assertEqual(telemetry["total_tokens_including_retries"],15)
        self.assertFalse(telemetry["token_usage_complete"])
        self.assertEqual(len(telemetry["attempts"]),4)

    def test_retry_exhaustion_and_permanent_error(self):
        exc=RuntimeError("busy");exc.code=503
        api=SimpleNamespace(models=SimpleNamespace(generate_content=Mock(side_effect=exc)))
        telemetry={}
        with patch("benchmarks.task1_extraction.extractor.asyncio.sleep",new_callable=AsyncMock) as sleep:
            with self.assertRaises(RuntimeError):asyncio.run(generate(api,"fixture",[],Task1ExtractionResult,telemetry))
            self.assertEqual(sleep.await_count,4)
        self.assertEqual(telemetry["attempt_count"],5)
        api.models.generate_content=Mock(side_effect=ValueError("schema"))
        with self.assertRaises(ValueError):asyncio.run(generate(api,"fixture",[],Task1ExtractionResult))
        self.assertEqual(api.models.generate_content.call_count,1)

    def test_real_extract_stages_and_failed_hash(self):
        from .schemas import PromptRecord
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);digest,data=normalize_image(Image.new("RGB",(100,100),"white"));path=root/"image.jpg";path.write_bytes(data)
            prompt=PromptRecord(image_hash=digest,image_path=str(path),prompt="Q",silver_reference_essay="",silver_score=None,essay_count=1)
            response=SimpleNamespace(text=raw().model_dump_json(),usage_metadata=SimpleNamespace(prompt_token_count=10,candidates_token_count=20,total_token_count=30))
            api=SimpleNamespace(models=SimpleNamespace(generate_content=Mock(return_value=response)))
            result=asyncio.run(extract(api,prompt,"fixture"))
            self.assertEqual(result.attempt_count,1)
            self.assertTrue(result.normalization_reused)
            self.assertGreater(result.t_total_ms,0)
            path.write_bytes(b"corrupt")
            with self.assertRaises(ValueError) as caught:asyncio.run(extract(api,prompt,"fixture"))
            self.assertEqual(caught.exception.benchmark_telemetry["failed_stage"],"normalize")
            self.assertEqual(api.models.generate_content.call_count,1)

    def test_checkpoint_resume_audit_html_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);Image.new("RGB",(100,100),"white").save(root/"image.png")
            records=prepare({"train":[dict(image="image.png",Essay="<script>bad()</script>",Question="Biểu đồ",overall_score=8)]},root/"data",root)
            args=SimpleNamespace(data_dir=root/"data",output_dir=root/"outputs",limit=10,concurrency=2,model="fixture-only",allow_partial=False,skip_audit=False)
            result=record(records[0]["image_hash"])
            with patch.object(run_benchmark,"arguments",return_value=args),patch.object(run_benchmark,"client",return_value=Mock()),patch.object(run_benchmark,"extract",new_callable=AsyncMock,return_value=result) as mock:
                asyncio.run(run_benchmark.main());asyncio.run(run_benchmark.main());self.assertEqual(mock.await_count,1)
            response=SimpleNamespace(text=json.dumps(dict(verdict="consistent",discrepancy_notes="fixture")),usage_metadata=None)
            with patch.object(audit_consistency,"arguments",return_value=args),patch.object(audit_consistency,"client",return_value=Mock()),patch.object(audit_consistency,"generate",new_callable=AsyncMock,return_value=response) as mock:
                asyncio.run(audit_consistency.main());asyncio.run(audit_consistency.main());self.assertEqual(mock.await_count,1)
            document=(args.output_dir/"review_report.html").read_text(encoding="utf-8")
            self.assertIn("data:image/jpeg;base64,",document);self.assertIn("Biểu đồ",document)
            self.assertNotIn("<script>bad()",document);self.assertIn("&lt;script&gt;",document)
            self.assertIn("t_extract_ms",document);self.assertIn("t_01",document)
            (args.output_dir/"audits.jsonl").unlink()
            with patch.object(audit_consistency,"arguments",return_value=args),patch.object(audit_consistency,"client",return_value=Mock()),patch.object(audit_consistency,"generate",new_callable=AsyncMock,side_effect=RuntimeError("offline")):
                with self.assertRaisesRegex(RuntimeError,"1 audits failed"):asyncio.run(audit_consistency.main())
            self.assertIn("audit_failed",(args.output_dir/"review_report.html").read_text(encoding="utf-8"))
            (args.output_dir/"extraction_results.jsonl").write_text("",encoding="utf-8");args.allow_partial=True;args.skip_audit=True
            with patch.object(audit_consistency,"arguments",return_value=args):
                with self.assertRaisesRegex(RuntimeError,"1 missing extractions"):asyncio.run(audit_consistency.main())
            self.assertIn("Extraction unavailable",(args.output_dir/"review_report.html").read_text(encoding="utf-8"))

    def test_gold_metrics_and_draft_refusal(self):
        gold=dict(image_hash="test",image_path="test.jpg",visual_category="chart_static",verification_status="verified",
            reviewed_by="synthetic test fixture",reviewed_at="2026-11-23",has_explicit_labels=True,flawed_or_low_confidence=True,
            numeric_tables=[table(rows=[row("A",[100]),row("B",[100],raw_labels=["~100"]),row("C",[0]),row("D",[20])],columns=["Jan"])])
        result=dict(image_hash="test",routing_status="needs_user_check",extraction=dict(has_explicit_labels=True,
            numeric_tables=[table(rows=[row("A",[101]),row("B",[101]),row("C",[1]),row("E",[55])],columns=["January"])]))
        metrics=evaluate([gold],[result])
        self.assertEqual(metrics["cell_recall_pct"],75)
        self.assertAlmostEqual(metrics["numeric_tolerance_match_pct"],100/3)
        self.assertEqual(metrics["numeric_precision_pct"],25)
        self.assertEqual(metrics["numeric_recall_pct"],25)
        self.assertEqual(metrics["numeric_mape_pct"],1)
        self.assertEqual(metrics["mape_cell_count"],2)
        self.assertEqual(metrics["routing_safety_pct"],100)
        gold["verification_status"]="draft"
        with self.assertRaisesRegex(ValueError,"No human-verified"):evaluate([gold],[result])

    def test_gold_duplicate_and_missing_predictions(self):
        gold=dict(image_hash="test",image_path="test.jpg",visual_category="chart_static",verification_status="verified",
            reviewed_by="synthetic fixture",reviewed_at="2026-11-23",has_explicit_labels=True,flawed_or_low_confidence=True,numeric_tables=[table()])
        metrics=evaluate([gold],[])
        self.assertEqual(metrics["cell_recall_pct"],0);self.assertEqual(metrics["routing_safety_pct"],0)
        result=dict(image_hash="test",routing_status="auto_verified",extraction=dict(has_explicit_labels=True,numeric_tables=[table(),table()]))
        self.assertEqual(evaluate([gold],[result])["matched_gold_cells"],0)
        gold["reviewed_by"]=None
        with self.assertRaises(ValueError):evaluate([gold],[])

    def test_gold_hash_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"unique_prompts.jsonl").write_text(''.join(json.dumps(dict(image_hash=str(i)))+'\n' for i in range(4)),encoding="utf-8")
            selection=root/"selected.jsonl";selection.write_text('{"image_hash":"2"}\n{"image_hash":"3"}\n',encoding="utf-8")
            args=SimpleNamespace(data_dir=root,limit=1,select_hashes_from=selection)
            self.assertEqual(run_benchmark.select_prompts(args),[dict(image_hash="2")])
            selection.write_text('{"image_hash":"unknown"}\n',encoding="utf-8")
            with self.assertRaises(ValueError):run_benchmark.select_prompts(args)

    def test_corrupt_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"checkpoint.jsonl";path.write_text('{"ok":true}\n{broken',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"line 2"):read_jsonl(path)


if __name__=="__main__":unittest.main()
