import asyncio
import copy
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.database import Database
from app.models import Base, TeacherAnchor, User
from app.grading.detailed import detailed_input, essay_paragraphs
from app.grading.payload import paragraph_metadata, essay_view, project_anchor
from app.grading.fewshot import compose
from app.grading.schemas import CRITERIA, GradeRequest
from app.grading.v2 import V2_RULES
from app.services.scorer import baseline_config, score
from app.providers.base import Generation
from test_rbac_and_ai_v2 import v2_output


@pytest.mark.parametrize('separator', ['\n\n','\r\n\r\n','\n \t\n'])
def test_lossless_paragraphs_anchor_and_target(separator):
    essay = 'Unicode café <tag> & text.\r\nA hard wrap.' + separator + '  Another paragraph with “quotes”.'
    req = GradeRequest(prompt='Discuss this general statement.',essay=essay)
    data = json.loads(detailed_input(req))
    raw = req.essay
    meta = paragraph_metadata(raw)
    assert meta['paragraph_boundary_verified']
    assert len(meta['paragraph_spans'])==2
    for n, span in enumerate(meta['paragraph_spans'],1):
        literal = raw[span['start']:span['end']]
        assert literal in data['student_essay']
        assert f'[p{n}]\n'+literal in data['student_essay']
    anchor = project_anchor({'question':req.prompt,'student_essay':raw,'scores':dict.fromkeys(CRITERIA,6), 'metadata':meta})
    assert anchor['student_essay']==data['student_essay']
    assert essay_paragraphs(raw)==[raw[s['start']:s['end']] for s in meta['paragraph_spans']]
    assert 'paragraphs' not in data and 'essay' not in data
    assert '&lt;' not in data['student_essay']


def test_unknown_boundaries_do_not_invent_paragraphs():
    essay='First line wraps\ninside a sentence. Finally, a conclusion.'
    view,meta=essay_view(essay)
    assert view==essay and not meta['paragraph_boundary_verified']
    assert 'do not penalize missing paragraph breaks as a student paragraphing error' in V2_RULES
    assert 'These TR findings do not cap CC' in V2_RULES
    assert 'A separate CC defect must be demonstrated' in V2_RULES


def test_allowlist_strips_legacy_db_fields_without_mutation():
    example={'essay_id':'opaque','question':'A task','student_essay':'Body.\n\nConclusion.',
             'scores':{**dict.fromkeys(CRITERIA,6),'overall':9},'examiner_calibration_cue':'Overall 9.0',
             'feedback_by_criterion':{'arbitrary':'unverified reasoning'}}
    original=copy.deepcopy(example)
    _,user=compose('rules', json.dumps({'prompt':'target','student_essay':'Unique target'}),
                   {'examples':[example],'experiment':'FS1'})
    data=json.loads(user)
    assert 'overall' not in json.dumps(data).lower()
    assert 'unverified reasoning' not in user
    assert example==original


@pytest.mark.parametrize('tr,cc',[(5,8),(8,5)])
def test_v2_single_payload_preserves_independent_criterion_scores(tr,cc):
    class Provider:
        async def generate_structured(self,system,user,schema,**kwargs):
            data=json.loads(user)
            target=data['NEW ESSAY']
            assert target['prompt']==submission.prompt
            assert target['student_essay']==submission.essay
            assert user.count(submission.essay)==1
            assert '<student_essay>' not in user and '<essay_metadata>' not in user
            assert 'COHERENCE AND COHESION ONLY' in system and 'TASK RESPONSE ONLY' in system
            output=v2_output();output.update(tr_score=tr,cc_score=cc)
            return Generation(json.dumps(output),'fake',None,1,{},[])
    submission=SimpleNamespace(prompt='Discuss ways to improve daily travel.',essay='Unique submitted essay. Evidence remains verbatim.',warnings=[],
                               config_snapshot={'fewshot':baseline_config(),'prompt_version':'v2'})
    result=asyncio.run(score(submission,Provider()))
    assert result['criterion_scores']['task_response']==tr
    assert result['criterion_scores']['coherence_cohesion']==cc


def test_default_sync_respects_ownership_and_is_idempotent(tmp_path,monkeypatch):
    from app import seed
    cfg={'version':'policy-a','examples':[{'essay_id':'first','student_essay':'A','scores':dict.fromkeys(CRITERIA,6)}]}
    monkeypatch.setattr(seed,'baseline_config',lambda:copy.deepcopy(cfg))
    async def run():
        db=Database('sqlite+aiosqlite:///'+(tmp_path/'sync.sqlite').as_posix())
        try:
            async with db.engine.begin() as c:await c.run_sync(Base.metadata.create_all)
            async with db.transaction() as s:
                user=User(external_auth_id='teacher-sync',role='teacher');s.add(user);await s.flush()
                s.add_all([TeacherAnchor(id='default-collision',teacher_id=user.id,payload={'private':'untouched'},version=9),
                           TeacherAnchor(id='personal',teacher_id=user.id,payload={'private':'kept'},version=4),
                           TeacherAnchor(id='default-retired',teacher_id=None,payload={'old':True},version=1)])
            await seed.seed_defaults(db)
            cfg['version']='policy-b';cfg['examples'][0]['student_essay']='B'
            cfg['examples'].append({'essay_id':'collision','student_essay':'never replace teacher','scores':dict.fromkeys(CRITERIA,7)})
            await seed.seed_defaults(db);await seed.seed_defaults(db)
            async with db.sessions() as s:
                rows={r.id:r for r in (await s.scalars(select(TeacherAnchor))).all()}
                assert rows['default-first'].version==2 and rows['default-first'].payload['student_essay']=='B'
                assert not rows['default-retired'].active and rows['default-retired'].version==2
                assert rows['default-collision'].payload=={'private':'untouched'} and rows['default-collision'].version==9 and rows['default-collision'].active
                assert rows['personal'].payload=={'private':'kept'} and rows['personal'].version==4 and rows['personal'].active
        finally:await db.engine.dispose()
    asyncio.run(run())


def test_text_redaction_updates_verified_offsets_without_merging_paragraphs():
    from app.grading.payload import transform_essay
    from app.guardrails import redact_pii
    essay='Contact student@example.com for details.\nA distinct second paragraph.'
    boundary=essay.index('\n')
    metadata={'paragraph_boundary_verified':True,'paragraph_spans':[
        {'id':'p1','start':0,'end':boundary}, {'id':'p2','start':boundary+1,'end':len(essay)}]}
    transformed, meta=transform_essay(essay,redact_pii,metadata)
    view, _=essay_view(transformed,meta)
    assert 'student@example.com' not in view and '[p1]' in view and '[p2]' in view
    assert meta['paragraph_boundary_verified'] and len(meta['paragraph_spans'])==2
    assert transformed[meta['paragraph_spans'][1]['start']:]=='A distinct second paragraph.'


def test_unverified_reasoning_cannot_be_promoted_by_a_source_label():
    example={'question':'A task','student_essay':'A response.', 'scores':dict.fromkeys(CRITERIA,6),
             'score_source':'examiner_verified','score_provenance':{'independently_verified':False},
             'feedback_by_criterion':{'task_response':{'summary':'Unverified reasoning'}}}
    projected=project_anchor(example)
    assert projected['provenance']['independently_verified'] is False
    assert 'feedback_by_criterion' not in projected


def test_offline_mode_blocks_real_sync_and_async_http(request):
    if not request.config.getoption('--offline'):
        pytest.skip('Requires explicit offline verification mode')
    import httpx
    with httpx.Client() as client:
        with pytest.raises(AssertionError,match='Real external HTTP'):
            client.get('https://example.invalid')
    async def run():
        async with httpx.AsyncClient() as client:
            with pytest.raises(AssertionError,match='Real external HTTP'):
                await client.get('https://example.invalid')
    asyncio.run(run())
