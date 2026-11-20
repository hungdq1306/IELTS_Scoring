import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import create_app
from app.practice.batch import PracticeBatch
from app.practice.schemas import BatchAssessment,PracticeAnswer
from app.practice.service import PracticeService
from app.practice.store import PracticeStore
from app.providers.base import Generation,ProviderError
from test_practice import FakeProvider,setup,ESSAY,QUESTION


class BatchProvider(FakeProvider):
 def __init__(self):
  super().__init__();self.settings=SimpleNamespace(model='gemini-3.1-flash-lite');self.omit=False
 async def generate_structured(self,system,user,schema):
  if schema is not BatchAssessment:return await super().generate_structured(system,user,schema)
  self.calls.append(schema.__name__)
  if self.wait:await self.wait.wait()
  if self.fail:raise self.fail
  data=json.loads(user)
  items=[{'exercise_id':r['exercise']['exercise_id'],'outcome':'correct','explanation':'The target skill is applied and meaning preserved.',
          'suggested_improvement':'','target_fixed':True,'meaning_preserved':True,'no_new_serious_errors':True} for r in data['responses']]
  if self.omit:items=items[:-1]
  return Generation(json.dumps({'items':items,'summary':'Continue practising agreement in new contexts.'}),'offline-fixture',None,1,{'total_token_count':50},[])


def ready(tmp_path):
 store,session,token,sid,service=setup(tmp_path)
 evaluator=BatchProvider();service.answer_provider=evaluator
 asyncio.run(service.generate(sid,session))
 exercises=store.batch(sid)['data']['exercises']
 answers=[PracticeAnswer(exercise_id=e['exercise_id'],answer=e['correct_answer']) for e in exercises]
 return store,session,sid,service,PracticeBatch(service),answers,evaluator


def test_no_evaluation_until_every_exercise_is_answered(tmp_path):
 store,session,sid,service,batch,answers,evaluator=ready(tmp_path)
 batch.save(sid,session,answers[:1])
 assert batch.view(sid,session)['result'] is None and not evaluator.calls
 for invalid in [answers[:-1],[*answers[:-1],answers[-1].model_copy(update={'answer':'  '})],[answers[0],answers[0]],
                 [*answers[:-1],PracticeAnswer(exercise_id='not-owned',answer='text')]]:
  with pytest.raises(HTTPException) as exc:asyncio.run(batch.submit(sid,session,invalid,'submit_001'))
  assert exc.value.status_code==422
 assert not evaluator.calls and not store.query('SELECT * FROM practice_attempts')
 with pytest.raises(HTTPException):batch.view(sid,'wrong-session')


def test_one_small_model_call_atomic_results_and_idempotency(tmp_path):
 store,session,sid,service,batch,answers,evaluator=ready(tmp_path)
 result=asyncio.run(batch.submit(sid,session,answers,'submit_001'))
 assert len(result['items'])==3 and result['correct_count']==3
 assert result['evaluation_model']=='gemini-3.1-flash-lite'
 assert evaluator.calls==['BatchAssessment'] and service.provider.calls==['PracticeDraft','PracticeReview']
 for key in ['submit_001','submit_002']:
  assert asyncio.run(batch.submit(sid,session,list(reversed(answers)),key))==result
 assert len(evaluator.calls)==1
 assert store.progress(sid,session)['attempts']==3
 assert store.progress(sid,session)['exercises_completed']==3
 restored=PracticeBatch(PracticeService(PracticeStore(store.path),service.provider,evaluator))
 assert restored.view(sid,session)['result']==result
 changed=[answers[0].model_copy(update={'answer':'help'}),*answers[1:]]
 with pytest.raises(HTTPException):asyncio.run(batch.submit(sid,session,changed,'submit_001'))
 batch.save(sid,session,changed)
 assert batch.view(sid,session)['state']=='draft' and batch.view(sid,session)['result'] is None
 assert asyncio.run(batch.submit(sid,session,answers,'submit_003'))==result
 assert batch.view(sid,session)['result']==result and len(evaluator.calls)==1


def test_mcq_is_authoritative_even_if_model_approves_wrong_choice(tmp_path):
 _,session,sid,_,batch,answers,_=ready(tmp_path)
 answers[0]=answers[0].model_copy(update={'answer':'help'})
 result=asyncio.run(batch.submit(sid,session,answers,'submit_001'))
 assert result['items'][0]['outcome']=='incorrect' and result['correct_count']==2


@pytest.mark.parametrize('failure',['timeout','missing_item'])
def test_failed_batch_publishes_no_partial_results_or_progress(tmp_path,failure):
 store,session,sid,_,batch,answers,evaluator=ready(tmp_path)
 if failure=='timeout':evaluator.fail=ProviderError('timeout','Fixture timeout',504)
 else:evaluator.omit=True
 with pytest.raises(ProviderError):asyncio.run(batch.submit(sid,session,answers,'submit_001'))
 assert batch.view(sid,session)['state']=='failed'
 assert batch.view(sid,session)['result'] is None
 assert not store.query('SELECT * FROM answers')
 with pytest.raises(HTTPException):asyncio.run(batch.submit(sid,session,answers,'submit_001'))
 assert len(evaluator.calls)==1


def test_duplicate_concurrent_submit_makes_one_model_request(tmp_path):
 # Setup generation uses its own event loop; start the concurrent checks afterwards.
 _,session,sid,_,batch,answers,evaluator=ready(tmp_path)
 async def check():
  evaluator.wait=asyncio.Event()
  first=asyncio.create_task(batch.submit(sid,session,answers,'submit_001'))
  await asyncio.sleep(.02)
  with pytest.raises(HTTPException):await batch.submit(sid,session,answers,'submit_002')
  evaluator.wait.set();await first
 asyncio.run(check())
 assert evaluator.calls==['BatchAssessment']


def test_batch_http_frontend_contract(tmp_path):
 provider=BatchProvider()
 with TestClient(create_app(tmp_path/'data',tmp_path/'results',lambda _:provider)) as client:
  graded=client.post('/api/writing/task2/evaluate',json={'prompt':QUESTION,'essay':ESSAY}).json();sid=graded['submission_id']
  exercises=client.post(f'/api/writing/task2/{sid}/exercises').json()['exercises']
  answers=[{'exercise_id':e['exercise_id'],'answer':a} for e,a in zip(exercises,['helps','A useful website helps people learn.','A patient tutor helps beginners. Each learner has a notebook.'])]
  path=f'/api/writing/task2/{sid}/practice-attempt'
  assert client.put(path,json={'answers':answers[:1]}).status_code==200
  assert client.get(path).json()['result'] is None
  assert client.post(path+'/submit',json={'answers':answers[:1],'request_id':'submit_001'}).status_code==422
  response=client.post(path+'/submit',json={'answers':answers,'request_id':'submit_001'})
  assert response.status_code==200,response.text
  assert response.json()['total']==3
  assert client.get(path).json()['state']=='complete'
  client.cookies.clear()
  assert client.get(path).status_code==401
