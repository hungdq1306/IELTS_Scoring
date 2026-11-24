const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const deps=process.env.FOGWRITE_NODE_MODULES||path.resolve(__dirname,'../frontend/node_modules');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||require.resolve('playwright',{paths:[deps]}));
const localChromium='C:/Users/Lenovo/AppData/Local/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe';
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8000',out=path.join(root,'.cache/auth-ui');fs.mkdirSync(out,{recursive:true});

async function assertFormA11y(page,label){
 const missing=await page.evaluate(()=>Array.from(document.querySelectorAll('input,textarea,select')).filter(el=>{
  const r=el.getBoundingClientRect();
  return (r.width>0||r.height>0)&&(!el.id||!el.name);
 }).map(el=>el.outerHTML.slice(0,120)));
 assert.deepEqual(missing,[],`${label}: form controls missing id or name`);
}

(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||(fs.existsSync(localChromium)?localChromium:undefined)});try{
for(const width of [1440,1024,768,390])for(const role of ['visitor','student','ta','teacher','admin']){
 const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();page.setDefaultTimeout(8000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let classSaves=0,userSaves=0,settingSaves=0,retries=0,removals=0,auditQueries=[],overviewConfigured=false;
 let consent=role==='teacher'?null:'v1',rooms=role==='ta'?[{id:'room-test',name:'Writing class',student_count:1,active:true,can_manage:false}]:[],creates=0,joins=0,consents=0,protectedCalls=0;
 await context.addInitScript(()=>{for(const id of ['backend-test-only','backend-user-a','backend-user-b','guide-user'])localStorage.setItem('fogwrite:tour_done:'+id,'completed');});
 await context.addInitScript(({visitor})=>{let listeners=[];window.__profileOpened=false;window.Clerk={user:visitor?null:{id:'clerk-test-only',fullName:'Alex Writer',primaryEmailAddress:{emailAddress:'alex@example.test'},imageUrl:''},session:visitor?null:{getToken:async()=> 'test-session-token'},load:async()=>{},addListener:fn=>{listeners.push(fn);return()=>{listeners=listeners.filter(x=>x!==fn);};},openSignIn:()=>{window.__signInOpened=true;},openUserProfile:()=>{window.__profileOpened=true;},signOut:async()=>{window.Clerk.session=null;window.Clerk.user=null;listeners.forEach(fn=>fn({}));}};},{visitor:role==='visitor'});
 await context.route('https://clerk.example.test/**',r=>r.fulfill({body:'',contentType:'text/javascript'}));await context.route('https://fonts.googleapis.com/**',r=>r.abort());
 await context.route(base+'/**',async route=>{const url=new URL(route.request().url()),p=url.pathname,method=route.request().method();
  if(p==='/api/auth/config')return route.fulfill({json:{mode:'clerk',issuer:'https://clerk.example.test',publishable_key:'pk_test_fixture',privacy_version:'v1',retention_days:30,gemini_data_policy:'free_product_improvement'}});
  if(p.startsWith('/api/')){protectedCalls++;assert.equal(route.request().headers().authorization,'Bearer test-session-token');
   if(p==='/api/auth/me')return route.fulfill({json:{id:'backend-test-only',role,consent_version:consent,classes:rooms,quota_status:{remaining_today:3,daily_limit:3,is_enrolled:rooms.length>0}}});
   if(p==='/api/auth/consent'){const body=route.request().postDataJSON();assert.equal(body.accepted_privacy,true);assert.equal(body.adult_confirmed,true);consent='v1';consents++;return route.fulfill({json:{accepted:true}});}
   if(p==='/api/teacher/classes'){assert.ok(['teacher','admin','ta'].includes(role));if(method==='POST'){creates++;rooms.push({id:'room-test',name:route.request().postDataJSON().name,student_count:0,join_code:'TESTCODE',active:true,can_manage:true});}return route.fulfill({json:method==='POST'?rooms.at(-1):{items:rooms}});}
   if(p==='/api/classes/room-test/leave'&&method==='POST'){rooms=[];return route.fulfill({json:{status:'LEFT'}});}
   if(p==='/api/classes/join'){joins++;if(route.request().postDataJSON().join_code!=='TESTCODE')return route.fulfill({status:400,json:{detail:'Invite code is invalid or expired.'}});rooms.push({id:'room-test',name:'Writing class',role:'student',teacher_name:'Teacher Nguyen',daily_student_quota:3,submission_count:1,active:true});return route.fulfill({json:rooms.at(-1)});}
   if(p==='/api/writing/task2/saved-assessment/submission'){const keys=['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'];return route.fulfill({json:{submission_id:'saved-assessment',prompt:'Discuss both views and give your opinion.',essay:'A saved teacher essay.',grade:{estimated_overall_band:6,criterion_scores:Object.fromEntries(keys.map(k=>[k,6])),criterion_feedback:Object.fromEntries(keys.map(k=>[k,{explanation:'Feedback',strengths:[],weaknesses:[],evidence:[]}])),grammar_corrections:[],language_suggestions:[],priority_improvements:[],validation_warnings:[]}}});}
   if(p==='/api/teacher/classes/room-test'&&method==='PATCH'){classSaves++;const patch=route.request().postDataJSON();Object.assign(rooms[0],{name:patch.name,daily_student_quota:patch.daily_student_quota,active:patch.is_active});return route.fulfill({json:{saved:true}});}
   if(p==='/api/practice/submissions')return route.fulfill({json:{items:[]}});
   if(p.endsWith('/students'))return route.fulfill({json:{items:[{user_id:'student-fixture',display_label:'Jamie Learner',email:'jamie@example.test',role:'student',member_role:'student',submission_count:2,joined_at:1700000000,active:true}]}});
   if(p==='/api/teacher/classes/room-test/students/student-fixture'&&method==='DELETE'){removals++;return route.fulfill({json:{saved:true}});}
   if(p.includes('/teacher/classes/')&&p.endsWith('/submissions'))return route.fulfill({json:{items:[{id:'sub-fixture-1',submission_code:'SUB00001',student_name:'Jamie Learner',student_email:'jamie@example.test',submitted_at:1700000000,prompt:'Discuss transport options.',essay:'Sample student essay text.',status:'COMPLETED'}]}});
   if(p==='/api/admin/users'){assert.equal(role,'admin');return route.fulfill({json:{items:[{id:'backend-test-only',external_auth_id:'clerk-test-only',display_label:'Alex Writer',email:'alex@example.test',role:'admin',is_active:true,bonus_daily_credits:0,classes:[],remaining_today:50,daily_limit:50}],total:1}});}
   if(p==='/api/admin/users/backend-test-only'&&method==='PATCH'){const b=route.request().postDataJSON();assert.equal(b.role,'admin');assert.equal(b.is_active,true);userSaves++;return route.fulfill({json:{saved:true}});}
   if(p==='/api/admin/settings'){if(method==='PATCH'){const b=route.request().postDataJSON();assert.equal(b.teacher_daily_limit,25);assert.equal(b.model_prices_usd_per_million,undefined,'unmodified pricing should not be sent');assert.equal(b.apply_to_existing_classes,false);settingSaves++;return route.fulfill({json:{settings:{enrolled_student_daily_limit:3,ta_daily_limit:5,teacher_daily_limit:25,admin_daily_limit:50,global_daily_submission_cap:500,active_prompt_version:'v2',calibration_offsets_json:{},model_prices_usd_per_million:{'fixture-model':{input:0.1,output:0.2}}},affected_classes_count:0}});}return route.fulfill({json:{enrolled_student_daily_limit:3,ta_daily_limit:5,teacher_daily_limit:20,admin_daily_limit:50,global_daily_submission_cap:500,active_prompt_version:'v2',calibration_offsets_json:{},model_prices_usd_per_million:{'fixture-model':{input:0.1,output:0.2}}}});}
   if(p==='/api/admin/overview')return route.fulfill({json:{today_submissions:3,completed_today:2,active_classes:1,queue_depth:0,failed_jobs_today:0,longest_active_wait_sec:0,grading_latency:{'24h':{count:2,median_sec:4.2,p95_sec:6.1},'7d':{count:5,median_sec:4.5,p95_sec:7.0}},total_tokens_used:overviewConfigured?0:100,pricing_configured:overviewConfigured,estimated_gemini_cost:overviewConfigured?0:null,unpriced_or_unknown_calls:overviewConfigured?0:1,usage_by_day_model:[]}});
   if(p==='/api/admin/jobs')return route.fulfill({json:{items:[{job_id:'failed-job',submission_id:'failed-submission',submission_code:'FAILED01',student_name:'Jamie Learner',class_name:'Writing class',kind:'score',status:retries?'QUEUED':'FAILED',attempt_count:1,created_at:1700000000,wait_duration_sec:12,error_code:retries?null:'provider_timeout',error_message:'Try again.',credit_refunded:!retries}],total:1}});
   if(p==='/api/admin/jobs/failed-submission/retry'){retries++;return route.fulfill({json:{status:'QUEUED'}});}
   if(p==='/api/admin/audit-logs'){auditQueries.push(url.searchParams.toString());return route.fulfill({json:{items:[{id:'audit-fixture',actor_name:'Alex Writer',actor_email:'alex@example.test',target_label:'Jamie Learner',action_type:'job_retried',reason:'Provider recovered',created_at:1700000000,before_json:{status:'FAILED'},after_json:{status:'QUEUED'}}],total:1}});}
   return route.fulfill({json:{items:[]}});
  }
  const asset=/\.(js|css|png)$/.test(p);const file=path.join(root,'frontend/dist',asset?p.slice(1):'index.html');return route.fulfill({path:file,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.png')?'image/png':'text/html'});
 });
 await page.goto(base);assert.equal(await page.locator('#pilot-account-root').count(),0);
 if(role==='visitor'){await page.getByRole('heading',{name:'Small steps. Stronger writing.'}).waitFor();assert.equal(await page.locator('.sidebar').count(),0);assert.equal(protectedCalls,0);await page.getByRole('button',{name:'Sign in',exact:true}).click();assert.equal(await page.evaluate(()=>window.__signInOpened),true);}
 else{
  if(role==='teacher'){await page.getByRole('heading',{name:'Your privacy, your choice.'}).waitFor();assert.equal(await page.getByRole('button',{name:'Accept and continue'}).isDisabled(),true);await assertFormA11y(page,'consent');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Accept and continue'}).click();assert.equal(consents,1);}
  await page.getByRole('heading',{name:'Welcome to your writing studio.'}).waitFor();assert.equal(await page.getByRole('button',{name:'Sign in',exact:true}).count(),0);
  if(role==='student')await page.getByRole('heading',{name:'Three steps to stronger writing'}).waitFor();
  if(width<=768)await page.getByRole('button',{name:'Open navigation'}).click();
  const bounds=await page.locator('.profile-trigger').boundingBox();assert.ok(bounds.y>700,'profile must be anchored at bottom');
  await page.locator('.profile-trigger').click();await page.getByRole('menu',{name:'Account menu'}).waitFor();await page.getByText(/Resets daily at 00:00 Vietnam time/).waitFor();await page.keyboard.press('Escape');assert.equal(await page.getByRole('menu',{name:'Account menu'}).count(),0);
  await page.locator('.profile-trigger').click();await page.getByRole('menuitem',{name:'My Classes',exact:true}).click();await page.getByRole('heading',{name:'My Classes',exact:true}).waitFor();
  if(role==='teacher'||role==='admin'){
   await assertFormA11y(page,'classes-create');
   await page.getByLabel('Create a class').fill('Writing class');await page.getByRole('button',{name:'Create Class',exact:true}).dblclick();await page.getByRole('heading',{name:'Writing class',exact:true}).waitFor();assert.equal(creates,1);
   await page.getByLabel('Class name',{exact:true}).fill('Updated writing class');await page.getByRole('button',{name:'Save class settings',exact:true}).click();await page.getByRole('heading',{name:'Updated writing class',exact:true}).waitFor();assert.equal(classSaves,1);
   await page.getByRole('button',{name:'View class'}).click();await page.getByRole('heading',{name:'Class members',exact:true}).waitFor();await page.getByLabel('Search class members').fill('no-such-member');await page.getByText('No matching class members.',{exact:true}).waitFor();await page.getByRole('button',{name:'All classes',exact:true}).click();await page.getByRole('button',{name:'View class',exact:true}).click();assert.equal(await page.getByLabel('Search class members').evaluate(el=>el.value),'');
   await page.getByText('jamie@example.test',{exact:true}).waitFor();await page.getByText(/2 submissions/).waitFor();
   await page.getByText(/SUB00001/).first().click();await page.getByText('SUB00001',{exact:true}).waitFor();
   await assertFormA11y(page,'class-detail');
   await page.getByRole('button',{name:'Remove student',exact:true}).click();
   await page.getByRole('dialog').getByText(/Jamie Learner \(jamie@example\.test\)/).waitFor();
   await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
   assert.equal(removals,0);
   await page.getByLabel('Search class members').fill('nobody');assert.equal(await page.getByText('jamie@example.test',{exact:true}).count(),0);
   await page.getByLabel('Search class members').fill('Jamie');await page.getByText('jamie@example.test',{exact:true}).waitFor();
  }
  else if(role==='ta'){assert.equal(await page.getByRole('button',{name:'Create Class',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Save class settings',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Regenerate code',exact:true}).count(),0);await page.getByRole('button',{name:'View class'}).click();await page.getByRole('heading',{name:'Class members',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Remove student',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Assign TA',exact:true}).count(),0);}
  else{
   await assertFormA11y(page,'student-join');
   await page.getByLabel('Teacher invite code').fill('WRONGCODE');await page.getByRole('button',{name:'Join Class',exact:true}).click();await page.getByRole('alert').filter({hasText:'invalid'}).waitFor();
   await page.getByLabel('Teacher invite code').fill('TESTCODE');await page.getByRole('button',{name:'Join Class',exact:true}).click();await page.getByRole('heading',{name:'Writing class',exact:true}).waitFor();
   assert.equal(joins,2);assert.equal(await page.getByRole('button',{name:'Create Class',exact:true}).count(),0);
   await page.locator('.active-class-badge').waitFor();await page.getByText('Teacher Nguyen').waitFor();await page.getByText('3 credits/day').waitFor();
   await page.goto(base+'/check');await page.getByText('Submitting to:').waitFor();await assertFormA11y(page,'check-editor');
   assert.equal(await page.locator('.assessment-options').count(),0,'Pilot mode must not expose unsupported FS0/FS5_FULL options');
   await page.goto(base+'/admin');await page.getByText('Administrator permissions are required.').waitFor();await page.locator('#main').getByRole('button',{name:'Back to Studio',exact:true}).waitFor();await page.locator('#main').getByRole('button',{name:'My Classes',exact:true}).click();await page.getByRole('heading',{name:'My Classes',exact:true}).waitFor();
   await page.getByRole('button',{name:'Leave class',exact:true}).click();
   await page.getByRole('heading',{name:'Leave class?',exact:true}).waitFor();
   await page.getByText(/Credits used today do not reset/).waitFor();
   await page.getByRole('button',{name:'Cancel',exact:true}).click();
   await page.getByRole('button',{name:'Leave class',exact:true}).click();
   await page.getByRole('dialog').getByRole('button',{name:'Leave class',exact:true}).click();
   await page.getByText(/You left the class/).waitFor();
   await page.goto(base+'/check');await page.getByText('Join a class to submit',{exact:true}).waitFor();
   await page.locator('#task-question').fill('Discuss whether cities should improve public transport.');
   await page.locator('#essay').fill('Cities should improve their bus networks to help people reach work.');
   assert.equal(await page.getByRole('button',{name:'Submit essay',exact:true}).isDisabled(),true);
   await page.goto(base+'/classes');await page.getByRole('heading',{name:'My Classes',exact:true}).waitFor();

  }
  if(role==='admin'){
   await page.goto(base+'/admin');await page.getByRole('heading',{name:'Administration',exact:true}).waitFor();
   await page.getByText('Current account (You)').waitFor();await page.getByText('clerk-test-only').waitFor();
   await assertFormA11y(page,'admin-users');
   await page.getByLabel('Bonus daily credits',{exact:true}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Save account',exact:true}).isDisabled(),true);
   await page.getByLabel('Bonus daily credits',{exact:true}).fill('2');
   assert.equal(await page.getByRole('button',{name:'Save account',exact:true}).isDisabled(),false);
   await page.getByRole('button',{name:'Save account',exact:true}).click();
   await page.getByRole('heading',{name:'Confirm account update'}).waitFor();
   await page.getByRole('button',{name:'Confirm changes',exact:true}).click();
   await page.getByText('Account updated.',{exact:true}).waitFor();assert.equal(userSaves,1);
   await page.getByRole('button',{name:'System settings',exact:true}).click();
   await assertFormA11y(page,'admin-settings');
   await page.getByLabel('Teacher daily credits',{exact:true}).fill('25');
   await page.getByRole('button',{name:'Save settings',exact:true}).click();
   await page.getByText('System settings saved.',{exact:true}).waitFor();assert.equal(settingSaves,1);
   await page.getByRole('button',{name:'Grading jobs',exact:true}).click();await assertFormA11y(page,'admin-jobs');
   await page.getByLabel('Reason for retry',{exact:true}).fill('Provider recovered');await page.getByRole('button',{name:'Retry failed assessment',exact:true}).click();
   await page.getByText('Assessment queued again. A daily credit has been reserved.',{exact:true}).waitFor();assert.equal(retries,1);
   await page.getByRole('button',{name:'Audit logs',exact:true}).click();await page.getByRole('heading',{name:'job retried',exact:true}).waitFor();
   await assertFormA11y(page,'admin-audit-logs');
   for(const value of ['operator_role_grant','operator_account_status','operator_deleted_writing','student_joined_class','student_left_class','class_enrollment_toggled'])assert.equal(await page.locator('#admin-audit-action option[value="'+value+'"]').count(),1);
   await page.getByLabel('Target (name, email or ID)',{exact:true}).fill('Jamie');
   await page.locator('#admin-audit-action').selectOption('job_retried');
   await page.getByRole('button',{name:'Search',exact:true}).click();
   await page.waitForFunction(()=>true);
   assert.ok(auditQueries.some(q=>q.includes('target=Jamie')&&q.includes('action=job_retried')),'audit-logs must send target and action filters');
   await page.getByRole('button',{name:'Usage overview',exact:true}).click();
   await page.getByText('Pricing unconfigured',{exact:true}).waitFor();await page.getByText('Longest active queue wait').waitFor();await page.getByText('End-to-end latency (Median / P95)').waitFor();
   overviewConfigured=true;
   await page.getByRole('button',{name:'Grading jobs',exact:true}).click();
   await page.getByRole('button',{name:'Usage overview',exact:true}).click();
   await page.getByText('$0.00',{exact:true}).waitFor();
   await page.goto(base+'/classes');
  }
  await page.reload();await page.getByRole('heading',{name:'My Classes',exact:true}).waitFor();assert.equal(await page.getByRole('heading',{name:'Your privacy, your choice.'}).count(),0);if(width===1440&&role==='teacher'){await page.evaluate(()=>sessionStorage.setItem('fogwrite.assessment','saved-assessment'));await page.goto(base+'/assessment');await page.getByRole('heading',{name:'Your writing, clearer.'}).waitFor();assert.equal(await page.evaluate(()=>sessionStorage.getItem('fogwrite.assessment')),'saved-assessment');await page.goto(base+'/classes');await page.getByRole('heading',{name:'My Classes',exact:true}).waitFor();}
  if(width<=768)await page.getByRole('button',{name:'Open navigation'}).click();await page.locator('.profile-trigger').click();await page.getByRole('menu',{name:'Account menu'}).waitFor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);const menuBounds=await page.getByRole('menu',{name:'Account menu'}).boundingBox();assert.ok(menuBounds.x>=0&&menuBounds.x+menuBounds.width<=width&&menuBounds.y>=0);await page.screenshot({path:path.join(out,`${width}-${role}.png`),fullPage:true});await page.getByRole('menuitem',{name:'Account Settings',exact:true}).click();assert.equal(await page.evaluate(()=>window.__profileOpened),true);if(width===1440&&role==='student'){await page.route(base+'/api/auth/me',r=>r.fulfill({status:401,json:{detail:'Session expired.'}}));await page.evaluate(()=>dispatchEvent(new Event('fogwrite:account')));await page.getByRole('heading',{name:'Your writing is safe.'}).waitFor();assert.equal(await page.locator('.sidebar').count(),0);await page.unroute(base+'/api/auth/me');await page.getByRole('button',{name:'Try again',exact:true}).click();await page.getByRole('heading',{name:'My Classes',exact:true}).waitFor();}
  await page.locator('.profile-trigger').click();await page.getByRole('menuitem',{name:'My Profile',exact:true}).click();await page.getByRole('heading',{name:'My Profile',exact:true}).waitFor();
  if(width<=768)await page.getByRole('button',{name:'Open navigation'}).click();await page.locator('.profile-trigger').click();await page.getByRole('menuitem',{name:'Sign Out',exact:true}).click();await page.getByRole('heading',{name:'Small steps. Stronger writing.'}).waitFor();
 }
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);if(role==='visitor')await page.screenshot({path:path.join(out,`${width}-${role}.png`),fullPage:true});await context.close();console.log('PASS '+width+' '+role);
}

// Cross-account draft isolation + Continue draft mode/timer restoration test.
{
 const context=await browser.newContext({viewport:{width:1440,height:900}}),page=await context.newPage();page.setDefaultTimeout(8000);
 await context.addInitScript(()=>{for(const id of ['backend-test-only','backend-user-a','backend-user-b','guide-user'])localStorage.setItem('fogwrite:tour_done:'+id,'completed');});
 await context.addInitScript(()=>{
  localStorage.setItem('fogwrite.draft.v1',JSON.stringify({prompt:'Legacy leak',essay:'Legacy essay text'}));
  let listeners=[];window.__setMockUser=(id,name)=>{window.Clerk.user={id,fullName:name,primaryEmailAddress:{emailAddress:id+'@example.test'},imageUrl:''};window.Clerk.session={getToken:async()=> 'token-'+id};listeners.forEach(fn=>fn({}));};
  window.Clerk={user:{id:'clerk-teacher',fullName:'Teacher A',primaryEmailAddress:{emailAddress:'a@example.test'},imageUrl:''},session:{getToken:async()=> 'token-a'},load:async()=>{},addListener:fn=>{listeners.push(fn);return()=>{};},openSignIn:()=>{},openUserProfile:()=>{},signOut:async()=>{window.Clerk.session=null;window.Clerk.user=null;listeners.forEach(fn=>fn({}));}};
 });
 await context.route('https://clerk.example.test/**',r=>r.fulfill({body:'',contentType:'text/javascript'}));await context.route('https://fonts.googleapis.com/**',r=>r.abort());
 await context.route(base+'/**',async route=>{const url=new URL(route.request().url()),p=url.pathname;
  if(p==='/api/auth/config')return route.fulfill({json:{mode:'clerk',issuer:'https://clerk.example.test',publishable_key:'pk_test_fixture',privacy_version:'v1',retention_days:30,gemini_data_policy:'free_product_improvement'}});
  if(p==='/api/auth/me'){const authHdr=route.request().headers().authorization||'';const isB=authHdr.includes('user-b');return route.fulfill({json:{id:isB?'backend-user-b':'backend-user-a',role:isB?'admin':'teacher',consent_version:'v1',classes:[{id:'class-1',name:'Fog1',role:'student',teacher_name:'Teacher Nguyen',daily_student_quota:3,submission_count:0,active:true}]}});}
  if(p.startsWith('/api/'))return route.fulfill({json:{items:[]}});
  const asset=/\.(js|css|png)$/.test(p);const file=path.join(root,'frontend/dist',asset?p.slice(1):'index.html');return route.fulfill({path:file,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.png')?'image/png':'text/html'});
 });
 await page.goto(base);
 await page.getByRole('heading',{name:'Welcome to your writing studio.'}).waitFor();
 assert.equal(await page.evaluate(()=>localStorage.getItem('fogwrite.draft.v1')),null,'legacy draft key must be purged');
 assert.equal(await page.getByRole('button',{name:'Continue draft'}).count(),0);
 await page.getByRole('button',{name:'Start writing',exact:true}).click();
 await page.locator('.topic-choose').first().click();
 await page.getByRole('button',{name:'Start writing',exact:true}).click();
 await page.locator('#essay').fill('Teacher A timed draft content.');
 await page.waitForFunction(()=>Boolean(localStorage.getItem('fogwrite:draft:backend-user-a')));
 await page.getByRole('button',{name:'Overview',exact:true}).click();
 await page.getByRole('button',{name:'Continue draft',exact:true}).waitFor();
 // Direct switch A -> B (no Sign Out in between) must NOT write A's draft into B's storage key!
 await page.evaluate(()=>window.__setMockUser('user-b','Admin B'));
 await page.waitForFunction(()=>document.body.innerText.includes('Administration'));
 await page.waitForTimeout(150);
 assert.equal(await page.evaluate(()=>localStorage.getItem('fogwrite:draft:backend-user-b')),null,'direct switch A->B must NEVER write A draft to B storage key');
 assert.equal(await page.getByRole('button',{name:'Continue draft'}).count(),0,'User B must never see User A draft');
 // Sign back in as User A with remainingSec=1500 (25:00) and verify Continue draft routes to /practice with accurate countdown.
 await page.evaluate(()=>{
  const raw=JSON.parse(localStorage.getItem('fogwrite:draft:backend-user-a'));
  localStorage.setItem('fogwrite:draft:backend-user-a',JSON.stringify({...raw,started:null,remainingSec:1500,timerDurationSec:2400}));
  window.__setMockUser('clerk-teacher','Teacher A');
 });
 await page.waitForFunction(()=>!document.body.innerText.includes('Administration'));
 await page.getByRole('button',{name:'Continue draft',exact:true}).click();
 await page.getByRole('heading',{name:'Writing Practice',exact:true}).waitFor();
 const timerText=await page.locator('[role="timer"]').innerText();
 const m=timerText.match(/(\d{2}):(\d{2})/);
 assert.ok(m,`expected MM:SS timer text, got ${timerText}`);
 const remaining=Number(m[1])*60+Number(m[2]);
 assert.ok(remaining>=1485&&remaining<=1500,`expected restored countdown ~25:00 (1485-1500s), got ${timerText} (${remaining}s)`);
 assert.equal(await page.locator('#essay').inputValue(),'Teacher A timed draft content.');
 await context.close();
 console.log('PASS direct A->B draft isolation & exact practice countdown continue-draft');
}

// In-flight restore() + History isolation on direct A -> B switch.
{
 const context=await browser.newContext({viewport:{width:1440,height:900}}),page=await context.newPage();page.setDefaultTimeout(8000);
 let releaseRestoreA;const restoreGateA=new Promise(resolve=>{releaseRestoreA=resolve;});
 await context.addInitScript(()=>{for(const id of ['backend-test-only','backend-user-a','backend-user-b','guide-user'])localStorage.setItem('fogwrite:tour_done:'+id,'completed');});
 await context.addInitScript(()=>{
  let listeners=[];window.__setMockUser=(id,name)=>{window.Clerk.user={id,fullName:name,primaryEmailAddress:{emailAddress:id+'@example.test'},imageUrl:''};window.Clerk.session={getToken:async()=> 'token-'+id};listeners.forEach(fn=>fn({}));};
  window.Clerk={user:{id:'clerk-a',fullName:'User A',primaryEmailAddress:{emailAddress:'a@example.test'},imageUrl:''},session:{getToken:async()=> 'token-a'},load:async()=>{},addListener:fn=>{listeners.push(fn);return()=>{};},openSignIn:()=>{},openUserProfile:()=>{},signOut:async()=>{window.Clerk.session=null;window.Clerk.user=null;listeners.forEach(fn=>fn({}));}};
 });
 await context.route('https://clerk.example.test/**',r=>r.fulfill({body:'',contentType:'text/javascript'}));await context.route('https://fonts.googleapis.com/**',r=>r.abort());
 await context.route(base+'/**',async route=>{const url=new URL(route.request().url()),p=url.pathname;
  const authHdr=route.request().headers().authorization||'';const isB=authHdr.includes('user-b');
  if(p==='/api/auth/config')return route.fulfill({json:{mode:'clerk',issuer:'https://clerk.example.test',publishable_key:'pk_test_fixture',privacy_version:'v1',retention_days:30,gemini_data_policy:'free_product_improvement'}});
  if(p==='/api/auth/me')return route.fulfill({json:{id:isB?'backend-user-b':'backend-user-a',role:isB?'admin':'student',consent_version:'v1',classes:[{id:'class-1',name:'Fog1',role:'student',teacher_name:'Teacher Nguyen',daily_student_quota:3,submission_count:0,active:true}]}});
  if(p==='/api/practice/submissions')return route.fulfill({json:{items:isB?[{submission_id:'sub-b',prompt:'PRIVATE HISTORY B',created:1700000100}]:[{submission_id:'sub-a',prompt:'PRIVATE HISTORY A',created:1700000000}]}});
  if(p==='/api/writing/task2/sub-a/submission'){
   await restoreGateA;
   const keys=['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'];
   try{return await route.fulfill({json:{submission_id:'sub-a',prompt:'PRIVATE HISTORY A',essay:'CONFIDENTIAL ESSAY OF USER A.',grade:{estimated_overall_band:7,criterion_scores:Object.fromEntries(keys.map(k=>[k,7])),criterion_feedback:Object.fromEntries(keys.map(k=>[k,{explanation:'Feedback A',strengths:[],weaknesses:[],evidence:[]}])),grammar_corrections:[],language_suggestions:[],priority_improvements:[],validation_warnings:[]}}});}catch{return;}
  }
  if(p.startsWith('/api/'))return route.fulfill({json:{items:[]}});
  const asset=/\.(js|css|png)$/.test(p);const file=path.join(root,'frontend/dist',asset?p.slice(1):'index.html');return route.fulfill({path:file,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.png')?'image/png':'text/html'});
 });
 await page.goto(base);
 await page.getByRole('heading',{name:'Welcome to your writing studio.'}).waitFor();
 await page.getByRole('button',{name:'History',exact:true}).click();
 await page.getByText('PRIVATE HISTORY A',{exact:true}).click();
 // Switch directly A -> B while User A's restore() request is still in-flight!
 await page.evaluate(()=>window.__setMockUser('user-b','Admin B'));
 await page.waitForFunction(()=>document.body.innerText.includes('Administration'));
 releaseRestoreA();
 await page.waitForTimeout(200);
 const bodyAfterSwitch=await page.evaluate(()=>document.body.innerText);
 assert.equal(bodyAfterSwitch.includes('CONFIDENTIAL ESSAY OF USER A.'),false,'stale restore() response must NOT render User A essay on User B screen');
 assert.equal(bodyAfterSwitch.includes('PRIVATE HISTORY A'),false,'User A history must NOT remain visible after direct A->B switch');
 await page.getByText('PRIVATE HISTORY B',{exact:true}).waitFor();
 await context.close();
 console.log('PASS in-flight restore & History isolation on direct A->B switch');
}

// Multi-class default & /check quick switch for Teacher + auto-polling practice generation.
{
 const context=await browser.newContext({viewport:{width:1440,height:900}}),page=await context.newPage();page.setDefaultTimeout(8000);
 let submittedClassId=null,exercisePolls=0;
 await context.addInitScript(()=>{localStorage.setItem('fogwrite:tour_done:backend-teacher','completed');});
 await context.addInitScript(()=>{
  window.Clerk={user:{id:'clerk-teacher-multi',fullName:'Teacher Multi',primaryEmailAddress:{emailAddress:'t@example.test'},imageUrl:''},session:{getToken:async()=> 'token-t'},load:async()=>{},addListener:()=>()=>{},openSignIn:()=>{},openUserProfile:()=>{},signOut:async()=>{}};
 });
 await context.route('https://clerk.example.test/**',r=>r.fulfill({body:'',contentType:'text/javascript'}));await context.route('https://fonts.googleapis.com/**',r=>r.abort());
 await context.route(base+'/**',async route=>{const url=new URL(route.request().url()),p=url.pathname,method=route.request().method();
  if(p==='/api/auth/config')return route.fulfill({json:{mode:'clerk',issuer:'https://clerk.example.test',publishable_key:'pk_test_fixture',privacy_version:'v1',retention_days:30,gemini_data_policy:'free_product_improvement'}});
  if(p==='/api/auth/me')return route.fulfill({json:{id:'backend-teacher',role:'teacher',consent_version:'v1',classes:[{id:'fog1',name:'Fog1',role:'teacher',active:true},{id:'qa-test',name:'QA Test',role:'teacher',active:true}],quota_status:{remaining_today:20,daily_limit:20,is_enrolled:true}}});
  if(p==='/api/writing/task2/evaluate'&&method==='POST'){
   submittedClassId=route.request().postDataJSON().class_id;
   return route.fulfill({json:{submission_id:'sub-multi-1',estimated_overall_band:7,criterion_scores:{task_response:7,coherence_cohesion:7,lexical_resource:7,grammatical_range_accuracy:7},criterion_feedback:{task_response:{explanation:'Feedback.',strengths:[],weaknesses:[],evidence:[]},coherence_cohesion:{explanation:'Feedback.',strengths:[],weaknesses:[],evidence:[]},lexical_resource:{explanation:'Feedback.',strengths:[],weaknesses:[],evidence:[]},grammatical_range_accuracy:{explanation:'Feedback.',strengths:[],weaknesses:[],evidence:[]}},grammar_corrections:[],language_suggestions:[],priority_improvements:['Develop body ideas.'],validation_warnings:[]}});
  }
  if(p==='/api/writing/task2/sub-multi-1/exercises'){
   exercisePolls++;
   if(exercisePolls===1)return route.fulfill({json:{submission_id:'sub-multi-1',state:'generating',errors:[],exercises:[]}});
   return route.fulfill({json:{submission_id:'sub-multi-1',state:'ready',errors:[{error_id:'e1',criterion:'TR',category:'task_response',subtype:'development',original_quote:'Cities need better buses.',paragraph_number:1,start:0,end:24,severity:'medium',evidence_verified:true,exercise_eligible:true,semantic_status:'machine_reviewed'}],exercises:[{exercise_id:'ex1',source_error_id:'e1',type:'sentence_rewriting',skill:'task_response',difficulty:1,instruction:'Rewrite to add clear cause and effect.',question:'Expand why buses help commuters.',structure_prompt:'',options:[],learning_objective:'Extend arguments',validation_status:'machine_reviewed_not_human_verified'}]}});
  }
  if(p.startsWith('/api/'))return route.fulfill({json:{items:[]}});
  const asset=/\.(js|css|png)$/.test(p);const file=path.join(root,'frontend/dist',asset?p.slice(1):'index.html');return route.fulfill({path:file,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.png')?'image/png':'text/html'});
 });
 await page.goto(base+'/check');
 await page.locator('#active-class-select').waitFor();
 assert.equal(await page.locator('#active-class-select').inputValue(),'fog1');
 await page.locator('#active-class-select').selectOption('qa-test');
 await page.locator('#task-question').fill('Discuss whether cities should invest more in public buses.');
 await page.locator('#essay').fill('Cities need better buses. Public buses reduce congestion and emissions for daily commuters across large cities.');
 await page.getByRole('button',{name:'Submit essay',exact:true}).click();
 await page.getByRole('button',{name:'Assess my essay',exact:true}).click();
 await page.getByRole('heading',{name:'Your writing, clearer.'}).waitFor();
 assert.equal(submittedClassId,'qa-test');
 await page.getByRole('button',{name:'Practise priority skills',exact:true}).click();
 await page.getByText('Preparing your practice exercises.',{exact:true}).waitFor();
 await page.getByText('Rewrite to add clear cause and effect.',{exact:true}).waitFor();
 assert.ok(exercisePolls>=2,'expected auto-poll until ready');
 await context.close();
 console.log('PASS multi-class Teacher /check switch & generating practice auto-poll');
}
}finally{await browser.close();}})().catch(e=>{console.error(e.message);process.exitCode=1;});
