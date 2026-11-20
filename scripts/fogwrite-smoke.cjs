const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await context.newPage();const failures=[];
 page.on('pageerror',e=>failures.push(e.message));
 if(process.env.FOGWRITE_OFFLINE_TEST){
   const path=require('node:path');
   await page.route('http://127.0.0.1:8000/**',async route=>{
     const url=new URL(route.request().url());
     if(url.pathname.startsWith('/api/'))return route.fulfill({json:url.pathname==='/api/health'?{model_configured:false}:{items:[]}});
     const file=path.join(__dirname,'../frontend/dist',url.pathname==='/'?'index.html':url.pathname.slice(1));
     await route.fulfill({path:file,contentType:file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'text/html'});
   });
   await page.route('https://fonts.googleapis.com/**',r=>r.abort());
 }
 await page.goto('http://127.0.0.1:8000');
 await page.getByRole('heading',{name:'Small steps. Stronger writing.'}).waitFor();
 await page.screenshot({path:'artifacts/fogwrite-landing.png',fullPage:true});
 await page.getByRole('button',{name:'Explore sample feedback'}).click();
 await page.getByRole('heading',{name:'Your writing, clearer.'}).waitFor();
 await page.getByRole('button',{name:/error: students has/}).click();
 await page.getByText('students have',{exact:true}).waitFor();
 await page.getByRole('button',{name:'← Back to overview'}).click();
 await page.getByRole('button',{name:/TR\s*Task Response/}).click();
 await page.getByRole('button',{name:'Practise TR',exact:true}).waitFor();
 await page.screenshot({path:'artifacts/fogwrite-feedback.png',fullPage:true});
 await page.getByRole('button',{name:'Practise TR',exact:true}).click();
 await page.getByRole('heading',{name:'Start with your own essay.'}).waitFor();
 await page.getByRole('button',{name:'← Back to feedback'}).click();
 await page.getByRole('button',{name:'Practise TR',exact:true}).waitFor();
 await page.getByRole('button',{name:'Writing Practice',exact:true}).click();
 await page.getByRole('button',{name:/Surprise me/}).click();
 await page.getByRole('heading',{name:'Ready for a little focus?'}).waitFor();
 page.once('dialog',d=>d.accept());
 await page.getByRole('button',{name:'Start writing',exact:true}).click();
 await page.locator('#essay').fill('This is a draft that should survive a page reload.');
 await page.reload();
 await assert.equal(await page.locator('#essay').inputValue(),'This is a draft that should survive a page reload.');
 await page.getByRole('timer').waitFor();
 await page.screenshot({path:'artifacts/fogwrite-writing.png',fullPage:true});
 await page.evaluate(()=>{const k='fogwrite.draft.v1';const d=JSON.parse(localStorage.getItem(k));d.started=Date.now()-2401000;localStorage.setItem(k,JSON.stringify(d));});
 await page.reload();await page.getByText('Time’s up.',{exact:false}).waitFor();assert.equal(await page.locator('#essay').isDisabled(),true);
 await page.getByRole('button',{name:'continue with extra time'}).click();assert.equal(await page.locator('#essay').isEnabled(),true);
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'artifacts/fogwrite-mobile.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 // Contract fixture: verify requests and rendering, not live model accuracy.
 const keys=['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'];
 const grade={submission_id:'ui-contract',estimated_overall_band:6,word_count:12,criterion_scores:Object.fromEntries(keys.map(k=>[k,6])),criterion_feedback:Object.fromEntries(keys.map(k=>[k,{explanation:'Contract test feedback',strengths:[],weaknesses:[],evidence:[]}])),grammar_corrections:[{original:'students has',corrected:'students have',explanation:'Plural subject needs a plural verb.'}],priority_improvements:['Check agreement.'],validation_warnings:[],paragraph_reviews:[],language_suggestions:[],aspect_reviews:[]};
 let submitted=false,generated=false,answered=false;
 const exercise={exercise_id:'exercise-ui',source_error_id:'error-ui',type:'multiple_choice',skill:'subject_verb_agreement',difficulty:1,instruction:'Choose the correct verb.',question:'The students ___ ready.',options:['is','are','be'],learning_objective:'Match the subject and verb.',attempts:0};
 const batch={state:'ready',errors:[{error_id:'error-ui',criterion:'GRA',original_quote:'students has',paragraph_number:1,exercise_eligible:true}],exercises:[exercise]};
 await page.route('http://127.0.0.1:8000/api/**',async route=>{
   const p=new URL(route.request().url()).pathname;
   if(p.endsWith('/evaluate')){const body=route.request().postDataJSON();assert.equal(body.source,null);assert.equal(body.experiment,'V1_STRATIFIED');assert.ok(body.essay.includes('students has'));submitted=true;return route.fulfill({json:grade});}
   if(p.endsWith('/exercises')){if(route.request().method()==='POST')generated=true;return route.fulfill({json:generated?batch:{state:'not_generated',errors:[],exercises:[]}});}
   if(p.endsWith('/answer')){assert.equal(route.request().postDataJSON().answer,'are');answered=true;return route.fulfill({json:{outcome:'correct',explanation:'Plural subjects take are.',correct_answer:'are',accepted_alternatives:[],attempt_number:1}});}
   if(p.endsWith('/progress'))return route.fulfill({json:{exercises_completed:answered?1:0}});
   return route.fulfill({json:{items:[]}});
 });
 await page.locator('#essay').fill('Many students has difficulty managing their time at university. They need support.');
 await page.getByRole('button',{name:'Submit for assessment'}).click();
 await page.getByRole('button',{name:'Assess my essay'}).click();
 await page.getByRole('heading',{name:'Your writing, clearer.'}).waitFor();assert.equal(submitted,true);
 await page.getByRole('button',{name:/error: students has/}).click();
 await page.getByRole('button',{name:'Practise this skill'}).click();
 await page.getByRole('button',{name:'Generate Practice Exercises'}).click();
 await page.getByRole('heading',{name:'Choose the correct verb.'}).waitFor();
 await page.getByRole('radio',{name:'are',exact:true}).check();
 await page.getByRole('button',{name:'Check Answer',exact:true}).click();
 await page.getByRole('heading',{name:'correct',exact:true}).waitFor();assert.equal(answered,true);
 await page.screenshot({path:'artifacts/fogwrite-practice.png',fullPage:true});
 await page.getByRole('button',{name:'Check My Essay',exact:true}).click();
 await page.locator('#essay').fill('This updated draft must not display the previous assessment.');
 await page.evaluate(()=>{location.hash='feedback';});
 await page.getByRole('heading',{name:'First, a little writing.'}).waitFor();
 assert.deepEqual(failures,[]);console.log('PASS: landing, highlight, criteria, practice navigation, draft reload, timer expiry, extra time, mobile, evaluation/practice API contracts, browser errors.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
