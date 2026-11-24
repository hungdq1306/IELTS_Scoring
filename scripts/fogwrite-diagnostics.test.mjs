import test from 'node:test';
import assert from 'node:assert/strict';
import {diagnosticItems} from '../frontend/src/diagnostics-model.js';
test('diagnostics prioritize low scores and preserve structured Vietnamese evidence',()=>{
 const rows=diagnosticItems([{aspect_name:'Depth of Ideas',score:5.5,strength_vi:'Phù hợp.',weakness_vi:'Thiếu ví dụ.'},{aspect_name:'Clarity of Position',score:8,strength_vi:'Rõ.',weakness_vi:'Chưa nhất quán.'}], 'task_response',7.5);
 assert.equal(rows[0].score,5.5);assert.equal(rows[0].needsWork,true);assert.equal(rows[1].needsWork,false);assert.equal(rows[0].weakness,'Thiếu ví dụ.');
});
test('legacy records render their original explanation without fabricated strengths or gaps',()=>{
 const rows=diagnosticItems([{aspect:'Depth of Ideas',score:6,explanation:'Original feedback.'},null,{aspect:'Unknown',score:7}], 'task_response',6);
 assert.equal(rows.length,1);assert.equal(rows[0].legacy,'Original feedback.');assert.equal(rows[0].strength,null);assert.equal(diagnosticItems('old string','task_response',6).length,0);
});

test('display ceiling follows calibrated or teacher-reviewed parent bands and retains the model proposal',()=>{
 const row=diagnosticItems([{aspect_name:'Depth of Ideas',score:8,strength_vi:'Rõ.',weakness_vi:'Thiếu ví dụ.'}],'task_response',6)[0];
 assert.equal(row.score,6.5);assert.equal(row.raw_score,8);assert.equal(row.needsWork,true);
});
