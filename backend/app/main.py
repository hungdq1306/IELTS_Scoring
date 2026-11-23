import asyncio
import hashlib
import re
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from filelock import FileLock, Timeout

from app import api_models as api
from app.config import ROOT, load_settings
from app.grading.schemas import GradeRequest
from app.grading.task2 import grade_essay
from app.providers.base import ProviderError
from app.providers.gemini import FREE_MODELS, GeminiProvider
from benchmark import store
from benchmark.datasets import PRIMARY, PROVENANCE, SPLIT_SIZES, read_csv
from benchmark.lexibot import PROVENANCE as LEXIBOT_PROVENANCE
from benchmark.metrics import summarize
from benchmark.run import evaluate_record, make_metadata, manifest_for


class FrontendFiles(StaticFiles):
    """Serve known React routes without routing missing API/assets to HTML."""
    async def get_response(self, path, scope):
        is_page = bool(re.fullmatch(
            r"(?:guide|overview|topics|practice|check|skill-practice|history|assessment(?:/(?:task-response|coherence-cohesion|lexical-resource|grammatical-range-accuracy))?)/?",
            path,
        ))
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not is_page:
                raise
            response = await super().get_response("index.html", scope)
        response.headers["Cache-Control"] = "no-store" if is_page or path in {"", ".", "index.html"} else "no-cache"
        return response


def create_app(data_root: Path = ROOT / "data", results_root: Path = ROOT / "results", provider_factory=GeminiProvider):
    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = load_settings()
        app.state.provider = provider_factory(replace(app.state.settings, retries=app.state.settings.web_retries))
        from app.practice.store import PracticeStore
        from app.practice.service import PracticeService
        app.state.practice_provider = provider_factory(replace(app.state.settings,retries=min(1,app.state.settings.retries)))
        app.state.practice_answer_provider = provider_factory(replace(app.state.settings,model=app.state.settings.practice_answer_model,retries=min(1,app.state.settings.retries)))
        app.state.practice = PracticeService(PracticeStore(results_root / "_practice.sqlite3"),app.state.practice_provider,app.state.practice_answer_provider)
        try:
            yield
        finally:
            await app.state.provider.close()
            if app.state.practice_provider is not app.state.provider:
                await app.state.practice_provider.close()
            if app.state.practice_answer_provider not in (app.state.provider,app.state.practice_provider):
                await app.state.practice_answer_provider.close()

    app = FastAPI(title="FogWrite — IELTS Writing Studio", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(ProviderError)
    async def handle_provider_error(_request: Request, exc: ProviderError):
        error = api.ErrorResponse(detail=api.ErrorBody(code=exc.code, message=exc.message, retry_after=exc.retry_after))
        return JSONResponse(status_code=exc.status, content=error.model_dump())

    def split_path(split):
        if split == "lexibot":
            return data_root / "processed" / "lexibot" / "lexibot.csv"
        return data_root / "splits" / f"{split}.csv"

    def find_essay(split, essay_id):
        path = split_path(split)
        if not path.is_file():
            raise HTTPException(404, "This split has not been prepared.")
        for row in read_csv(path):
            if row["essay_id"] == essay_id:
                return row
        raise HTTPException(404, "Essay not found in this split.")

    def run_path(run_id):
        if not re.fullmatch(r"(?:a[01]|fs[01257]|fs5_full|fs5_compact)-[a-f0-9]{16}", run_id):
            raise HTTPException(404, "Run not found.")
        path = results_root / f"{run_id}.sqlite3"
        if not path.is_file():
            raise HTTPException(404, "Run not found.")
        return path

    def run_details(path):
        meta, latest, history = store.read(path)
        summary = summarize(latest, history, meta["expected"])
        try:
            with FileLock(str(path) + ".lock", timeout=0):
                status = "complete" if summary["completed"] == summary["expected"] else "incomplete"
        except Timeout:
            status = "in_progress"
        return api.RunInfo.model_validate({"run": meta, "summary": summary, "status": status})

    from app.practice.routes import install_routes, COOKIE
    install_routes(app)

    def remember_submission(http_request, response, prompt, essay, grade):
        practice_store=app.state.practice.store
        session_id=practice_store.session(http_request.cookies.get(COOKIE))
        if not session_id:
            session_id,token=practice_store.new_session()
            response.set_cookie(COOKIE,token,httponly=True,samesite="strict",secure=http_request.url.scheme=="https",max_age=60*60*24*30)
        return practice_store.create_submission(session_id,prompt,essay,grade)

    @app.get("/api/health", response_model=api.Health)
    def health():
        state = app.state.settings
        return api.Health(model_configured=bool(state.api_key), model=state.model)

    @app.get("/api/models", response_model=api.Models)
    async def models(verify: bool = False):
        state = app.state.settings
        available = await app.state.provider.available_models() if verify else None
        return api.Models(configured_model=state.model, key_configured=bool(state.api_key),
                          free_tier_candidates=sorted(FREE_MODELS), available_to_key=available)

    @app.get('/api/fewshot/lecturer/status')
    def lecturer_status():
        from app.grading.lecturer import validation_status
        return validation_status()

    @app.get('/api/fewshot/lecturer/examples')
    def lecturer_examples():
        from app.grading.lecturer import _excerpt_for_compact, load_manifest, validation_status
        from app.grading.schemas import CRITERIA
        try:
            _, examples, _ = load_manifest()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, 'Lecturer examples are unavailable.') from exc
        items = []
        for example in examples:
            criterion_rationale = {}
            edits = []
            for criterion in CRITERIA:
                group = getattr(example.feedback_by_criterion, criterion)
                joined = group.summary
                if group.comments:
                    joined += ' ' + ' '.join(group.comments)
                criterion_rationale[criterion] = joined
                label = criterion.replace('_', ' ').title()
                for edit in group.edits:
                    edits.append({
                        'suggestion_id': label,
                        'operation': f"{label} edit",
                        'original': edit.original,
                        'corrected': edit.revised,
                        'criterion': criterion,
                        'explanation': edit.note,
                    })
            items.append({
                'essay_id': example.essay_id,
                'question': example.question,
                'essay': example.essay,
                'essay_excerpt_compact': _excerpt_for_compact(example.essay),
                'word_count': example.word_count,
                'scores': {c: getattr(example.scores, c) for c in CRITERIA},
                'lecturer_reported_overall_band': example.scores.overall,
                'calculated_overall_band': example.scores.overall,
                'feedback_by_criterion': example.feedback_by_criterion.model_dump(),
                'lecturer_assessment': {
                    'rationale_provenance': 'standardized_english_from_lecturer_annotation',
                    'criterion_rationale': criterion_rationale,
                    'verified_corrections': edits,
                },
                'source': example.source,
                'label_provenance': example.label_provenance,
            })
        return {'items': items, 'status': validation_status()}

    @app.post("/api/writing/task2/evaluate", response_model=api.Evaluation,
              responses={429: {"model": api.ErrorResponse}, 503: {"model": api.ErrorResponse}})
    async def evaluate(request: api.EvaluateRequest, http_request: Request, response: Response):
        provider = app.state.provider
        if request.source is None:
            grade, _ = await grade_essay(GradeRequest.model_validate(request.model_dump(exclude={"source", "experiment"})), provider, detailed=True, experiment=request.experiment)
            submission_id=remember_submission(http_request,response,request.prompt,request.essay,grade.model_dump())
            return api.Evaluation(**grade.model_dump(),submission_id=submission_id)
        split, essay_id = request.source.split, request.source.essay_id
        essay = find_essay(split, essay_id)
        if request.prompt != essay["prompt"] or request.essay != essay["essay"]:
            raise HTTPException(409, "The dataset essay changed. Evaluate the edited text without a source reference.")
        dataset_path = split_path(split)
        file_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
        manifest = manifest_for(dataset_path)
        meta = make_metadata(essay["source_dataset"], split, 1, app.state.settings.model, file_hash,
                             manifest, experiment=request.experiment, kind="manual", essay_id=essay_id)
        path = results_root / f"{meta['run_id']}.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(str(path) + ".lock", timeout=0):
                store.initialize(path, meta)
                row, raw = await evaluate_record(essay, provider, detailed=True, experiment=request.experiment)
                store.add(path, row, raw)
        except Timeout as exc:
            raise HTTPException(409, "An evaluation for this dataset essay is already running.") from exc
        if row["prediction"] is None:
            code = row["status"]
            status = (409 if code in {"reference_overlap","lecturer_reference_review_required"} else 429 if "quota" in code or "rate_limit" in code or "budget" in code else
                      503 if code in {"fewshot_configuration", "upstream_unavailable", "timeout", "missing_api_key", "gemini_configuration", "connection_error", "model_not_allowed"} else 502)
            raise ProviderError(code, row["error"], status)
        submission_id=remember_submission(http_request,response,request.prompt,request.essay,row["prediction"])
        return api.Evaluation(**row["prediction"], saved_run_id=meta["run_id"],submission_id=submission_id)

    @app.get("/api/datasets", response_model=api.DatasetInfo)
    def datasets():
        manifest = manifest_for(split_path("smoke"))
        splits = []
        for name in ("lexibot", *SPLIT_SIZES):
            path = split_path(name)
            rows = read_csv(path) if path.is_file() else []
            splits.append(api.SplitInfo(name=name, count=len(rows),
                                       bands=sorted(Counter(row["gold_overall"] for row in rows)),
                                       source="Lexibot" if name == "lexibot" else "Writing9",
                                       label_provenance=LEXIBOT_PROVENANCE if name == "lexibot" else PROVENANCE))
        return api.DatasetInfo(name=PRIMARY, revision=manifest.get("revision"),
                               label_provenance=PROVENANCE, splits=splits)

    @app.get("/api/datasets/{split}/essays", response_model=api.EssayPage)
    def essays(split: api.Split, band: float | None = Query(None, ge=0, le=9),
               offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
        path = split_path(split)
        rows = read_csv(path) if path.is_file() else []
        filtered = [row for row in rows if band is None or band == row["gold_overall"]]
        return api.EssayPage(total=len(filtered), items=[
            api.EssayOverview(**{field: row[field] for field in api.EssayOverview.model_fields})
            for row in filtered[offset:offset + limit]
        ])

    @app.get("/api/datasets/{split}/essays/{essay_id}", response_model=api.Essay)
    def essay(split: api.Split, essay_id: str):
        return api.Essay.model_validate(find_essay(split, essay_id))

    @app.get("/api/benchmarks", response_model=list[api.RunMetadata])
    def runs():
        found = []
        for path in [*results_root.glob("a[01]-*.sqlite3"), *results_root.glob("fs[012]-*.sqlite3"), *results_root.glob("fs[57]*.sqlite3")]:
            metadata, _, _ = store.read(path)
            found.append(api.RunMetadata.model_validate(metadata))
        return sorted(found, key=lambda item: item.created_at, reverse=True)

    @app.get("/api/fewshot/comparisons")
    def fewshot_comparisons():
        from benchmark.fewshot_report import paired
        files = [*results_root.glob("fs[012]-*.sqlite3"),*results_root.glob("fs[57]*.sqlite3")]
        metas = {path: store.read(path)[0] for path in files}
        output = []
        for control in files:
            if metas[control]["experiment"] != "FS0" or metas[control]["kind"] != "benchmark":
                continue
            for candidate in files:
                if metas[candidate]["experiment"] not in {"FS1", "FS2", "FS5", "FS5_FULL", "FS5_COMPACT", "FS7"} or metas[candidate]["kind"] != "benchmark":
                    continue
                try:
                    result = paired(control, candidate)
                except ValueError:
                    continue
                output.append({"source":metas[control]["dataset"], "split":metas[control]["split"],
                               "control":metas[control]["run_id"], "candidate":metas[candidate]["run_id"],
                               **{k:v for k,v in result.items() if k != "rows"}})
        return output

    @app.get("/api/benchmarks/{run_id}", response_model=api.RunInfo)
    async def run(run_id: str):
        return await asyncio.to_thread(run_details, run_path(run_id))

    @app.get("/api/benchmarks/{run_id}/results", response_model=list[api.RunResult])
    def run_results(run_id: str):
        _, latest, _ = store.read(run_path(run_id))
        return [api.RunResult.model_validate(row) for row in latest]

    @app.get("/api/benchmarks/{run_id}/lexibot/{essay_id}")
    def lexibot_reference(run_id: str, essay_id: str):
        from benchmark.lexibot import compare
        path = run_path(run_id)
        try:
            cases = compare(path, data_root / "processed" / "lexibot")["cases"]
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(404, "Matching Lexibot references are unavailable for this run.") from exc
        for case in cases:
            if case["essay_id"] == essay_id:
                return case["lexibot"]
        raise HTTPException(404, "Lexibot reference essay not found.")

    dist = ROOT / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/", FrontendFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
