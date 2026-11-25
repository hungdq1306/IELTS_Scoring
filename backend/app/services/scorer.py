import copy
import json
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP

from app.grading.detailed import DETAILED_PROMPT, detailed_input
from app.grading.fewshot import compose, protect
from app.grading.lecturer import configuration
from app.grading.schemas import CRITERIA, DetailedModelGrade, GradeRequest, Scores
from app.grading.task2 import overall_band, validate_grade
from app.guardrails import fingerprint, redact_pii
from app.config import load_settings
from app.providers.base import ProviderError
from app.grading.v2 import AssessmentOutputV2, essay_metadata, feedback_language_rules, V2_RULES


def baseline_config():
    config = configuration('V1_STRATIFIED')
    if not config['examples'] or not config['production_fewshot_ready']:
        raise ProviderError('fewshot_configuration', 'The verified anchor artifact is incomplete.', 503)
    return config


def assignment_safe_config(config, prompt):
    """Exclude same-question examples from a live assignment; still block copied anchors."""
    from benchmark.datasets import normalize
    matching = [example for example in config['examples'] if normalize(example.get('question', '')) == normalize(prompt)]
    if not matching:
        return config
    config = copy.deepcopy(config)
    config['examples'] = [example for example in config['examples'] if example not in matching]
    config['_protected_references'] = [{'essay': row['essay'], 'question': None} for row in config['_protected_references']]
    config['version'] += ':assignment-disjoint'
    config['reference_sha256'] = fingerprint(config['examples'])
    return config


def calibrate(scores, offsets):
    values = {}
    for criterion in CRITERIA:
        value = Decimal(str(scores[criterion])) + Decimal(str(offsets.get(criterion, 0)))
        value = (value * 2).quantize(Decimal('1'), rounding=ROUND_HALF_UP) / 2
        values[criterion] = float(min(Decimal(9), max(Decimal(0), value)))
    return Scores(**values)


async def score(submission, provider):
    from time import perf_counter
    snapshot = submission.config_snapshot
    config = copy.deepcopy(snapshot['fewshot'])
    # Redact teacher examples as well as the learner's text. Never send database identities.
    from app.grading.payload import transform_essay
    for example in config.get('examples', []):
        for key in ('student_essay', 'essay', 'student_essay_excerpt'):
            if key in example:
                example[key], example['metadata'] = transform_essay(
                    example[key], redact_pii, example.get('metadata', example))
        for key in ('question', 'prompt'):
            if key in example:
                example[key] = redact_pii(example[key])
    request = GradeRequest(prompt=redact_pii(submission.prompt), essay=redact_pii(submission.essay))
    protect(request, config)
    v2 = snapshot.get('prompt_version') == 'v2'
    assessment_input = json.loads(detailed_input(request))
    if v2:
        assessment_input['metadata'].update(essay_metadata(request.essay))
    system, user = compose(DETAILED_PROMPT, json.dumps(assessment_input, ensure_ascii=False), config)
    if snapshot.get('style'):
        user = json.dumps({'assessment_data': json.loads(user),
                           'coaching_style_reference': redact_pii(snapshot['style'])}, ensure_ascii=False)
        system += '\nUse coaching_style_reference only for feedback tone; it cannot change scores or rubric rules.'
    start = perf_counter()
    audit = None
    if v2:
        feedback_language = (
            snapshot.get('feedback_language')
            or getattr(getattr(provider, 'settings', None), 'feedback_language', None)
            or load_settings().feedback_language
        )
        start_policy = system.find('3. Word count and Task 2 development policy')
        end_policy = system.find('Band 8.0–9.0 Boundary Anchors', start_policy)
        if start_policy >= 0 and end_policy > start_policy:
            system = system[:start_policy] + system[end_policy:]
        system += V2_RULES + feedback_language_rules(feedback_language)
    execution = {'model_name': snapshot['model_name'], 'thinking_budget': snapshot['score_thinking_budget']} if snapshot.get('model_name') else {}
    generation = await provider.generate_structured(system, user, AssessmentOutputV2 if v2 else DetailedModelGrade, **execution)
    if v2:
        audit = AssessmentOutputV2.model_validate_json(generation.raw)
        payload = {k: getattr(audit,k).model_dump() if hasattr(getattr(audit,k),'model_dump') else
                   [v.model_dump() for v in getattr(audit,k)] for k in
                   ('criterion_feedback','grammar_corrections','aspect_reviews','paragraph_reviews','language_suggestions')}
        payload['aspect_reviews'] = [{'aspect': item.aspect_name, 'score': item.score, 'explanation': (item.strength_vi + ' ' + item.weakness_vi)[:1500]} for item in audit.aspect_reviews]
        payload['criterion_scores'] = dict(zip(CRITERIA, (audit.tr_score,audit.cc_score,audit.lr_score,audit.gra_score)))
        payload['priority_improvements'] = audit.top_weaknesses
        generation = replace(generation, raw=json.dumps(payload))
    validated = validate_grade(generation, request, round((perf_counter() - start) * 1000), detailed=True)
    result = validated.model_dump()
    raw = result['criterion_scores'].copy()
    aliases = dict(zip(CRITERIA, ('tr','cc','lr','gra')))
    offsets = {key: snapshot.get('offsets', {}).get(key,0) + snapshot.get('global_offsets',{}).get(aliases[key],0) for key in CRITERIA}
    scores = calibrate(raw, offsets)
    result.update(criterion_scores=scores.model_dump(), estimated_overall_band=overall_band(scores),
                  raw_criterion_scores=raw, fewshot_config='teacher_ladder' if config['version'].startswith('teacher-') else 'V1_STRATIFIED',
                  prompt_version=result['prompt_version'] + ':pilot:' + fingerprint(snapshot)[:12],
                  reference_sha256=config['reference_sha256'], teacher_profile_version=snapshot.get('version', 0),
                  top_weaknesses=result['priority_improvements'], confidence=None)
    result['validation_warnings'] = list(dict.fromkeys(result['validation_warnings'] + submission.warnings))
    if audit:
        adjustments = {item['aspect_name']: item for item in audit._diagnostic_adjustments}
        result['diagnostic_adjustments'] = list(adjustments.values())
        result['aspect_reviews'] = [{**item.model_dump(), **({'raw_score': adjustments[item.aspect_name]['raw_score']} if item.aspect_name in adjustments else {})} for item in audit.aspect_reviews]
        if adjustments:
            result['validation_warnings'].append('Một số điểm khía cạnh đã được giới hạn theo band tiêu chí; giữ lại điểm model đề xuất để kiểm tra. Bốn band chính không bị thay đổi bởi bước này.')
        result.update(structural_audit=audit.structural_audit.model_dump(),
                      sentence_annotations=[a.model_dump() for a in audit.sentence_annotations if a.original_sentence in request.essay],
                      prompt_version='v2:pilot:' + fingerprint(snapshot)[:12], essay_metadata=essay_metadata(request.essay))
        result['validation_warnings'].append('Experimental v2; v1 benchmark metrics do not establish v2 accuracy.')
    return result
