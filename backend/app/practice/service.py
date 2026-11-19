import asyncio
import json
import re
from time import perf_counter
from filelock import FileLock, Timeout
from fastapi import HTTPException
from pydantic import ValidationError
from app.providers.base import ProviderError
from app.practice.store import uid,now
from app.practice.schemas import PracticeDraft,PracticeReview,AnswerAssessment
from app.practice.diagnosis import normalize,verify_errors,prioritize,validate_exercise
from app.practice.prompts import GENERATOR,REVIEWER,ANSWER_EVALUATOR,GENERATION_VERSION,generation_input


class PracticeService:
 def __init__(self,store,provider):self.store,self.provider=store,provider

 def lock(self,resource):return FileLock(str(self.store.path.parent / ('practice-'+resource+'.lock')),timeout=0)

 async def call(self,sid,operation,system,data,schema):
  start=perf_counter()
  try:
   g=await self.provider.generate_structured(system,json.dumps(data,ensure_ascii=False) if not isinstance(data,str) else data,schema)
  except ProviderError as exc:
   self.store.log_call(sid,operation,exc.generation.raw if exc.generation else None,{'status':exc.code,'elapsed_ms':round((perf_counter()-start)*1000),'attempts':[a.model_dump() for a in exc.attempts]})
   raise
  metadata={'status':'ok','model':g.model,'model_version':g.version,'elapsed_ms':round((perf_counter()-start)*1000),
            'provider_latency_ms':g.latency_ms,'usage':g.usage,'attempts':[a.model_dump() for a in g.attempts],'version':GENERATION_VERSION}
  try:result=schema.model_validate_json(g.raw)
  except ValidationError as exc:
   metadata['status']='invalid_schema';self.store.log_call(sid,operation,g.raw,metadata)
   raise ProviderError('practice_invalid_schema','Gemini returned an invalid practice response. No unvalidated exercise was published.',502) from exc
  self.store.log_call(sid,operation,g.raw,metadata)
  return result

 def public(self,sid,session_id):
  self.store.owned_submission(sid,session_id);batch=self.store.batch(sid)
  if not batch:return {'submission_id':sid,'state':'not_generated','errors':[],'exercises':[],'exclusions':[],'message':'Generate optional practice from evidence in your essay.'}
  data=batch['data'];public_errors=[]
  for e in data.get('errors',[]):
   public_errors.append({k:e[k] for k in ('error_id','criterion','category','subtype','original_quote','paragraph_number','start','end','severity','evidence_verified','exercise_eligible','semantic_status','recurrence')})
   public_errors[-1]['explanation']='Evidence found in the student essay. Target skill: '+e['subtype'].replace('_',' ')+'. Automated review; not lecturer-verified.'
  public_ex=[]
  for e in data.get('exercises',[]):
   out={k:e[k] for k in ('exercise_id','source_error_id','type','skill','difficulty','instruction','question','options','learning_objective','validation_status')}
   answers=[r for r in self.store.answer_rows(e['exercise_id']) if r.get('state')=='complete']
   out.update(completed=any(r['result']['outcome']=='correct' for r in answers),attempts=len(answers),hint_used=bool(self.store.query('SELECT 1 FROM hints WHERE exercise_id=?',(e['exercise_id'],))))
   public_ex.append(out)
  # Exclusion reasons are server-controlled; never expose reviewer text or keys.
  exclusions=[{'kind':r.get('kind','exercise'),'reason':r['reason']} for r in data.get('exclusions',[])]
  return {'submission_id':sid,'state':batch['state'],'errors':public_errors,'exercises':public_ex,
          'exclusions':exclusions,'message':data.get('message','')}

 async def generate(self,sid,session_id):
  submission=self.store.owned_submission(sid,session_id)
  try:
   with self.lock(sid):
    batch=self.store.batch(sid)
    if batch and batch['state']=='ready':return self.public(sid,session_id)
    if batch and batch['state']=='generating':raise HTTPException(409,'Generation is already pending or was interrupted. It is not automatically rebilled; inspect the operation before resetting it.')
    count=batch['generations'] if batch else 0
    if count>=2:raise HTTPException(409,'The two-generation limit for this submission has been reached.')
    count+=1
    self.store.set_batch(sid,'generating',{'message':'Generating and reviewing evidence-grounded practice.'},count)
    try:
     # Prefer recognition for new learners; prior practice data permits only a modest stage adjustment.
     history=self.store.query("SELECT a.payload FROM answers a JOIN exercises e ON e.id=a.exercise_id JOIN submissions s ON s.id=e.submission_id WHERE s.session_id=?",(session_id,))
     successes=sum(json.loads(r['payload']).get('result',{}).get('outcome')=='correct' for r in history)
     preferred=2 if successes>=3 else 1
     draft=await self.call(sid,'generate',GENERATOR,generation_input(submission['prompt'],submission['essay'],submission['grade'],preferred),PracticeDraft)
     errors,mapping,excluded=verify_errors(draft.errors,submission['essay'],sid)
     if not errors:
      data={'errors':[],'exercises':[],'exclusions':excluded,'message':'No sufficiently grounded error was found. No mistakes were invented to fill practice slots.'}
      self.store.save_batch(sid,data,count);return self.public(sid,session_id)
     # One independent semantic review request. No unlimited regeneration loop.
     review=await self.call(sid,'review',REVIEWER,{'question':submission['prompt'],'essay':submission['essay'],'draft':draft.model_dump()},PracticeReview)
     from collections import Counter
     err_counts=Counter(r.error_id for r in review.errors);ex_counts=Counter(r.index for r in review.exercises)
     er={r.error_id:r for r in review.errors if err_counts[r.error_id]==1}
     judgments={r.index:r for r in review.exercises if ex_counts[r.index]==1}
     reverse={v:k for k,v in mapping.items()}
     for e in errors:
      judgment=er.get(reverse[e['error_id']]);valid=bool(judgment and judgment.real_error and (judgment.correction_valid or e['category'] in {'coherence','task_response'}))
      e.update(exercise_eligible=valid,semantic_status='machine_reviewed' if valid else 'review_required')
      if not valid:excluded.append({'kind':'error','source_id':e['error_id'],'reason':'automated semantic review did not approve the diagnosis'})
     selected=prioritize([e for e in errors if e['exercise_eligible']]);selected_ids={e['error_id'] for e in selected};lookup={e['error_id']:e for e in errors}
     exercises=[];seen=set()
     for index,ex in enumerate(draft.exercises):
      stable=mapping.get(ex.source_error_id);reason=[]
      if stable not in selected_ids:reason.append('source error is not approved and selected')
      else:reason+=validate_exercise(ex,lookup[stable],submission['essay'])
      judgment=judgments.get(index)
      flags=('aligned','answer_correct','unambiguous','explanation_correct','difficulty_appropriate','distractors_plausible','no_answer_leak','no_injection')
      if not judgment or not all(getattr(judgment,f) for f in flags):reason.append('automated semantic review did not approve the exercise')
      key=normalize(ex.question)
      if key in seen:reason.append('duplicate exercise question')
      if reason:
       excluded.append({'kind':'exercise','index':index,'reason':'; '.join(reason)});continue
      seen.add(key);item=ex.model_dump();item.update(exercise_id=uid('ex'),source_error_id=stable,validation_status='machine_reviewed_not_human_verified')
      exercises.append(item)
     exercises.sort(key=lambda e:(e['difficulty'],e['exercise_id']))
     data={'errors':errors,'exercises':exercises,'exclusions':excluded,
           'message':f'{len(exercises)} exercises passed structural checks and automated review. Keys and judgments still need lecturer validation.'}
     self.store.save_batch(sid,data,count)
    except BaseException:
     self.store.set_batch(sid,'failed',{'message':'Practice generation did not finish. Your essay and grade are preserved.'},count)
     raise
    return self.public(sid,session_id)
  except Timeout as exc:raise HTTPException(409,'Practice generation for this essay is already in progress.') from exc

 def hint(self,eid,session_id):
  sid,e=self.store.owned_exercise(eid,session_id)
  self.store.execute('INSERT OR IGNORE INTO hints VALUES (?,?)',(eid,now()))
  return {'exercise_id':eid,'hint':e['hint'],'human_reviewed':False}

 def deterministic(self,e,answer):
  if e['type']=='multiple_choice':return normalize(answer)==normalize(e['correct_answer'])
  if e['type']=='error_identification':
   target=re.findall(r"\w+",e['target_span'].casefold());tokens=re.findall(r"\w+",answer.casefold())
   return normalize(answer) in normalize(e['question']) and set(target)<=set(tokens) and len(target)<=len(tokens)<=len(target)+2
  keys=[e['correct_answer'],*e['accepted_alternatives']]
  norm=lambda t: normalize(t).rstrip('.!?')
  if any(norm(answer)==norm(k) for k in keys):return True
  return None

 async def answer(self,eid,session_id,answer,request_id):
  sid,e=self.store.owned_exercise(eid,session_id)
  try:
   with self.lock(eid):
    prior=self.store.query('SELECT payload FROM answers WHERE exercise_id=? AND request_id=?',(eid,request_id))
    if prior:
     previous=json.loads(prior[0]['payload'])
     if previous['answer']!=answer:raise HTTPException(409,'This request ID was already used with a different answer.')
     if previous['state']=='complete':return previous['result']
     raise HTTPException(409,'This answer request is pending or failed; no duplicate evaluation is made. Use a new request ID only after checking its status.')
    records=[r for r in self.store.answer_rows(eid) if r.get('state')=='complete']
    if records and normalize(records[-1]['answer'])==normalize(answer):return records[-1]['result']
    if len(records)>=5:raise HTTPException(409,'Five-answer limit reached for this exercise. Review the explanation before continuing.')
    aid=uid('attempt');record={'state':'pending','answer':answer}
    self.store.execute('INSERT INTO answers VALUES (?,?,?,?,?)',(aid,eid,request_id,json.dumps(record),now()))
    try:
     correct=self.deterministic(e,answer)
     if correct is not None:
      outcome='correct' if correct else 'incorrect'
      assessment=AnswerAssessment(outcome=outcome,explanation=e['explanation'],suggested_improvement=e['correct_answer'] if not correct else '',target_fixed=correct,meaning_preserved=correct,no_new_serious_errors=correct)
      evaluator='deterministic_key_match' if e['type'] not in {'multiple_choice','error_identification'} else 'deterministic'
     else:
      sub=self.store.owned_submission(sid,session_id)
      assessment=await self.call(sid,'answer',ANSWER_EVALUATOR,{'question':sub['prompt'],'exercise':e,'learner_answer':answer},AnswerAssessment)
      if assessment.outcome=='correct' and not (assessment.target_fixed and assessment.meaning_preserved and assessment.no_new_serious_errors):assessment.outcome='partially_correct'
      evaluator='gemini_automated'
     hinted=bool(self.store.query('SELECT 1 FROM hints WHERE exercise_id=?',(eid,)))
     result={'attempt_id':aid,'exercise_id':eid,**assessment.model_dump(),'evaluator':evaluator,'human_reviewed':False,
       'correct_answer':e['correct_answer'],'accepted_alternatives':e['accepted_alternatives'],'attempt_number':len(records)+1,'hint_used':hinted}
     record.update(state='complete',result=result)
    except BaseException:
     record['state']='failed';self.store.execute('UPDATE answers SET payload=? WHERE id=?',(json.dumps(record),aid));raise
    self.store.execute('UPDATE answers SET payload=? WHERE id=?',(json.dumps(record,ensure_ascii=False),aid))
    return result
  except Timeout as exc:raise HTTPException(409,'This exercise answer is already being checked.') from exc

 async def revision(self,sid,session_id,paragraph_number,answer,request_id):
  sub=self.store.owned_submission(sid,session_id)
  from app.grading.detailed import essay_paragraphs
  paragraphs=essay_paragraphs(sub['essay'])
  if paragraph_number>len(paragraphs):raise HTTPException(422,'Paragraph number does not exist.')
  batch=self.store.batch(sid)
  errors=[e for e in (batch['data'].get('errors',[]) if batch else []) if e['paragraph_number']==paragraph_number and e.get('exercise_eligible')]
  if not errors:raise HTTPException(409,'Generate practice first and choose a paragraph with an approved evidence-grounded weakness.')
  try:
   with self.lock(sid+'-revision'):
    previous=self.store.query('SELECT payload FROM revisions WHERE submission_id=? AND request_id=?',(sid,request_id))
    if previous:
     data=json.loads(previous[0]['payload'])
     if data.get('after')!=answer or data.get('paragraph_number')!=paragraph_number:raise HTTPException(409,'Revision request ID already used.')
     if data['state']=='complete':return data
     raise HTTPException(409,'Revision pending or failed; no duplicate model request is made.')
    completed=[json.loads(r['payload']) for r in self.store.query('SELECT payload FROM revisions WHERE submission_id=? ORDER BY created DESC,rowid DESC',(sid,))]
    if completed and completed[0].get('state')=='complete' and completed[0].get('after')==answer and completed[0].get('paragraph_number')==paragraph_number:return completed[0]
    if len(completed)>=5:raise HTTPException(409,'Revision request limit reached.')
    rid=uid('rev');data={'revision_id':rid,'state':'pending','paragraph_number':paragraph_number,'before':paragraphs[paragraph_number-1],'after':answer}
    self.store.execute('INSERT INTO revisions VALUES (?,?,?,?,?)',(rid,sid,request_id,json.dumps(data),now()))
    try:
     feedback=await self.call(sid,'revision',ANSWER_EVALUATOR,{'IELTS_question':sub['prompt'],'original_paragraph':data['before'],'weaknesses':errors,'revised_paragraph':answer},AnswerAssessment)
     if feedback.outcome=='correct' and not (feedback.target_fixed and feedback.meaning_preserved and feedback.no_new_serious_errors):feedback.outcome='partially_correct'
     data.update(state='complete',feedback=feedback.model_dump(),evaluator='gemini_automated',human_reviewed=False,completed_at=now())
    except BaseException:
     data['state']='failed';self.store.execute('UPDATE revisions SET payload=? WHERE id=?',(json.dumps(data),rid));raise
    self.store.execute('UPDATE revisions SET payload=? WHERE id=?',(json.dumps(data,ensure_ascii=False),rid))
    return data
  except Timeout as exc:raise HTTPException(409,'A paragraph revision is already being checked.') from exc
