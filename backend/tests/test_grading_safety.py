import json
import pytest
from app.grading.detailed import detailed_input
from app.grading.schemas import DetailedModelGrade, GradeRequest, ModelGrade
from app.grading.task2 import validate_grade
from app.providers.gemini import gemini_schema
from app.providers.base import ProviderError
from test_mvp import generation, payload


def test_small_enums_are_preserved():
    schema=gemini_schema(DetailedModelGrade)
    assert schema["$defs"]["LanguageSuggestion"]["properties"]["category"]["enum"]==["word_choice","clarity","style"]
    assert schema["$defs"]["ParagraphReview"]["properties"]["role"]["enum"]


def test_schema_orders_evidence_before_criterion_scores():
    for model_cls in (ModelGrade, DetailedModelGrade):
        schema=gemini_schema(model_cls)
        assert list(schema["properties"])[-1]=="criterion_scores"
        assert schema["required"][-1]=="criterion_scores"


def test_detailed_input_includes_word_count_and_short_essay_note():
    short_req=GradeRequest(prompt="Should cities invest in public transport?",essay="One two three four five.")
    short_payload=json.loads(detailed_input(short_req))
    assert short_payload["word_count"]==5
    assert "length_note" in short_payload and "under 250 words" in short_payload["length_note"]

    long_essay=" ".join(["argument"] * 260)
    long_req=GradeRequest(prompt="Should cities invest in public transport?",essay=long_essay)
    long_payload=json.loads(detailed_input(long_req))
    assert long_payload["word_count"]==260
    assert "length_note" not in long_payload


def test_detailed_grading_rejects_question_only_evidence():
    data={**payload(),"aspect_reviews":[],"paragraph_reviews":[],"language_suggestions":[]}
    data["grammar_corrections"]=[{"original":"have been spend","corrected":"have been spent","explanation":"Participle"}]
    request=GradeRequest(prompt="Too many resources have been spend on conservation.",essay="Resources have been utilized for wildlife protection.")
    with pytest.raises(ProviderError) as e:validate_grade(generation(json.dumps(data)),request,1,detailed=True)
    assert e.value.code=="question_evidence_leak" and e.value.generation is not None
    request=GradeRequest(prompt=request.prompt,essay="Resources have been spend on wildlife protection.")
    result=validate_grade(generation(json.dumps(data)),request,1,detailed=True)
    assert result.grammar_corrections
