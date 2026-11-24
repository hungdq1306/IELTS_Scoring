const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),deps=process.env.FOGWRITE_NODE_MODULES||path.join(root,'frontend/node_modules');
const {chromium}=require(require.resolve('playwright',{paths:[deps]}));
const local='C:/Users/Lenovo/AppData/Local/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe';
const base='http://127.0.0.1:8000';
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||(fs.existsSync(local)?local:undefined)});try{
 for(const role of ['visitor','demo','student','teacher','admin'])for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();page.setDefaultTimeout(10000);
  const errors=[];let protectedCalls=0;
  page.on('pageerror',e=>errors.push(e.message));
  await context.addInitScript(()=>{for(const id of ['backend-test-only','backend-user-a','backend-user-b','guide-user'])localStorage.setItem('fogwrite:tour_done:'+id,'completed');});
 await context.addInitScript(({role})=>{window.Clerk={user:role==='visitor'?null:{id:'guide-test',fullName:'Guide Tester'},session:role==='visitor'?null:{id:'session-guide',getToken:async()=> 'fixture'},load:async()=>{},addListener:()=>()=>{},openSignIn:()=>{window.__signIn=true;}};},{role});
  await context.route('https://clerk.example.test/**',r=>r.fulfill({body:'',contentType:'text/javascript'}));
  await context.route('https://fonts.googleapis.com/**',r=>r.abort());
  await context.route(base+'/**',async r=>{
   const p=new URL(r.request().url()).pathname;
   if(p==='/api/auth/config')return r.fulfill({json:role==='demo'?{mode:'demo'}:{mode:'clerk',issuer:'https://clerk.example.test',publishable_key:'pk_test_fixture',privacy_version:'v1'}});
   if(p.startsWith('/api/')){protectedCalls++;return r.fulfill({json:p==='/api/auth/me'?{id:'guide-user',role,consent_version:'v1',classes:[]}:{items:[]}});}
   const asset=/\.(js|css|png)$/.test(p),file=path.join(root,'frontend/dist',asset?p.slice(1):'index.html');
   return r.fulfill({path:file,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.png')?'image/png':'text/html'});
  });
  await page.goto(base+'/guide');
  await page.getByRole('heading',{name:'Hướng dẫn sử dụng',exact:true}).waitFor();
  if(['student','teacher','admin'].includes(role)){assert.equal(await page.locator('.tour-launcher').count(),0);assert.equal(await page.locator('.tour-step-card').count(),0);}
  if(role==='visitor')assert.equal(protectedCalls,0,'public help must not request protected APIs');
  if(role==='demo')await page.getByText('Bạn đang xem bản demo local.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Học sinh',exact:true}).click();
  assert.equal(await page.locator('.guide-steps>li').count(),6);
  await page.getByLabel('Tìm câu hỏi').fill('Credits được');
  assert.equal(await page.locator('.guide-faq details').count(),1);
  await page.locator('.guide-faq summary').click();await page.getByText(/Lượt chấm làm mới lúc/).waitFor();
  await page.getByLabel('Tìm câu hỏi').fill('not-a-question-xyz');await page.getByText(/Chưa có câu hỏi phù hợp/).waitFor();
  await page.getByLabel('Tìm câu hỏi').fill('');
  await page.getByRole('button',{name:'Giáo viên / TA',exact:true}).click();assert.equal(await page.locator('.guide-steps>li').count(),3);
  await page.getByRole('button',{name:'Quản trị viên',exact:true}).click();assert.equal(await page.locator('.guide-steps>li').count(),3);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'help must fit mobile');
  await page.getByRole('button',{name:'Xem bài mẫu',exact:true}).click();await page.getByRole('heading',{name:'Your writing, clearer.'}).waitFor();
  await page.goto(base+'/guide');await page.getByRole('heading',{name:'Hướng dẫn sử dụng',exact:true}).waitFor();
  await page.locator('.guide-choices').getByRole('button',{name:'Check My Essay',exact:true}).click();
  if(['student','teacher','admin'].includes(role)){assert.equal(await page.locator('.tour-launcher').count(),0);assert.equal(await page.locator('.tour-step-card').count(),0);}
  if(role==='visitor')assert.equal(await page.evaluate(()=>window.__signIn),true);
  else await page.getByRole('heading',{name:'Check My Essay',exact:true}).waitFor();
  assert.deepEqual(errors,[]);await context.close();console.log(`PASS help ${role} ${width}`);
 }
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
