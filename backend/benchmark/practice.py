"""Separate practice-quality benchmark; never computes or modifies grading MAE/QWK."""
import argparse
import asyncio
import csv
import hashlib
import json
import random
from dataclasses import replace
from pathlib import Path
from app.config import ROOT,load_settings
from app.practice.store import PracticeStore
from app.practice.service import PracticeService
from app.providers.gemini import GeminiProvider
from app.providers.base import ProviderError
from benchmark import store
from benchmark.metrics import percentile

DEST=ROOT / 'results/practice_benchmark'

def prepare(max_samples):
 DEST.mkdir(exist_ok=True)
 target=DEST / 'manifest.json'
 if target.exists():
  data=json.loads(target.read_text())
  if data['requested_samples']!=max_samples:raise ValueError('Manifest already frozen with a different sample count.')
  return data
 records=[]
 for file,source in [('fs1-a551b6858d5fc278.sqlite3','Lexibot'),('fs1-7fece1548a9e8230.sqlite3','Writing9')]:
  path=ROOT / 'results' / file
  if not path.exists():continue
  meta,rows,_=store.read(path)
  valid=[r for r in rows if r.get('prediction')]
  random.Random(42).shuffle(valid)
  for r in valid:records.append((r,source,meta['run_id']))
 selected=[];seen=set()
 for row,source,run in records:
  key=hashlib.sha256(row['essay'].encode()).hexdigest()
  if key in seen:continue
  seen.add(key);selected.append((row,source,run))
  if len(selected)>=max_samples:break
 if not selected:raise ValueError('No cached real essay grades are available.')
 db=PracticeStore(ROOT / 'results/_practice.sqlite3');sid,_=db.new_session()
 cases=[]
 for row,source,run in selected:
  sub=db.create_submission(sid,row['prompt'],row['essay'],row['prediction'])
  cases.append({'submission_id':sub,'essay_id':row['essay_id'],'source':source,'cached_run':run})
 from app.practice.prompts import GENERATION_VERSION
 manifest={'version':GENERATION_VERSION,'seed':42,'requested_samples':max_samples,'session_id':sid,'cases':cases,
  'provenance':'Original essays with cached AI feedback; error annotations and exercise keys are NOT human ground truth.'}
 target.write_text(json.dumps(manifest,indent=2),encoding='utf-8');return manifest


async def benchmark(args):
 manifest=prepare(args.max_samples)
 settings=replace(load_settings(),retries=1,daily_budget=args.daily_budget,requests_per_minute=3,concurrency=1)
 provider=GeminiProvider(settings,generation_budget=args.request_budget)
 db=PracticeStore(ROOT / 'results/_practice.sqlite3');service=PracticeService(db,provider)
 try:
  for case in manifest['cases']:
   batch=db.batch(case['submission_id'])
   if batch and batch['state']=='ready':continue
   if batch and not args.retry_failures:continue
   try:
    result=await service.generate(case['submission_id'],manifest['session_id'])
    print(json.dumps({'essay':case['essay_id'],'source':case['source'],'exercises':len(result['exercises']),'state':result['state']}),flush=True)
   except ProviderError as e:
    print(json.dumps({'essay':case['essay_id'],'error':e.code}),flush=True)
    if e.code in {'request_budget','daily_quota','local_daily_budget','gemini_configuration','connection_error'}:break
   except Exception as e:
    print(json.dumps({'essay':case['essay_id'],'error':type(e).__name__,'detail':str(e)}),flush=True)
 finally:await provider.close()
 export()


def write_review(path,rows,fields):
 # Preserve lecturer-entered judgments on repeated exports.
 existing={}
 if path.exists():
  with path.open(encoding='utf-8',newline='') as f:
   for row in csv.DictReader(f):existing[row['review_id']]=row
 for row in rows:
  old=existing.get(row['review_id'],{})
  for field in fields:
   if old.get(field) not in (None,''):row[field]=old[field]
 with path.open('w',encoding='utf-8',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['review_id',*fields]);writer.writeheader();writer.writerows(rows)


def human_metrics(path,columns):
 if not path.exists():return {key:{'reviewed':0,'positive':0,'rate':None} for key in columns}
 with path.open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
 result={}
 for key in columns:
  values=[]
  for row in rows:
   val=(row.get(key) or '').strip().lower()
   if val in {'1','true','yes'}:values.append(True)
   elif val in {'0','false','no'}:values.append(False)
   elif val:raise ValueError(f'Invalid reviewer value in {key}; use 1/0 or blank')
  result[key]={'reviewed':len(values),'positive':sum(values),'rate':sum(values)/len(values) if values else None}
 return result


def export():
 target=DEST / 'manifest.json'
 if not target.exists():return
 manifest=json.loads(target.read_text());db=PracticeStore(ROOT / 'results/_practice.sqlite3')
 error_rows=[];exercise_rows=[];calls=[];published=0;ready=0;candidate_count=0;all_candidate_count=0;case_counts=[]
 for case in manifest['cases']:
  sid=case['submission_id'];sub=db.owned_submission(sid,manifest['session_id']);batch=db.batch(sid)
  data=batch['data'] if batch else {};pub=data.get('exercises',[]);published+=len(pub);ready+=bool(batch and batch['state']=='ready')
  case_counts.append({**case,'state':batch['state'] if batch else 'not_attempted','published':len(pub)})
  rawcalls=db.query('SELECT * FROM practice_calls WHERE submission_id=? ORDER BY created,rowid',(sid,))
  calls.extend([{**r,'meta':json.loads(r['metadata'])} for r in rawcalls])
  # Export latest generation candidate set; never overwrite completed human labels.
  drafts=[r for r in rawcalls if r['operation']=='generate' and json.loads(r['metadata'])['status']=='ok']
  all_candidate_count+=sum(len(json.loads(r['raw']).get('exercises',[])) for r in drafts)
  draft=json.loads(drafts[-1]['raw']) if drafts else {'errors':[],'exercises':[]};candidate_count+=len(draft['exercises'])
  errors={e['error_id']:e for e in draft['errors']}
  for e in draft['errors']:
   error_rows.append({'review_id':sid+':'+e['error_id'],'essay_id':case['essay_id'],'source':case['source'],'question':sub['prompt'],'essay':sub['essay'],
    'category':e['category'],'subtype':e['subtype'],'quote':e['original_quote'],'correction':e['suggested_correction'],'explanation':e['explanation'],
    'real_error':'','important_error':'','notes':''})
  for index,e in enumerate(draft['exercises']):
   er=errors.get(e['source_error_id'],{})
   exercise_rows.append({'review_id':sid+':'+str(index),'essay_id':case['essay_id'],'source':case['source'],
    'source_quote':er.get('original_quote',''),'source_error_explanation':er.get('explanation',''),'type':e['type'],'question':e['question'],
    'options':json.dumps(e['options']),'answer_key':e['correct_answer'],'explanation':e['explanation'],
    'automated_published':any(p['question']==e['question'] for p in pub),
    'valid_exercise':'','source_aligned':'','answer_key_correct':'','unambiguous':'','explanation_correct':'','difficulty_appropriate':'','useful_for_ielts':'','notes':''})
 if error_rows:write_review(DEST/'lecturer_errors.csv',error_rows,['real_error','important_error','notes'])
 if exercise_rows:write_review(DEST/'lecturer_exercises.csv',exercise_rows,['valid_exercise','source_aligned','answer_key_correct','unambiguous','explanation_correct','difficulty_appropriate','useful_for_ielts','notes'])
 elapsed=[c['meta'].get('elapsed_ms',0) for c in calls]
 attempts=[a for c in calls for a in c['meta'].get('attempts',[])]
 tokens=sum(c['meta'].get('usage',{}).get('total_token_count',0) for c in calls)
 summary={'essays_requested':len(manifest['cases']),'essays_ready':ready,'candidates_generated_latest':candidate_count,'candidates_generated_all_attempts':all_candidate_count,'published_after_automated_checks':published,
  'automated_generation_success_rate':published/all_candidate_count if all_candidate_count else None,
  'rejected_exercise_rate':(all_candidate_count-published)/all_candidate_count if all_candidate_count else None,
  'logical_calls':len(calls),'provider_attempts':len(attempts),'provider_failures':sum(a['status']!='ok' for a in attempts),
  'logical_api_failure_rate':sum(c['meta']['status']!='ok' for c in calls)/len(calls) if calls else None,
  'mean_call_latency_ms':sum(elapsed)/len(elapsed) if elapsed else None,'p95_call_latency_ms':percentile(elapsed,.95),'reported_tokens':tokens,
  'calls_per_essay':len(calls)/len(manifest['cases']) if manifest['cases'] else None,
  'human_error_precision':human_metrics(DEST/'lecturer_errors.csv',['real_error']),
  'human_exercise_metrics':human_metrics(DEST/'lecturer_exercises.csv',['valid_exercise','source_aligned','answer_key_correct','explanation_correct']),
  'cases':case_counts,'caveat':'Automated acceptance is NOT human exercise validity or learning effectiveness.'}
 (DEST/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in summary.items() if k!='cases'},indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--max-samples',type=int,default=20);parser.add_argument('--request-budget',type=int,default=50)
 parser.add_argument('--daily-budget',type=int,default=300);parser.add_argument('--retry-failures',action='store_true');parser.add_argument('--export-only',action='store_true')
 args=parser.parse_args()
 if args.max_samples<1 or args.request_budget<1:parser.error('Positive sample/request limits required')
 if args.export_only:export()
 else:asyncio.run(benchmark(args))
