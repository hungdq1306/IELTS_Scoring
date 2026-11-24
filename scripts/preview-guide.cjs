// Offline UI preview: real frontend, illustrative sample only, no provider calls.
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const root=process.env.FOGWRITE_PREVIEW_ROOT||path.resolve(__dirname,'../frontend/dist'),port=Number(process.env.FOGWRITE_PREVIEW_PORT||8000);
const pages=new Set(['/','/guide','/overview','/topics','/practice','/check','/assessment','/skill-practice','/history','/classes','/join','/profile','/admin']);
http.createServer((req,res)=>{
 const json=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
 let p;try{p=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}catch{return json(400,{detail:'Invalid URL'});}
 if(p==='/api/auth/config')return json(200,{mode:'demo',offline_preview:true});
 if(p==='/api/practice/submissions')return json(200,{items:[]});
 if(p.startsWith('/api/'))return json(503,{detail:'This is an offline UI demo. Use sample feedback to explore results. Real grading requires the AI backend (RUN_FOGWRITE.cmd). Your draft is preserved.'});
 if(req.method!=='GET'&&req.method!=='HEAD')return json(405,{detail:'Read-only preview.'});
 const file=pages.has(p)||/^\/assessment\/(task-response|coherence-cohesion|lexical-resource|grammatical-range-accuracy)$/.test(p)?path.join(root,'index.html'):path.resolve(root,'.'+p);
 if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile())return json(404,{detail:'Not found.'});
 const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png','.svg':'image/svg+xml','.ico':'image/x-icon'};
 res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
 if(req.method==='HEAD')return res.end();
 fs.createReadStream(file).pipe(res);
}).listen(port,'127.0.0.1',()=>console.log(`FogWrite offline demo: http://127.0.0.1:${port}/guide`));
