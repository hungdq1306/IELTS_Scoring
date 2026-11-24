import asyncio
import json
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.grading.v2 import AssessmentOutputV2, V2_RULES, DiagnosticReview
from app.services.scorer import score, baseline_config
from app.providers.base import Generation
from test_rbac_and_ai_v2 import v2_output
from test_concurrency_and_guardrails import QUESTION, ESSAY

def test_diagnostics_constraints_and_order():
    fields=list(AssessmentOutputV2.model_fields)
    assert fields[:9]==['structural_audit','tr_reasoning','tr_score','cc_reasoning','cc_score','lr_reasoning','lr_score','gra_reasoning','gra_score']
    assert fields.index('aspect_reviews') < fields.index('sentence_annotations')
    assert 'develop_this_idea' not in str(AssessmentOutputV2.model_json_schema())
    assert 'next_step' not in str(AssessmentOutputV2.model_json_schema())
    item=dict(aspect_name='Depth of Ideas',score=6.0,strength_vi='Ý chính phù hợp.',weakness_vi='Chưa giải thích tác động.')
    assert DiagnosticReview(**item).score==6
    with pytest.raises(ValidationError):DiagnosticReview(**{**item,'weakness_vi':'Không có lỗi đáng kể'})
    bounded=AssessmentOutputV2.model_validate({**v2_output(),'aspect_reviews':[{**item,'score':8.0}]})
    assert bounded.aspect_reviews[0].score==7.0
    assert bounded.tr_score==6.5
    assert bounded._diagnostic_adjustments[0]['raw_score']==8.0

def test_v2_has_no_mechanical_word_count_caps():
    captured=[]
    class Provider:
        async def generate_structured(self,system,user,schema,**options):
            captured.append(system)
            assert "length_note" not in user
            return Generation(json.dumps(v2_output()),'fixture',None,1,{},[])
    async def run():
        for essay in [ESSAY,ESSAY+' Additional relevant explanation.'*50]:
            sub=SimpleNamespace(prompt=QUESTION,essay=essay,warnings=[],config_snapshot={'fewshot':baseline_config(),'prompt_version':'v2','feedback_language':'vi'})
            result=await score(sub,Provider())
            assert result['criterion_scores']['task_response']==6.5
    asyncio.run(run())
    for system in captured:
        assert '< 190 words rarely exceed' not in system
        assert 'length alone is neither good nor bad' in system
        assert 'FEEDBACK_LANGUAGE=vi' in system


def test_diagnostic_ceiling_preserves_core_band_and_discloses_raw_score():
    class Provider:
        async def generate_structured(self,system,user,schema,**options):
            payload=v2_output()
            payload['aspect_reviews']=[dict(aspect_name='Depth of Ideas',score=8.0,strength_vi='Ý chính liên quan.',weakness_vi='Cần phát triển ví dụ.')]
            return Generation(json.dumps(payload),'fixture',None,1,{},[])
    async def run():
        result=await score(SimpleNamespace(prompt=QUESTION,essay=ESSAY,warnings=[],config_snapshot={'fewshot':baseline_config(),'prompt_version':'v2','feedback_language':'vi'}),Provider())
        assert result['criterion_scores']['task_response']==6.5
        assert result['raw_criterion_scores']['task_response']==6.5
        assert result['aspect_reviews'][0]['score']==7.0
        assert result['aspect_reviews'][0]['raw_score']==8.0
        assert result['diagnostic_adjustments'][0]['raw_score']==8.0
    asyncio.run(run())


def test_structured_diagnostics_keep_full_text_through_legacy_adapter():
    class Provider:
        async def generate_structured(self,system,user,schema,**options):
            payload=v2_output()
            payload['aspect_reviews']=[dict(aspect_name='Depth of Ideas',score=6.0,strength_vi='A'*1000,weakness_vi='B'*1000)]
            return Generation(json.dumps(payload),'fixture',None,1,{},[])
    async def run():
        result=await score(SimpleNamespace(prompt=QUESTION,essay=ESSAY,warnings=[],config_snapshot={'fewshot':baseline_config(),'prompt_version':'v2','feedback_language':'vi'}),Provider())
        assert result['aspect_reviews'][0]['strength_vi']=='A'*1000
        assert result['aspect_reviews'][0]['weakness_vi']=='B'*1000
        assert result['criterion_scores']['task_response']==6.5
    asyncio.run(run())
