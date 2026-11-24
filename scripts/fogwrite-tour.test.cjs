const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),assetRoot=process.env.FOGWRITE_TOUR_ASSET_ROOT||path.join(root,'frontend/dist'),deps=process.env.FOGWRITE_NODE_MODULES||path.join(root,'.cache/pilot-ui-deps/node_modules');
const {chromium}=require(require.resolve('playwright',{paths:[deps]}));
const local='C:/Users/Lenovo/AppData/Local/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe',base=process.env.FOGWRITE_TOUR_BASE_URL||'http://127.0.0.1:5173',live=process.env.FOGWRITE_TOUR_LIVE==='1';
async function setup(browser,{width=1440,user=null,reducedMotion='no-preference'}={}){
 const context=await browser.newContext({viewport:{width,height:900},reducedMotion}),page=await context.newPage();page.setDefaultTimeout(10000);const errors=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',r=>{if(r.url().startsWith(base+'/')&&r.status()>=400)errors.push(`HTTP ${r.status()} ${new URL(r.url()).pathname}`);});
 await context.addInitScript(({user})=>{localStorage.setItem('fogwrite:draft:tour-user',JSON.stringify({userId:'tour-user',essay:'PRIVATE DRAFT MUST SURVIVE',prompt:'Private question',mode:'check'}));window.Clerk={session:user?{id:'tour-session',getToken:async()=> 'fixture'}:null,user:user?{id:user,fullName:'Tour Tester'}:null,load:async()=>{},addListener:()=>()=>{},openSignIn:()=>{}};},{user});
 await context.route('https://clerk.example.test/**',r=>r.fulfill({body:'',contentType:'text/javascript'}));await context.route('https://fonts.googleapis.com/**',r=>r.abort());
 await context.route(base+'/**',async r=>{const p=new URL(r.request().url()).pathname;
  if(live&&!user){if(p.startsWith('/api/')&&r.request().method()!=='GET')writes.push(p);return r.continue();}
  if(p==='/api/auth/config')return r.fulfill({json:user?{mode:'clerk',issuer:'https://clerk.example.test',publishable_key:'pk_test_fixture',privacy_version:'v1'}:{mode:'demo',offline_preview:true}});
  if(p.startsWith('/api/')){if(r.request().method()!=='GET')writes.push(p);return r.fulfill({json:p==='/api/auth/me'?{id:user,role:'student',full_name:'Tour Tester',email:'test@example.test',consent_version:'v1',classes:[]}:{items:[]}});}
  const asset=/\.(js|css|png)$/.test(p);const file=path.join(assetRoot,asset?p.slice(1):'index.html');return r.fulfill({path:file,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.png')?'image/png':'text/html'});
 });return {context,page,errors,writes};
}
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||(fs.existsSync(local)?local:undefined)});try{
 for(const width of [1440,390])for(const role of ['student','teacher']){
  const {context,page,errors,writes}=await setup(browser,{width});await page.goto(base+'/?tour='+role);const card=page.locator('.tour-step-card');await card.waitFor();
  await card.getByRole('button',{name:/Auto-play/}).click();assert.equal(await card.getByRole('button',{name:/Auto-play/}).getAttribute('aria-pressed'),'false');
  const steps=role==='student'?6:4;const routes=role==='student'?['/overview','/classes','/check','/assessment','/practice','/history']:['/classes','/classes','/classes','/check'];
  let enteredEssay="";const positions=[];fs.mkdirSync(path.join(root,'.cache/tour-ui'),{recursive:true});
  for(let i=0;i<steps;i++){
   await page.waitForFunction(()=>{const c=document.querySelector('.tour-cutout');return c&&c.getBoundingClientRect().width>0&&!document.querySelector('.tour-step-card small[role=status]');});
   assert.equal(new URL(page.url()).pathname,routes[i]);assert.match(await card.innerText(),new RegExp(`Bước ${i+1}/${steps}`));
   positions.push(await page.locator('.tour-cursor').getAttribute('style'));
   if(role==='student'&&i===1){await page.waitForFunction(()=>document.querySelector('#tour-invite')?.value==='FOG1XXXX');}
   if(role==='student'&&i===2){await page.locator('[data-tour=sample-prompt-editor]').waitFor();await page.locator('[data-tour=sample-essay-editor]').waitFor();enteredEssay=await page.locator('[data-tour=sample-essay-editor]').inputValue();assert.ok(Number((await page.locator('.word-pill').innerText()).split(' ')[0])>=250);await page.locator('[data-tour=sample-active-class]').waitFor();await page.waitForFunction(()=>document.querySelector('[data-tour-active-target=sample-submit-essay]'));assert.equal(new URL(page.url()).pathname,'/check');}
   if(role==='student'&&i===4)await page.locator('[data-tour=sample-drill-feedback]').filter({hasText:'Đúng'}).waitFor();
   if(role==='teacher'&&i===2){await page.waitForFunction(()=>document.querySelector('[data-tour-active-target=teacher-score-override]'));await page.waitForFunction(()=>{const t=document.querySelector('[data-tour=teacher-score-override]')?.getBoundingClientRect();return t&&t.top>=0&&t.bottom<=innerHeight;});await page.waitForTimeout(750);}
   if(role==='teacher'&&i===3)assert.equal(await page.locator('.app-shell').getAttribute('data-route'),'check');
   if(role==='student'&&i===3){assert.ok(enteredEssay.includes(await page.locator('[data-tour=sample-error-highlight]').innerText()),'feedback quote belongs to the preceding essay');await page.locator('.tour-correction').waitFor();await page.getByText('Minimal Fix',{exact:true}).waitFor();await page.waitForFunction(()=>document.querySelector('[data-tour-active-target="sample-correction-card"]')); }
   if(role==='student'&&i===3)await page.waitForTimeout(900);
   if(role==='teacher'&&i===2)await page.screenshot({path:path.join(root,`.cache/tour-ui/teacher-${width}.png`),fullPage:false});
   if(role==='student'&&i===3)await page.screenshot({path:path.join(root,`.cache/tour-ui/student-${width}.png`),fullPage:false});
   const rect=await card.boundingBox();if(!(rect.x>=0&&rect.y>=0&&rect.x+rect.width<=width+1&&rect.y+rect.height<=901))await page.screenshot({path:path.join(root,'.cache/tour-ui/failed-layout.png')});assert.ok(rect.x>=0&&rect.y>=0&&rect.x+rect.width<=width+1&&rect.y+rect.height<=901,`card fits screen: ${role} ${width} step ${i+1} ${JSON.stringify(rect)}`);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   if(i===0){await card.getByRole('button',{name:'Tiếp theo',exact:false}).click();await card.getByRole('button',{name:'Quay lại',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.tour-step-card small[role=status]'));}
   await card.getByRole('button',{name:i===steps-1?'Hoàn tất':'Tiếp theo',exact:false}).click();
  }
  assert.ok(new Set(positions).size>1,'cursor moves between targets');await card.waitFor({state:'detached'});assert.equal(new URL(page.url()).pathname,'/');assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>Object.keys(localStorage).filter(key=>key.startsWith('fogwrite:tour_done:')).length),0);
  await page.locator('.tour-pill').click();await page.getByRole('button',{name:'Học sinh · 6 bước'}).click();await card.waitFor();await page.keyboard.press('Escape');await card.waitFor({state:'detached'});
  await context.close();console.log(`PASS ${role} tour ${width}: routes, cursor, preview, controls, exit, no mutations`);
 }
 const typed=await setup(browser);await typed.page.goto(base+'/?tour=student');await typed.page.locator('.tour-step-card').waitFor();await typed.page.locator('.tour-auto').click();await typed.page.locator('.tour-step-card').getByRole('button',{name:'Tiếp theo',exact:false}).click();await typed.page.locator('.tour-auto').click();await typed.page.locator('#tour-invite').click();await typed.page.locator('#tour-invite').fill('MYCODE99');assert.equal(await typed.page.locator('.tour-auto').getAttribute('aria-pressed'),'false');await typed.page.waitForTimeout(1500);assert.equal(await typed.page.locator('#tour-invite').inputValue(),'MYCODE99');await typed.page.keyboard.press('Escape');await typed.context.close();console.log('PASS invite typing yields to user input');
 // Authenticated persistence is scoped; anonymous demos never write a done key.
 const {context,page,errors}=await setup(browser,{user:'tour-user',reducedMotion:'reduce'});await page.goto(base+'/overview');const card=page.locator('.tour-step-card');await card.waitFor();assert.equal(await card.getByRole('button',{name:/Auto-play/}).getAttribute('aria-pressed'),'false');await page.keyboard.press('Escape');await card.waitFor({state:'detached'});
 assert.equal(await page.evaluate(()=>localStorage.getItem('fogwrite:tour_done:tour-user')),'skipped');assert.equal(await page.evaluate(()=>localStorage.getItem('fogwrite:tour_done:another-user')),null);assert.match(await page.evaluate(()=>localStorage.getItem('fogwrite:draft:tour-user')),/PRIVATE DRAFT MUST SURVIVE/);
 await page.reload();await page.getByRole('heading',{name:'Welcome to your writing studio.'}).waitFor();assert.equal(await card.count(),0);assert.deepEqual(errors,[]);await context.close();console.log('PASS authenticated auto-start, scoped persistence, reduced motion, draft preservation');
 const auto=await setup(browser);await auto.page.goto(base+'/?tour=teacher');await auto.page.locator('.tour-step-card').waitFor();await auto.page.waitForTimeout(7000);assert.match(await auto.page.locator('.tour-step-card').innerText(),/Bước 1\/4/);await auto.page.locator('.tour-step-card').hover();await auto.page.waitForTimeout(5000);assert.match(await auto.page.locator('.tour-step-card').innerText(),/Bước 1\/4/);await auto.page.mouse.move(0,0);await auto.page.getByRole('heading',{name:'Nhìn rõ học sinh trong lớp'}).waitFor({timeout:20000});await auto.page.keyboard.press('Escape');assert.deepEqual(auto.errors,[]);await auto.context.close();console.log('PASS automatic advance after target readiness');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
