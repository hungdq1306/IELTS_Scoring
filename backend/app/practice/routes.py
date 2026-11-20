from fastapi import HTTPException,Request
from app.practice.schemas import PracticeResponse,AnswerRequest,AnswerResponse,RevisionRequest,ProgressResponse
from app.practice.schemas import PracticeAnswers,PracticeSubmit,PracticeAttemptResponse,PracticeSubmitResponse
from app.practice.batch import PracticeBatch

COOKIE='ielts_practice_session'

def install_routes(app):
 def context(request):
  service=request.app.state.practice
  session_id=service.store.session(request.cookies.get(COOKIE))
  if not session_id:raise HTTPException(401,'This browser session has expired. Grade an essay to start a new session.')
  return service,session_id

 @app.get('/api/practice/submissions')
 def submissions(request:Request):
  service=request.app.state.practice;session_id=service.store.session(request.cookies.get(COOKIE))
  if not session_id:return {'items':[]}
  rows=service.store.query('SELECT id,payload,created FROM submissions WHERE session_id=? ORDER BY created DESC,rowid DESC LIMIT 30',(session_id,))
  import json
  return {'items':[{'submission_id':r['id'],'prompt':json.loads(r['payload'])['prompt'],'created':r['created']} for r in rows]}

 @app.get('/api/writing/task2/{submission_id}/practice-attempt',response_model=PracticeAttemptResponse)
 def practice_attempt(submission_id:str,request:Request):
  service,sid=context(request)
  return PracticeBatch(service).view(submission_id,sid)

 @app.put('/api/writing/task2/{submission_id}/practice-attempt')
 def save_practice_attempt(submission_id:str,body:PracticeAnswers,request:Request):
  service,sid=context(request)
  return PracticeBatch(service).save(submission_id,sid,body.answers)

 @app.post('/api/writing/task2/{submission_id}/practice-attempt/submit',response_model=PracticeSubmitResponse)
 async def submit_practice_attempt(submission_id:str,body:PracticeSubmit,request:Request):
  service,sid=context(request)
  return await PracticeBatch(service).submit(submission_id,sid,body.answers,body.request_id)

 @app.get('/api/writing/task2/{submission_id}/submission')
 def submission(submission_id:str,request:Request):
  service,sid=context(request)
  return {'submission_id':submission_id,**service.store.owned_submission(submission_id,sid)}

 @app.post('/api/writing/task2/{submission_id}/exercises',response_model=PracticeResponse)
 async def generate(submission_id:str,request:Request):
  service,sid=context(request)
  return await service.generate(submission_id,sid)

 @app.get('/api/writing/task2/{submission_id}/exercises',response_model=PracticeResponse)
 def exercises(submission_id:str,request:Request):
  service,sid=context(request)
  return service.public(submission_id,sid)

 @app.post('/api/exercises/{exercise_id}/answer',response_model=AnswerResponse)
 async def answer(exercise_id:str,body:AnswerRequest,request:Request):
  service,sid=context(request)
  return await service.answer(exercise_id,sid,body.answer,body.request_id)

 @app.get('/api/exercises/{exercise_id}/feedback',response_model=AnswerResponse)
 def last_feedback(exercise_id:str,request:Request):
  service,sid=context(request)
  _,exercise=service.store.owned_exercise(exercise_id,sid)
  records=[r for r in service.store.answer_rows(exercise_id) if r.get('state')=='complete']
  if not records:raise HTTPException(404,'No answer has been submitted yet.')
  return service.answer_view(exercise,records[-1]['result'])

 @app.post('/api/exercises/{exercise_id}/hint')
 def hint(exercise_id:str,request:Request):
  service,sid=context(request)
  return service.hint(exercise_id,sid)

 @app.post('/api/writing/task2/{submission_id}/revision')
 async def revision(submission_id:str,body:RevisionRequest,request:Request):
  service,sid=context(request)
  return await service.revision(submission_id,sid,body.paragraph_number,body.answer,body.request_id)

 @app.get('/api/writing/task2/{submission_id}/progress',response_model=ProgressResponse)
 def progress(submission_id:str,request:Request):
  service,sid=context(request)
  return service.store.progress(submission_id,sid)
