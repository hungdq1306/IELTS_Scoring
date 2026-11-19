import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import create_app
from app.practice.schemas import ErrorDraft,ExerciseDraft,PracticeDraft,PracticeReview,AnswerAssessment
from app.practice.diagnosis import verify_errors,validate_exercise,prioritize
from app.practice.store import PracticeStore
from app.practice.service import PracticeService
from app.providers.base import Generation,ProviderError
from test_mvp import payload

QUESTION='Should technology support students in education?'
ESSAY='Technology help students access useful materials. It give learners more flexibility.'

def error(**kw):
 return {'error_id':'d1','criterion':'GRA','category':'grammar','subtype':'subject_verb_agreement','original_quote':'Technology help students','suggested_correction':'Technology helps students','explanation':'A singular subject needs a singular present-tense verb.','severity':'high','paragraph_number':1,'optional_style':False,**kw}

def exercise(**kw):
 return {'source_error_id':'d1','type':'multiple_choice','skill':'subject_verb_agreement','difficulty':1,'instruction':'Choose the correct verb form.','question':'A digital library ___ students find books.','options':['help','helps','helping','have helped'],'correct_answer':'helps','accepted_alternatives':[],'target_span':'','explanation':'The singular subject takes helps.','hint':'Look at the number of the subject.','learning_objective':'Match present-tense verbs with singular subjects.','evaluation_rubric':['Select the correct singular present-tense verb.'],**kw}

class FakeProvider:
 def __init__(self):self.calls=[];self.fail=None;self.wait=None
 async def close(self):pass
 async def generate_structured(self,system,user,schema):
  self.calls.append(schema.__name__)
  if self.wait:await self.wait.wait()
  if self.fail:raise self.fail
  if schema is PracticeDraft:
   result={'errors':[error()], 'exercises':[exercise(),exercise(type='sentence_correction',difficulty=2,question='A useful website help people learn.',options=[],correct_answer='A useful website helps people learn.',instruction='Correct the sentence.'),exercise(type='error_imitation',difficulty=4,question='A patient tutor help beginners. Each learner have a notebook.',options=[],correct_answer='A patient tutor helps beginners. Each learner has a notebook.',instruction='Correct the repeated agreement errors.') ]}
  elif schema is PracticeReview:
   result={'errors':[{'error_id':'d1','real_error':True,'correction_valid':True,'reason':'Valid agreement error.'}], 'exercises':[{'index':i,**{k:True for k in ['aligned','answer_correct','unambiguous','explanation_correct','difficulty_appropriate','distractors_plausible','no_answer_leak','no_injection']},'reason':'Meets the checks.'} for i in range(3)]}
  elif schema is AnswerAssessment:
   result={'outcome':'correct','explanation':'The target agreement error was fixed and meaning preserved.','suggested_improvement':'','target_fixed':True,'meaning_preserved':True,'no_new_serious_errors':True}
  else:result={**payload(),'aspect_reviews':[],'paragraph_reviews':[],'language_suggestions':[]}
  return Generation(json.dumps(result),'offline-fixture',None,5,{'total_token_count':20},[])


def setup(tmp_path,provider=None):
 store=PracticeStore(tmp_path/'practice.sqlite3');session,token=store.new_session()
 sid=store.create_submission(session,QUESTION,ESSAY,{})
 return store,session,token,sid,PracticeService(store,provider or FakeProvider())


def test_evidence_ownership_dedup_and_taxonomy():
 drafts=[ErrorDraft(**error()),ErrorDraft(**error(error_id='d2')),ErrorDraft(**error(error_id='d3',original_quote='not in the student essay')),ErrorDraft(**error(error_id='d4',optional_style=True))]
 verified,mapping,rejected=verify_errors(drafts,ESSAY,'sub')
 assert len(verified)==1 and len(rejected)==3
 assert ESSAY[verified[0]['start']:verified[0]['end']]==verified[0]['original_quote']
 assert not verified[0]['exercise_eligible']
 assert len(prioritize(verified))==1
 verified,_,rejected=verify_errors([ErrorDraft(**error(subtype='not_a_skill'))],ESSAY,'sub')
 assert not verified


def test_exercise_validation_rejects_bad_key_and_discourse_mismatch():
 e=error();e['error_id']='stable'
 assert not validate_exercise(ExerciseDraft(**exercise()),e,ESSAY)
 assert validate_exercise(ExerciseDraft(**exercise(correct_answer='unknown')),e,ESSAY)
 assert validate_exercise(ExerciseDraft(**exercise(options=['helps','helps','help'])),e,ESSAY)
 e['category']='task_response'
 assert validate_exercise(ExerciseDraft(**exercise()),e,ESSAY)


def test_generation_is_idempotent_and_keys_hidden(tmp_path):
 store,session,token,sid,service=setup(tmp_path);provider=service.provider
 result=asyncio.run(service.generate(sid,session))
 assert len(result['exercises'])==3 and len(provider.calls)==2
 assert all('correct_answer' not in e and 'accepted_alternatives' not in e and 'hint' not in e for e in result['exercises'])
 assert 'suggested_correction' not in result['errors'][0]
 assert asyncio.run(service.generate(sid,session))==result
 assert len(provider.calls)==2
 assert store.session(token)==session and store.session('fake') is None


def test_mcq_attempts_hint_progress_and_ownership(tmp_path):
 store,session,token,sid,service=setup(tmp_path)
 batch=asyncio.run(service.generate(sid,session));eid=batch['exercises'][0]['exercise_id']
 with pytest.raises(HTTPException):store.owned_exercise(eid,'someone_else')
 service.hint(eid,session)
 wrong=asyncio.run(service.answer(eid,session,'help','request_001'))
 right=asyncio.run(service.answer(eid,session,'helps','request_002'))
 assert wrong['outcome']=='incorrect' and right['outcome']=='correct'
 assert len(service.provider.calls)==2 # checking and hint never call Gemini
 assert asyncio.run(service.answer(eid,session,'helps','request_002'))==right
 with pytest.raises(HTTPException):asyncio.run(service.answer(eid,session,'helping','request_002'))
 progress=store.progress(sid,session)
 assert progress['exercises_completed']==1 and progress['attempts']==2 and progress['first_attempt_accuracy']==0
 assert progress['unassisted_first_attempt_accuracy'] is None
 reloaded=PracticeStore(store.path)
 assert reloaded.progress(sid,session)==progress


def test_free_text_alternatives_and_revision_idempotency(tmp_path):
 store,session,token,sid,service=setup(tmp_path)
 batch=asyncio.run(service.generate(sid,session));eid=batch['exercises'][1]['exercise_id']
 result=asyncio.run(service.answer(eid,session,'A useful website helps people learn.','request_001'))
 assert result['evaluator']=='deterministic_key_match'
 result=asyncio.run(service.answer(eid,session,'People learn with help from a useful website.','request_002'))
 assert result['evaluator']=='gemini_automated' and result['outcome']=='correct'
 r=asyncio.run(service.revision(sid,session,1,'Technology helps students access materials. It gives learners flexibility.','revision_001'))
 calls=len(service.provider.calls)
 assert asyncio.run(service.revision(sid,session,1,r['after'],'revision_001'))==r
 assert len(service.provider.calls)==calls
 assert store.progress(sid,session)['revisions'][0]['after']==r['after']


@pytest.mark.parametrize('code,status',[('timeout',504),('rate_limited',429),('daily_quota',429)])
def test_provider_errors_leave_grading_and_bounded_generation(tmp_path,code,status):
 provider=FakeProvider();provider.fail=ProviderError(code,'Fixture failure',status)
 store,session,token,sid,service=setup(tmp_path,provider)
 for _ in range(2):
  with pytest.raises(ProviderError):asyncio.run(service.generate(sid,session))
 with pytest.raises(HTTPException):asyncio.run(service.generate(sid,session))
 assert len(provider.calls)==2 and service.public(sid,session)['state']=='failed'
 assert store.owned_submission(sid,session)['essay']==ESSAY


def test_concurrent_duplicate_generation_is_not_rebilled(tmp_path):
 async def scenario():
  provider=FakeProvider();provider.wait=asyncio.Event()
  store,session,token,sid,service=setup(tmp_path,provider)
  first=asyncio.create_task(service.generate(sid,session));await asyncio.sleep(.02)
  with pytest.raises(HTTPException) as e:await service.generate(sid,session)
  assert e.value.status_code==409
  provider.wait.set();await first
  assert len(provider.calls)==2
 asyncio.run(scenario())


def test_http_end_to_end_and_cookie_ownership(tmp_path):
 provider=FakeProvider()
 app=create_app(tmp_path/'data',tmp_path/'results',lambda _:provider)
 with TestClient(app) as client:
  assert client.get('/api/practice/submissions').json()=={'items':[]}
  response=client.post('/api/writing/task2/evaluate',json={'prompt':QUESTION,'essay':ESSAY})
  assert response.status_code==200,response.text
  sid=response.json()['submission_id'];assert sid
  cookie=client.cookies.get('ielts_practice_session');assert cookie
  assert 'HttpOnly' in response.headers['set-cookie']
  assert client.get(f'/api/writing/task2/{sid}/submission').json()['grade']['criterion_scores']==response.json()['criterion_scores']
  batch=client.post(f'/api/writing/task2/{sid}/exercises');assert batch.status_code==200,batch.text
  e=batch.json()['exercises'][0];assert 'correct_answer' not in e
  assert client.get(f"/api/exercises/{e['exercise_id']}/feedback").status_code==404
  answer=client.post(f"/api/exercises/{e['exercise_id']}/answer",json={'answer':'helps','request_id':'request_001'})
  assert answer.status_code==200,answer.text
  assert client.get(f'/api/writing/task2/{sid}/progress').json()['exercises_completed']==1
  client.cookies.clear()
  assert client.get(f'/api/writing/task2/{sid}/exercises').status_code==401
  session2,token2=app.state.practice.store.new_session();client.cookies.set('ielts_practice_session',token2)
  assert client.get(f'/api/writing/task2/{sid}/submission').status_code==404
  assert client.post(f"/api/exercises/{e['exercise_id']}/answer",json={'answer':'helps','request_id':'request_002'}).status_code==404


def test_lecturer_metrics_exclude_missing_labels_and_preserve_reviews(tmp_path):
 from benchmark.practice import human_metrics,write_review
 target=tmp_path/'review.csv'
 rows=[{'review_id':'one','real_error':'','notes':''},{'review_id':'two','real_error':'','notes':''}]
 write_review(target,rows,['real_error','notes'])
 assert human_metrics(target,['real_error'])['real_error']['rate'] is None
 target.write_text('review_id,real_error,notes\none,1,checked\ntwo,,\n')
 write_review(target,rows,['real_error','notes'])
 assert human_metrics(target,['real_error'])['real_error']=={'reviewed':1,'positive':1,'rate':1.0}
 assert 'checked' in target.read_text()
 target.write_text('review_id,real_error\none,maybe\n')
 with pytest.raises(ValueError):human_metrics(target,['real_error'])


def test_blank_answers_are_rejected():
 from app.practice.schemas import AnswerRequest
 from pydantic import ValidationError
 with pytest.raises(ValidationError):AnswerRequest(answer='   ',request_id='blank-answer-01')
