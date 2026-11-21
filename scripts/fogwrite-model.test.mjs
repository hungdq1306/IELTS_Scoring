import test from 'node:test';
import assert from 'node:assert/strict';
import {annotations,annotationSegments,clock,topics,wordCount,normalizeDraft} from '../frontend/src/fogwrite-model.js';

test('grounding rejects missing or repeated quotes instead of highlighting arbitrary text',()=>{
 const result={grammar_corrections:[{original:'has',corrected:'have'}]};
 assert.equal(annotations(result,'has appeared and has returned').length,0);
 assert.equal(annotations(result,'nothing matches').length,0);
 assert.deepEqual(annotations(result,'students has')[0].start,9);
});
test('criterion filter excludes unrelated corrections and preserves neutral evidence',()=>{
 const result={grammar_corrections:[{original:'has'}],language_suggestions:[],criterion_feedback:{task_response:{evidence:[{quote:'more detail',explanation:'Develop the point.'}]}}};
 const list=annotations(result,'has more detail','task_response');
 assert.equal(list.length,1);assert.equal(list[0].kind,'evidence');
 assert.equal(list[0].quote,'more detail');
});

test('v2 sentence annotations feed grounded highlights and preserve criterion ownership',()=>{
 const sentence='Technology help students learn.';
 const result={sentence_annotations:[{criterion:'grammatical_range_accuracy',original_sentence:sentence,minimal_fix:'Technology helps students learn.',explanation:'Agreement',band_upgrade:'Use an accurate verb form.'}]};
 const marks=annotations(result,sentence,'grammatical_range_accuracy');
 assert.equal(marks.length,1);assert.equal(marks[0].kind,'error');assert.equal(marks[0].corrected,'Technology helps students learn.');
 assert.equal(annotations(result,sentence,'task_response').length,0);
 assert.equal(annotations(result,'A different essay.').length,0);
 const duplicate={...result,grammar_corrections:[{original:sentence,corrected:'Technology helps students learn.'}]};
 assert.equal(annotations(duplicate,sentence).filter(m=>m.kind==='error').length,1);
});
test('timer formats zero, expiry and a full session; words support apostrophes',()=>{
 assert.equal(clock(2400),'40:00');assert.equal(clock(-10),'00:00');assert.equal(clock(65),'01:05');
 assert.equal(wordCount("Students' time isn't unlimited."),4);
  assert.equal(wordCount("Students’ time isn’t unlimited."),4);
 assert.equal(topics.length,12);assert.equal(new Set(topics.map(t=>t.prompt)).size,12);
});

test('draft recovery tolerates invalid storage and retains valid timer consent',()=>{
  const blank=normalizeDraft(null);
  for(const value of [false,42,'invalid',[],{prompt:42,essay:{},started:'broken',finished:Infinity}]) {
    assert.deepEqual(normalizeDraft(value),blank);
  }
  assert.deepEqual(normalizeDraft({prompt:'Question',essay:'Draft',started:1000,finished:900,extraAllowed:true}),{
    ...blank,prompt:'Question',essay:'Draft',started:1000,extraAllowed:true,
  });
  assert.equal(normalizeDraft({started:1000,finished:2000}).finished,2000);
  assert.equal(normalizeDraft({extraAllowed:'true'}).extraAllowed,false);
});

test('grammar errors remain selectable inside longer criterion evidence',()=>{
 const essay='Many students has useful ideas.';
 const result={grammar_corrections:[{original:'students has'}],criterion_feedback:{task_response:{evidence:[{quote:essay,explanation:'A complete supporting point.'}]}}};
 const parts=annotationSegments(annotations(result,essay),essay.length);
 assert.equal(parts.map(p=>essay.slice(p.start,p.end)).join(''),essay);
 const error=parts.find(p=>p.mark?.kind==='error');
 assert.equal(essay.slice(error.start,error.end),'students has');
 assert.equal(parts.filter(p=>p.mark?.kind==='evidence').length,2);
});
