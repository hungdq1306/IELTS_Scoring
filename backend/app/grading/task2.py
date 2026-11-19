import json
from decimal import Decimal, ROUND_HALF_UP
from time import perf_counter

from pydantic import ValidationError

from app.grading.aspects import ASPECT_LABELS
from app.grading.detailed import DETAILED_PROMPT, DETAILED_PROMPT_VERSION, detailed_input, essay_paragraphs
from app.grading.schemas import DetailedModelGrade, MAX_REVIEW_PARAGRAPHS
from app.grading.rubric import PROMPT_VERSION, RUBRIC_VERSION, SYSTEM_PROMPT
from app.grading.schemas import CRITERIA, GradeRequest, GradeResult, ModelGrade, Scores, word_count
from app.providers.base import Generation, LLMProvider, ProviderError


def overall_band(scores: Scores) -> float:
    total = sum(Decimal(str(value)) for value in scores.model_dump().values())
    half_band_units = (total / 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(half_band_units / 2)


def validate_grade(generation: Generation, request: GradeRequest, elapsed: int, *, detailed: bool = False) -> GradeResult:
    try:
        payload = (DetailedModelGrade if detailed else ModelGrade).model_validate_json(generation.raw)
    except ValidationError as exc:
        code = "invalid_json" if any(e["type"] == "json_invalid" for e in exc.errors()) else "invalid_schema"
        raise ProviderError(code, "Gemini returned an unusable grading response.",
                            attempts=generation.attempts, generation=generation) from exc

    if detailed:
        from app.grading.ownership import reject_question_evidence
        reject_question_evidence(generation, request)

    count = word_count(request.essay)
    warnings = []
    if count < 250:
        warnings.append(f"The response contains {count} words. IELTS Task 2 asks for at least 250.")
    for criterion in CRITERIA:
        detail = getattr(payload.criterion_feedback, criterion)
        grounded = [example for example in detail.evidence if example.quote in request.essay]
        removed = len(detail.evidence) - len(grounded)
        if removed:
            warnings.append(f"Removed {removed} unverified evidence quote(s) for {criterion.replace('_', ' ')}.")
        detail.evidence = grounded
    corrections = [item for item in payload.grammar_corrections if item.original in request.essay and item.original != item.corrected]
    if len(corrections) != len(payload.grammar_corrections):
        warnings.append("Some grammar corrections were omitted because their original text could not be found.")
    payload.grammar_corrections = corrections

    paragraphs = essay_paragraphs(request.essay)
    if isinstance(payload, DetailedModelGrade):
        aspects = {item.aspect: item for item in reversed(payload.aspect_reviews)}
        payload.aspect_reviews = [aspects[label] for label in ASPECT_LABELS if label in aspects]
        if len(aspects) != len(ASPECT_LABELS):
            warnings.append("Some diagnostic aspects are unavailable.")
        reviews = {}
        for review in payload.paragraph_reviews:
            if review.paragraph_number > len(paragraphs) or review.paragraph_number in reviews:
                continue
            paragraph = paragraphs[review.paragraph_number - 1]
            if review.evidence and review.evidence.quote not in paragraph:
                review.evidence = None
                warnings.append(f"An unverified quote was omitted from paragraph {review.paragraph_number}.")
            reviews[review.paragraph_number] = review
        payload.paragraph_reviews = [reviews[index] for index in sorted(reviews)]
        if len(reviews) != min(len(paragraphs), MAX_REVIEW_PARAGRAPHS):
            warnings.append("Some paragraphs have no validated review.")
        if len(paragraphs) > MAX_REVIEW_PARAGRAPHS:
            warnings.append(f"Paragraph review covers up to {MAX_REVIEW_PARAGRAPHS} paragraphs.")
        grounded_suggestions = [item for item in payload.language_suggestions
                                if item.original in request.essay and item.original != item.corrected]
        if len(grounded_suggestions) != len(payload.language_suggestions):
            warnings.append("Some language suggestions were omitted because their edits could not be verified.")
        payload.language_suggestions = grounded_suggestions

    return GradeResult(
        paragraph_count=len(paragraphs) if detailed else None,
        **payload.model_dump(), estimated_overall_band=overall_band(payload.criterion_scores),
        word_count=count, model=generation.model, model_version=generation.version,
        rubric_version=RUBRIC_VERSION, prompt_version=DETAILED_PROMPT_VERSION if detailed else PROMPT_VERSION, latency_ms=elapsed,
        provider_latency_ms=generation.latency_ms, usage=generation.usage, attempts=generation.attempts,
        validation_warnings=warnings,
    )


async def grade_essay(request: GradeRequest, provider: LLMProvider, *, detailed: bool = False, experiment: str | None = None) -> tuple[GradeResult, Generation]:
    if word_count(request.essay) == 0:
        raise ProviderError("empty_essay", "Enter at least one word to evaluate.", 422)
    started = perf_counter()
    from app.grading.fewshot import configuration, compose, protect
    config = configuration(experiment)
    if config is not None:
        detailed = True
        protect(request, config)
    system = DETAILED_PROMPT if detailed else SYSTEM_PROMPT
    output_schema = DetailedModelGrade if detailed else ModelGrade
    user = (
        detailed_input(request)
        if detailed
        else json.dumps(
            {**request.model_dump(exclude_defaults=True), "word_count": word_count(request.essay)},
            ensure_ascii=False,
        )
    )
    if config is not None:
        system, user = compose(system, user, config)
    generation = await provider.generate_structured(system, user, output_schema)
    result = validate_grade(generation, request, round((perf_counter() - started) * 1000), detailed=detailed)
    if config is not None:
        result.fewshot_config = experiment
        result.reference_example_ids = [e["essay_id"] for e in config["examples"]]
        result.reference_sha256 = config["reference_sha256"]
        result.fewshot_version = config['version']
        result.production_fewshot_ready = config.get('production_fewshot_ready')
        result.diagnostic_mode = config.get('diagnostic_mode',False)
        if result.diagnostic_mode:
            result.validation_warnings.append('Diagnostic lecturer few-shot: some reference Task 2 prompts remain unverified. This configuration is not production-validated.')
        result.prompt_version += ":" + config["version"] + ":" + experiment
    return result, generation
