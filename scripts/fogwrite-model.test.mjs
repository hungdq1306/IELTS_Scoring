import test from 'node:test';
import assert from 'node:assert/strict';
import {annotations,clock,topics,wordCount} from '../frontend/src/fogwrite-model.js';

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
test('timer formats zero, expiry and a full session; words support apostrophes',()=>{
 assert.equal(clock(2400),'40:00');assert.equal(clock(-10),'00:00');assert.equal(clock(65),'01:05');
 assert.equal(wordCount("Students' time isn't unlimited."),4);
 assert.equal(topics.length,12);assert.equal(new Set(topics.map(t=>t.prompt)).size,12);
});
