import hashlib
import json
import secrets
from time import time
from uuid import uuid4
from fastapi import HTTPException
from benchmark.store import connect


def uid(prefix):return prefix+'_'+uuid4().hex

def now():return int(time())

class PracticeStore:
 def __init__(self,path):
  self.path=path;path.parent.mkdir(parents=True,exist_ok=True)
  with connect(path) as db:
   db.executescript("""
   CREATE TABLE IF NOT EXISTS practice_sessions(id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, created INTEGER, expires INTEGER);
   CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, payload TEXT NOT NULL, created INTEGER);
   CREATE TABLE IF NOT EXISTS practice_batches(submission_id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, generations INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS exercises(id TEXT PRIMARY KEY, submission_id TEXT NOT NULL, payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS answers(id TEXT PRIMARY KEY, exercise_id TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, created INTEGER, UNIQUE(exercise_id,request_id));
   CREATE TABLE IF NOT EXISTS hints(exercise_id TEXT PRIMARY KEY, created INTEGER);
   CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY, submission_id TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, created INTEGER, UNIQUE(submission_id,request_id));
   CREATE TABLE IF NOT EXISTS practice_calls(id TEXT PRIMARY KEY, submission_id TEXT NOT NULL, operation TEXT NOT NULL, raw TEXT, metadata TEXT NOT NULL, created INTEGER);
   CREATE TABLE IF NOT EXISTS study_observations(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, study_id TEXT, group_label TEXT CHECK(group_label IN ('feedback_only','feedback_plus_practice')), phase TEXT CHECK(phase IN ('pre_test','mid_test','post_test','transfer','delayed')), assessment_ref TEXT, recorded INTEGER);
   """)

 def query(self,sql,args=()):
  with connect(self.path) as db:
   db.row_factory=__import__('sqlite3').Row
   return [dict(r) for r in db.execute(sql,args)]

 def execute(self,sql,args=()):
  with connect(self.path) as db:db.execute(sql,args)

 def new_session(self):
  token=secrets.token_urlsafe(32);sid=uid('ses')
  self.execute('INSERT INTO practice_sessions VALUES (?,?,?,?)',(sid,hashlib.sha256(token.encode()).hexdigest(),now(),now()+60*60*24*30))
  return sid,token

 def session(self,token):
  if not token:return None
  rows=self.query('SELECT id FROM practice_sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),now()))
  return rows[0]['id'] if rows else None

 def create_submission(self,session_id,prompt,essay,grade):
  sid=uid('sub');data={'prompt':prompt,'essay':essay,'grade':grade}
  self.execute('INSERT INTO submissions VALUES (?,?,?,?)',(sid,session_id,json.dumps(data,ensure_ascii=False),now()))
  return sid

 def owned_submission(self,sid,session_id):
  rows=self.query('SELECT * FROM submissions WHERE id=? AND session_id=?',(sid,session_id))
  if not rows:raise HTTPException(404,'Submission not found for this session.')
  return json.loads(rows[0]['payload'])

 def owned_exercise(self,eid,session_id):
  rows=self.query('SELECT e.* FROM exercises e JOIN submissions s ON e.submission_id=s.id WHERE e.id=? AND s.session_id=?',(eid,session_id))
  if not rows:raise HTTPException(404,'Exercise not found for this session.')
  return rows[0]['submission_id'],json.loads(rows[0]['payload'])

 def batch(self,sid):
  rows=self.query('SELECT * FROM practice_batches WHERE submission_id=?',(sid,))
  return {**rows[0],'data':json.loads(rows[0]['payload'])} if rows else None

 def set_batch(self,sid,state,data,generations):
  self.execute('INSERT INTO practice_batches VALUES (?,?,?,?) ON CONFLICT(submission_id) DO UPDATE SET payload=excluded.payload,state=excluded.state,generations=excluded.generations',
               (sid,json.dumps(data,ensure_ascii=False),state,generations))

 def save_batch(self,sid,data,generations):
  with connect(self.path) as db:
   for e in data['exercises']:db.execute('INSERT INTO exercises VALUES (?,?,?)',(e['exercise_id'],sid,json.dumps(e,ensure_ascii=False)))
   db.execute('UPDATE practice_batches SET payload=?,state=?,generations=? WHERE submission_id=?',(json.dumps(data,ensure_ascii=False),'ready',generations,sid))

 def log_call(self,sid,operation,raw,metadata):
  self.execute('INSERT INTO practice_calls VALUES (?,?,?,?,?,?)',(uid('call'),sid,operation,raw,json.dumps(metadata),now()))

 def answer_rows(self,eid):
  return [json.loads(r['payload']) for r in self.query('SELECT payload FROM answers WHERE exercise_id=? ORDER BY created,rowid',(eid,))]

 def progress(self,sid,session_id):
  self.owned_submission(sid,session_id)
  batch=self.batch(sid);data=batch['data'] if batch else {'errors':[],'exercises':[]}
  exercises=data.get('exercises',[]);records={e['exercise_id']:self.answer_rows(e['exercise_id']) for e in exercises}
  records={eid:[r for r in rs if r.get('state')=='complete'] for eid,rs in records.items()}
  done={eid for eid,rs in records.items() if any(r['result']['outcome']=='correct' for r in rs)}
  first=[rs[0] for rs in records.values() if rs];unassisted=[r for r in first if not r['result']['hint_used']]
  practiced={e['skill'] for e in exercises if records.get(e['exercise_id'])}
  revisions=[json.loads(r['payload']) for r in self.query('SELECT payload FROM revisions WHERE submission_id=? ORDER BY created,rowid',(sid,))]
  from collections import Counter
  error_counts=Counter(e['category'] for e in data.get('errors',[]) if e.get('exercise_eligible'))
  patterns=Counter(e['subtype'] for e in data.get('errors',[]) if e.get('exercise_eligible'))
  corrected={e['source_error_id'] for e in exercises if e['exercise_id'] in done}
  return {'submission_id':sid,'exercises_total':len(exercises),'exercises_completed':len(done),
   'attempts':sum(len(r) for r in records.values()),'first_attempt_accuracy':sum(r['result']['outcome']=='correct' for r in first)/len(first) if first else None,
   'unassisted_first_attempt_accuracy':sum(r['result']['outcome']=='correct' for r in unassisted)/len(unassisted) if unassisted else None,
   'hints_used':sum(bool(self.query('SELECT 1 FROM hints WHERE exercise_id=?',(e['exercise_id'],))) for e in exercises),
   'skills_practiced':sorted(practiced),'common_error_categories':dict(error_counts),'repeated_error_patterns':{k:v for k,v in patterns.items() if v>1},
   'skills_requiring_practice':sorted({e['skill'] for e in exercises if e['exercise_id'] not in done}),
   'errors_successfully_corrected':len(corrected),'revisions':[{k:v for k,v in r.items() if k not in ('raw',)} for r in revisions if r.get('state')=='complete'],
   'caveat':'Practice outcomes are automatically evaluated, not human-reviewed proficiency or IELTS band gains.'}
