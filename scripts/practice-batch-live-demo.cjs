// Real backend/browser demo. Context is prepared from real Gemini grade/generation calls.
// This script never intercepts API responses and never reads backend answer keys.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'.cache/practice-batch-demo');
const data=JSON.parse(fs.readFileSync(path.join(out,'context.json'),'utf8'));
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.FOGWRITE_BASE_URL||'http://127.0.0.1:8000';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});await context.addCookies(data.cookies);
  const prior=await (await context.request.get(base+`/api/writing/task2/${data.submission_id}/practice-attempt`)).json();
  const replay=(await context.request.get(base+`/api/exercises/${data.batch.exercises[0].exercise_id}/feedback`)).ok();
  if(replay)await context.request.put(base+`/api/writing/task2/${data.submission_id}/practice-attempt`,{data:{answers:[]}});
  const page=await context.newPage();page.setDefaultTimeout(20000);const errors=[];let batchCalls=0,individualCalls=0;
  page.on('dialog',dialog=>dialog.accept());
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/practice-attempt/submit'))batchCalls++;if(r.method()==='POST'&&r.url().endsWith('/answer'))individualCalls++;});
  await page.goto(base+'/history');await page.getByRole('button').filter({hasText:data.prompt}).click();
  await page.getByRole('heading',{name:'Your writing, clearer.'}).waitFor();
  await page.screenshot({path:path.join(out,'01-real-assessment.png'),fullPage:true});
  await page.getByRole('button',{name:'Practise priority skills'}).click();
  await page.getByRole('button',{name:'Submit all responses'}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Check answer',exact:true}).count(),0);
  const submit=page.getByRole('button',{name:'Submit all responses',exact:true});
  assert.equal(await submit.isDisabled(),true);
  for(let i=0;i<data.batch.exercises.length;i++){
   const e=data.batch.exercises[i],answer=data.learner_answers[e.exercise_id];
   if(e.type==='multiple_choice')await page.getByRole('radio',{name:answer,exact:true}).check();
   else await page.locator('.exercise-editor textarea').fill(answer);
   if(i<data.batch.exercises.length-1){
    assert.equal(await submit.isDisabled(),true);
    await page.getByRole('button',{name:'Next exercise',exact:true}).click();
    await page.getByRole('heading',{name:data.batch.exercises[i+1].instruction,exact:true}).waitFor();
   }
  }
  assert.equal(await submit.isEnabled(),true);
  await page.getByRole('button',{name:'Save responses',exact:true}).click();
  const before=await context.request.get(base+`/api/writing/task2/${data.submission_id}/practice-attempt`);
  const draft=await before.json();assert.equal(draft.answers.length,data.batch.exercises.length);
  // A replay may restore the already-graded identical responses; a first attempt must have no feedback.
  if(!replay)assert.equal(draft.result,null);assert.equal(individualCalls,0);assert.equal(batchCalls,0);
  await page.screenshot({path:path.join(out,'02-all-responses-before-submit.png'),fullPage:true});
  const responsePromise=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/practice-attempt/submit'),{timeout:180000});
  const started=Date.now();await submit.click();const response=await responsePromise;const result=await response.json();const responseLatency=Date.now()-started;
  assert.equal(response.ok(),true,JSON.stringify(result));assert.equal(result.evaluation_model,'gemini-3.1-flash-lite');
  await page.getByRole('heading',{name:/Practice results:/}).waitFor();
  assert.equal(batchCalls,1);assert.equal(individualCalls,0);assert.equal(result.total,data.batch.exercises.length);
  await page.screenshot({path:path.join(out,'03-real-batch-results.png'),fullPage:true});
  const repeated=await context.request.post(base+`/api/writing/task2/${data.submission_id}/practice-attempt/submit`,{data:{answers:data.batch.exercises.map(e=>({exercise_id:e.exercise_id,answer:data.learner_answers[e.exercise_id]})),request_id:'demo_replay_001'}});
  assert.equal((await repeated.json()).attempt_id,result.attempt_id);
  await page.goto(base+'/history');await page.getByRole('button').filter({hasText:data.prompt}).click();
  await page.getByRole('button',{name:'Practise priority skills'}).click();await page.getByRole('heading',{name:/Practice results:/}).waitFor();
  assert.deepEqual(errors,[]);
  const report={mode:'REAL_GEMINI',submission_id:data.submission_id,evaluation_model:result.evaluation_model,
    exercises:result.total,correct_count:result.correct_count,batch_browser_posts:batchCalls,individual_answer_posts:individualCalls,
    browser_submission_latency_ms:responseLatency,scoring_reused_existing_result:replay,result,idempotent_replay:true,results_restored_after_navigation:true,browser_errors:errors};
  fs.writeFileSync(path.join(out,'live-demo-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(String(e.stack).slice(0,1800));process.exitCode=1;});
