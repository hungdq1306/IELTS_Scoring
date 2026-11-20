"""Deterministic evidence ownership and prioritization; no band-based selection."""
import hashlib
import re
from collections import Counter
from app.grading.detailed import essay_paragraphs
from app.practice.schemas import TAXONOMY,CRITERION


def normalize(text):
 return " ".join(text.casefold().split())


def evidence_location(essay,quote,paragraph_number):
 paragraphs=essay_paragraphs(essay)
 if paragraph_number>len(paragraphs): return None
 paragraph=paragraphs[paragraph_number-1]
 if paragraph.count(quote)!=1:return None
 # Locate paragraphs sequentially, preserving original essay offsets.
 cursor=0
 for index,p in enumerate(paragraphs):
  start=essay.find(p,cursor);cursor=start+len(p)
  if index+1==paragraph_number:return start+paragraph.index(quote)
 return None


def verify_errors(drafts,essay,submission_id):
 verified=[];rejected=[];seen=set();mapping={};ids=Counter(e.error_id for e in drafts)
 for error in drafts:
  e=error.model_dump();reason=None
  if ids[e['error_id']]!=1:reason='duplicate model error_id'
  elif e['subtype'] not in TAXONOMY[e['category']] or e['criterion']!=CRITERION[e['category']]:reason='taxonomy mismatch'
  elif e['optional_style']:reason='optional style is not a definite error'
  elif e['suggested_correction'] and normalize(e['suggested_correction'])==normalize(e['original_quote']):reason='no meaningful correction'
  start=evidence_location(essay,e['original_quote'],e['paragraph_number'])
  if start is None:reason=reason or 'missing or ambiguous student evidence'
  key=(start,e['subtype'])
  if key in seen:reason=reason or 'duplicate evidence and subtype'
  if reason:
   rejected.append({'kind':'error','source_id':e['error_id'],'reason':reason});continue
  seen.add(key)
  stable='err_'+hashlib.sha256(f"{submission_id}:{start}:{e['subtype']}".encode()).hexdigest()[:24]
  mapping[e['error_id']]=stable
  e.update(error_id=stable,start=start,end=start+len(e['original_quote']),evidence_verified=True,
           exercise_eligible=False,semantic_status='candidate_not_human_verified')
  verified.append(e)
 counts=Counter(e['subtype'] for e in verified)
 for e in verified:e['recurrence']=counts[e['subtype']]
 return verified,mapping,rejected


def prioritize(errors):
 return sorted(errors,key=lambda e: (-({'high':3,'medium':2,'low':1}[e['severity']]+min(3,e['recurrence'])),e['start'],e['error_id']))[:5]


def cached_seeds(grade,essay):
 # Suggestions are optional style; they are never converted to grammar diagnoses.
 return [r for r in grade.get('grammar_corrections',[]) if r.get('original') and r['original'] in essay and r['original']!=r.get('corrected')]


def validate_exercise(ex,error,essay):
 issues=[]
 if ex.skill!=error['subtype']:issues.append('skill does not match source error')
 expected={'multiple_choice':1,'error_identification':1,'sentence_correction':2,'sentence_rewriting':3,'paragraph_revision':4,'error_imitation':4}
 if ex.difficulty!=expected[ex.type]:issues.append('scaffolding level does not match type')
 discourse=error['category'] in {'coherence','task_response'}
 if discourse and ex.type!='paragraph_revision':issues.append('discourse issues require paragraph revision')
 if ex.type=='multiple_choice':
  if not 3<=len(ex.options)<=4:issues.append('MCQ needs 3-4 options')
  if len({normalize(o) for o in ex.options})!=len(ex.options):issues.append('duplicate MCQ options')
  if ex.options.count(ex.correct_answer)!=1:issues.append('MCQ key must be exactly one option')
 elif ex.options:issues.append('non-MCQ options must be empty')
 if ex.type=='error_identification':
  if not ex.target_span or ex.question.count(ex.target_span)!=1:issues.append('identification target must be unique in question')
  if normalize(ex.correct_answer)!=normalize(ex.target_span):issues.append('identification key must match target span')
 if ex.type not in {'multiple_choice','error_identification'} and not ex.evaluation_rubric:issues.append('missing free-text rubric')
 if ex.structure_prompt:
  if ex.type!='sentence_rewriting':issues.append('structure scaffolds are for rewriting only')
  if normalize(ex.structure_prompt)==normalize(ex.correct_answer) or (len(ex.correct_answer)>20 and normalize(ex.correct_answer) in normalize(ex.structure_prompt)):
   issues.append('structure scaffold reveals reference answer')
 if ex.type=='paragraph_revision':
  p=essay_paragraphs(essay)[error['paragraph_number']-1]
  if ex.question!=p:issues.append('paragraph revision must use original paragraph')
 elif normalize(ex.question) in normalize(essay) or normalize(ex.question)==normalize(error['original_quote']):
  issues.append('practice must use a new context')
 if re.search(r'ignore (?:all |previous |system )?instructions|system prompt|api.?key|correct answer is',ex.question+' '+ex.instruction+' '+ex.structure_prompt,re.I):issues.append('instruction injection or answer leakage')
 return issues
