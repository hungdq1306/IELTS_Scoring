// Browser contract fixture only: no live Clerk accounts or Gemini calls.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base='http://localhost:4719';
const essay='Cities need reliable public transport because many residents depend on buses to reach work. Frequent services reduce waiting times and make journeys more predictable. Governments should also maintain safe walking routes around stations. This approach gives people a practical alternative to driving and can reduce congestion in busy neighbourhoods. Clear information about routes helps new passengers travel confidently while affordable tickets support families.';
const keys=['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'];
const grade={submission_id:'fixture-submission',estimated_overall_band:6.5,word_count:71,
 criterion_scores:Object.fromEntries(keys.map(key=>[key,6.5])),
 criterion_feedback:Object.fromEntries(keys.map(key=>[key,{explanation:'Clear argument; add a concrete example.',strengths:['Clear position.'],weaknesses:['Extend the example.'],evidence:[]}])),
 grammar_corrections:[],priority_improvements:['Develop specific examples.'],validation_warnings:[],paragraph_reviews:[],language_suggestions:[],aspect_reviews:[]};
(async()=>{
 const browser=await chromium.launch({headless:true,timeout:8000,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  page.setDefaultTimeout(5000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let joined=false,polls=0,submitted=0;
  await context.route('https://fonts.googleapis.com/**',r=>r.abort());
  await context.route('https://clerk.fixture.test/**',route=>route.fulfill({headers:{'access-control-allow-origin':'*'},contentType:'application/javascript',body:route.request().url().includes('/ui@')?'window.__internal_ClerkUICtor=function(){};':`
   window.__listeners=[];window.__tokens=0;
   window.Clerk={user:null,session:null,load:async()=>{},addListener(fn){window.__listeners.push(fn);fn({});return()=>{};},
    openSignIn(){this.user={id:'user_browser'};this.session={getToken:async()=>{window.__tokens++;return 'fixture-token';}};window.__listeners.forEach(fn=>fn({}));},signOut:async()=>{}};
  `}));
  await context.route(base+'/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname;
   if(p==='/api/auth/config')return route.fulfill({json:{mode:'clerk',issuer:'https://clerk.fixture.test',publishable_key:'pk_test_fixture',privacy_version:'fixture',retention_days:30,gemini_data_policy:'free_product_improvement'}});
   if(p.startsWith('/api/')){
    assert.equal(request.headers().authorization,'Bearer fixture-token');
    if(p==='/api/auth/me')return route.fulfill({json:{id:'fixture-user',role:'student',consent_version:joined?'fixture':null,classes:joined?[{id:'fixture-class',name:'YP03',role:'student'}]:[]}});
    if(p==='/api/classes/join'){assert.equal(request.postDataJSON().adult_confirmed,true);joined=true;return route.fulfill({json:{id:'fixture-class',name:'YP03'}});}
    if(p==='/api/writing/task2/evaluate'){
     assert.equal(request.postDataJSON().essay,essay);assert.match(request.headers()['idempotency-key'],/^[\w-]{8,}$/);submitted++;
     return route.fulfill({status:202,json:{submission_id:'fixture-submission',job_id:'fixture-job',status:'QUEUED',poll_url:'/api/jobs/fixture-job'}});
    }
    if(p==='/api/jobs/fixture-job'){polls++;return route.fulfill({json:{status:polls===1?'RUNNING':'COMPLETED',queue_position:null,result:polls===1?null:grade}});}
    if(p==='/api/practice/submissions')return route.fulfill({json:{items:[]}});
    return route.fulfill({status:404,json:{detail:'Not found'}});
   }
   const asset=/\.(js|css|png)$/.test(p),file=path.join(root,'frontend/dist',asset?p.slice(1):'index.html');
   if(!fs.existsSync(file))return route.fulfill({status:404,body:''});
   return route.fulfill({path:file,contentType:file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':file.endsWith('.png')?'image/png':'text/html'});
  });
  // History may probe before a session exists; return the real API's 401 in that case.
  await context.route(base+'/api/**',async route=>{
   if(route.request().url().endsWith('/auth/config')||route.request().headers().authorization)return route.fallback();
   return route.fulfill({status:401,json:{detail:'Sign in'}});
  });
  await page.goto(base);
  await page.locator('#pilot-account-root').getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByLabel('I am 18 or older and accept the pilot privacy conditions.').check();
  await page.getByLabel('Teacher invite code').fill('fixture-invite-code-long-enough');
  await page.getByRole('button',{name:'Join class',exact:true}).click();
  await page.locator('#pilot-account-root').getByText('YP03',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Check my essay',exact:true}).click();
  await page.getByLabel('Task question').fill('How should a city improve everyday transport for its residents?');
  await page.locator('#essay').fill(essay);
  await page.getByRole('button',{name:'Submit essay',exact:true}).click();
  await page.getByRole('button',{name:'Assess my essay',exact:true}).click();
  await page.locator('#pilot-account-root').getByRole('status').waitFor();
  await page.getByRole('heading',{name:'Your writing, clearer.'}).waitFor();
  assert.equal(submitted,1);assert.equal(polls,2);assert.ok(await page.evaluate(()=>window.__tokens)>=3);
  assert.deepEqual(errors,[]);
  console.log('PASS: Clerk SDK contract, login, consent/join, bearer headers, idempotency, 202 polling, token refresh and grading UI.');
 }finally{await browser.close();}
})().catch(error=>{console.error(String(error.stack||error).slice(0,2500));process.exitCode=1;});
