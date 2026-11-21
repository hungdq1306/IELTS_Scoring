const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const {chromium}=require(require.resolve(process.env.PLAYWRIGHT_MODULE||'playwright',{paths:[path.join(root,'frontend/node_modules')]}));
const base=process.env.FOGWRITE_BASE_URL||'http://127.0.0.1:8000';
const out=path.resolve(root,process.env.FOGWRITE_SCREENSHOT_DIR||'.cache/ui-checks');
fs.mkdirSync(out,{recursive:true});
const essay='In my opinion, universities should balance practical skills and academic knowledge.\n\nAcademic study helps students understand important principles. Many students has difficulty finding practical opportunities.\n\nUniversities can improve their courses to meet the needs of the job market.';
const keys=['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'];
const grade={submission_id:'ui-contract',estimated_overall_band:6.5,word_count:47,criterion_scores:Object.fromEntries(keys.map(k=>[k,6.5])),criterion_feedback:Object.fromEntries(keys.map(k=>[k,{explanation:'Develop the supporting point.',strengths:['A clear position.'],weaknesses:['Add an example.'],evidence:[]}])),grammar_corrections:[{original:'students has',corrected:'students have',explanation:'Plural subject needs a plural verb.'}],priority_improvements:['Check subject-verb agreement.'],validation_warnings:[],paragraph_reviews:[],language_suggestions:[],aspect_reviews:[]};
(async()=>{
 let browser;
 try{
  browser=await chromium.launch({headless:true,timeout:10000,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
  for(const viewport of [{width:1440,height:900},{width:1280,height:800}]){
   const context=await browser.newContext({viewport});const page=await context.newPage();page.setDefaultTimeout(10000);const failures=[];
   page.on('pageerror',e=>failures.push(e.message));
   if(process.env.FOGWRITE_OFFLINE_TEST||process.argv.includes('--offline')){await context.route(base+'/**',async route=>{const url=new URL(route.request().url());if(url.pathname.startsWith('/api/'))return route.fulfill({json:url.pathname==='/api/auth/config'?{mode:'demo'}:{items:[]}});const asset=/\.(js|css|png)$/.test(url.pathname);const file=path.join(root,'frontend/dist',asset?url.pathname.slice(1):'index.html');if(!fs.existsSync(file))return route.fulfill({status:404,body:''});return route.fulfill({path:file,contentType:file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':file.endsWith('.png')?'image/png':'text/html'});});await context.route('https://fonts.googleapis.com/**',r=>r.abort());}
   async function capture(name){await page.waitForFunction(()=>Array.from(document.images).every(img=>img.complete));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name}: horizontal overflow`);assert.equal(await page.locator('img[data-mascot]').evaluateAll(imgs=>imgs.every(img=>img.naturalWidth>0)),true,`${name}: missing image`);assert.equal(await page.locator('img[data-mascot]').evaluateAll(imgs=>imgs.every(img=>{const r=img.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})),true,`${name}: clipped mascot`);await page.screenshot({path:path.join(out,`${viewport.width}-${name}.png`),fullPage:true});}
   await page.goto(base);await page.getByRole('heading',{name:'Small steps. Stronger writing.'}).waitFor();await capture('01-landing');
   await page.route('**/mascots/frog-writing.png',r=>r.fulfill({status:404,body:''}));await page.reload();await page.locator('[data-mascot-placeholder="writing"]').waitFor();assert.equal(await page.locator('[data-mascot-placeholder="writing"] svg').count(),0);await page.unroute('**/mascots/frog-writing.png');await page.reload();
   await page.getByRole('button',{name:'Start 40-minute practice'}).click();await page.getByRole('heading',{name:'What will you write today?'}).waitFor();assert.equal(await page.locator('.topic-card').count(),4);await capture('02-topics');
   await page.getByRole('button',{name:'Surprise me',exact:true}).click();await page.getByRole('button',{name:'Start writing',exact:true}).click();await page.locator('#essay').fill(essay);await page.reload();assert.equal(await page.locator('#essay').inputValue(),essay);await capture('03-writing');
   const draft=await page.evaluate(()=>localStorage.getItem('fogwrite.draft.v1'));await page.getByRole('button',{name:'Overview',exact:true}).click();await page.getByRole('button',{name:'Explore sample feedback'}).click();await page.getByRole('button',{name:/error: students has/}).click();await page.getByRole('region',{name:'Selected passage feedback'}).waitFor();await capture('04-assessment');assert.equal(await page.evaluate(()=>localStorage.getItem('fogwrite.draft.v1')),draft);
   await page.getByRole('button',{name:'Close passage feedback'}).click();await page.getByRole('button',{name:/TR Task Response/}).click();await page.getByRole('button',{name:'Practise Task Response',exact:true}).waitFor();assert.match(page.url(),/assessment\/task-response$/);await capture('05-criterion');
   await page.getByRole('button',{name:'Practise Task Response',exact:true}).click();await page.getByRole('button',{name:'Check answer',exact:true}).click();await page.getByRole('heading',{name:'Partially correct',exact:true}).waitFor();await capture('06-skill-practice');
   // Real client contracts: fixture responses never call Gemini or spend quota.
   let submitted=false,generated=false,answered=false;
   await page.route(base+'/api/**',async route=>{const p=new URL(route.request().url()).pathname;
    if(p.endsWith('/evaluate')){const body=route.request().postDataJSON();assert.equal(body.essay,essay);assert.equal(body.source,null);assert.equal(body.experiment,'V1_STRATIFIED');submitted=true;return route.fulfill({json:grade});}
    if(p.endsWith('/exercises')){if(route.request().method()==='POST')generated=true;return route.fulfill({json:generated?{state:'ready',errors:[{error_id:'error-ui',criterion:'GRA',original_quote:'students has',paragraph_number:2,exercise_eligible:true}],exercises:[{exercise_id:'exercise-ui',source_error_id:'error-ui',type:'multiple_choice',skill:'subject_verb_agreement',difficulty:1,instruction:'Choose the correct verb.',question:'The students ___ ready.',options:['is','are','be'],attempts:answered?1:0}]}:{state:'not_generated',errors:[],exercises:[]}});}
    if(p.endsWith('/practice-attempt/submit')){assert.equal(route.request().postDataJSON().answers[0].answer,'are');answered=true;return route.fulfill({json:{state:'complete',correct_count:1,total:1,summary:'Agreement practised.',items:[{exercise_id:'exercise-ui',outcome:'correct',explanation:'Plural subjects take are.',correct_answer:'are',accepted_alternatives:[],attempt_number:1}]}});}
    if(p.endsWith('/practice-attempt'))return route.fulfill({json:{state:'draft',answers:[],result:null}});
    if(p.endsWith('/hint'))return route.fulfill({json:{hint:'Check whether the subject is plural.'}});
    if(p.endsWith('/progress'))return route.fulfill({json:{exercises_completed:answered?1:0,exercises_total:1,skills_practiced:[],skills_requiring_practice:[],hints_used:0,revisions:[]}});
    if(p.endsWith('/submission'))return route.fulfill({json:{submission_id:'ui-contract',prompt:'Discuss both views and give your opinion.',essay,grade}});
    return route.fulfill({json:{items:[]}});
   });
   page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Check My Essay',exact:true}).click();assert.equal(await page.locator('#essay').inputValue(),essay);await page.getByRole('button',{name:'Submit essay',exact:true}).click();await page.getByRole('button',{name:'Assess my essay'}).click();await page.getByRole('heading',{name:'Your writing, clearer.'}).waitFor();assert.equal(submitted,true);
   await page.getByRole('button',{name:/error: students has/}).click();await page.getByRole('button',{name:'Practise this skill'}).click();await page.getByRole('button',{name:'Generate Practice Exercises'}).click();await page.getByRole('radio',{name:'are',exact:true}).check();assert.equal(await page.getByRole('button',{name:'Check answer',exact:true}).count(),0);await page.getByRole('button',{name:'Submit all responses',exact:true}).click();await page.getByRole('heading',{name:'Correct',exact:true}).waitFor();assert.equal(answered,true);
   assert.deepEqual(failures,[]);await context.close();
  }
  console.log('PASS: six screens at 1440x900 and 1280x800, PNG loading/fallbacks, overflow, draft isolation, navigation, grading and practice API contracts. Screenshots: '+out);
 }finally{if(browser)await browser.close();}
})().catch(e=>{console.error(String(e.message).slice(0,1200));process.exitCode=1;});
