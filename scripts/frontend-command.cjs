// Prefer the normal Vite toolchain; support the repository's existing offline cache.
const path=require('node:path'),fs=require('node:fs'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),deps=process.env.FOGWRITE_NODE_MODULES||path.join(root,'.cache/pilot-ui-deps/node_modules'),mode=process.argv[2]||'dev';
const args=process.argv.slice(3);
const portOption=args.find(value=>value.startsWith('--port='));
const port=portOption?.slice(7)||(args.includes('--port')?args[args.indexOf('--port')+1]:'5173');
if(!/^\d+$/.test(port)||Number(port)<1024||Number(port)>65535)throw new Error('Use --port with a port between 1024 and 65535.');
let vite;try{vite=path.join(path.dirname(require.resolve('vite/package.json',{paths:[path.join(root,'frontend'),root]})),'bin/vite.js');}catch{}
if(vite){const result=spawnSync(process.execPath,[vite,...(mode==='build'?['build',...args]:['--host','127.0.0.1','--port',port,'--strictPort'])],{cwd:path.join(root,'frontend'),stdio:'inherit',env:process.env});process.exit(result.status??1);}
console.log('Vite is unavailable in this offline checkout. Using the existing esbuild cache; tour preview uses no backend or AI.');
process.env.FOGWRITE_NODE_MODULES=deps;
const build=spawnSync(process.execPath,[path.join(root,'scripts/build-frontend.cjs')],{cwd:root,stdio:'inherit',env:process.env});if(build.status!==0)process.exit(build.status??1);
if(mode==='build')process.exit(0);
const devRoot=path.join(root,'.cache/tour-dev');fs.mkdirSync(devRoot,{recursive:true});fs.cpSync(path.join(root,'frontend/dist'),devRoot,{recursive:true});
process.env.FOGWRITE_PREVIEW_ROOT=devRoot;process.env.FOGWRITE_PREVIEW_PORT=port;require('./preview-guide.cjs');
const esbuild=require(require.resolve('esbuild',{paths:[deps]}));
esbuild.context({entryPoints:[path.join(root,'frontend/src/fogwrite.jsx')],bundle:true,outfile:path.join(devRoot,'app.js'),nodePaths:[deps],jsx:'automatic',define:{'process.env.NODE_ENV':'"development"'},logLevel:'info'}).then(ctx=>ctx.watch()).catch(e=>{console.error(e.message);process.exit(1);});
