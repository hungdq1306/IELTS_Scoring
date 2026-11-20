const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const {createHash}=require('node:crypto');
const root=path.resolve(__dirname,'..');
const deps=process.env.FOGWRITE_NODE_MODULES||path.join(root,'frontend/node_modules');
const esbuild=require(require.resolve('esbuild',{paths:[deps]}));
const React=require(require.resolve('react',{paths:[deps]}));
const {renderToStaticMarkup}=require(require.resolve('react-dom/server',{paths:[deps]}));
function load(file){const result=esbuild.buildSync({entryPoints:[path.join(root,file)],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',nodePaths:[deps],external:['react','react-dom','react/jsx-runtime']});const mod=new Module(path.join(root,file),module);mod.paths=[deps,...module.paths];mod._compile(result.outputFiles[0].text,path.join(root,file));return mod.exports;}
const {default:FrogMascot,FROG_ASSETS}=load('frontend/src/components/FrogMascot.tsx');
const {Landing,Shell,TopicLibrary,EssayEditor,Assessment,ExerciseLayout}=load('frontend/src/components/StudioScreens.jsx');
const {readRoute,pathFor}=load('frontend/src/routes.js');
const html=(component,props={})=>renderToStaticMarkup(React.createElement(component,props));
const blank={prompt:'Discuss both views and give your opinion.',essay:'Many students has useful ideas. Universities should explain them.',started:Date.now(),finished:null,extraAllowed:false};
const keys=['task_response','coherence_cohesion','lexical_resource','grammatical_range_accuracy'];
const grade={estimated_overall_band:6.5,criterion_scores:Object.fromEntries(keys.map(k=>[k,6])),criterion_feedback:Object.fromEntries(keys.map(k=>[k,{explanation:'Explain the argument clearly.',strengths:['A clear position.'],weaknesses:['Develop the supporting idea.'],evidence:[]}])),grammar_corrections:[{original:'students has',corrected:'students have',explanation:'Plural subject needs a plural verb.'}],priority_improvements:['Add an explanation and a specific example.'],validation_warnings:[],paragraph_reviews:[],aspect_reviews:[],language_suggestions:[]};
const noop=()=>{};

test('rewriting shows a structure scaffold and never presents a fixed reference answer',()=>{
 const props={type:'sentence_rewriting',source:'Source evidence.',instruction:'Rewrite in your own words.',question:'Online lessons help students learn.',structurePrompt:'Although + clause, + main clause.',answer:'My own rewrite.',setAnswer:noop,check:noop,showHint:noop,feedback:{outcome:'correct',explanation:'Meaning preserved.',correct_answer:'A hidden reference answer.'}};
 const markup=html(ExerciseLayout,props);
 assert.match(markup,/Suggested structure/);
 assert.match(markup,/Although \+ clause, \+ main clause/);
 assert.match(markup,/several valid ways/);
 assert.match(markup,/Write your own version/);
 assert.doesNotMatch(markup,/A hidden reference answer|Reference answer/);
 const free=html(ExerciseLayout,{...props,structurePrompt:''});
 assert.doesNotMatch(free,/Suggested structure/);
});

test('contextual multiple choice keeps answer options separate from the hidden key',()=>{
 const markup=html(ExerciseLayout,{type:'multiple_choice',source:'Evidence.',instruction:'Choose the best word.',question:'Researchers ___ a study.',options:['conduct','commit','attend'],answer:'',setAnswer:noop,check:noop,showHint:noop});
 assert.equal((markup.match(/type="radio"/g)||[]).length,3);
 assert.match(markup,/fits this context best/);
 assert.doesNotMatch(markup,/Reference answer|<textarea/);
});

test('complete-set exercise editor defers checking until the parent submits all responses',()=>{
 const markup=html(ExerciseLayout,{deferCheck:true,type:'sentence_rewriting',source:'Evidence.',instruction:'Rewrite.',question:'A new sentence.',answer:'My answer.',setAnswer:noop,showHint:noop});
 assert.doesNotMatch(markup,/Check answer/);
 assert.match(markup,/Show hint/);
});
test('all seven mascot variants render only local PNG images',()=>{assert.equal(Object.keys(FROG_ASSETS).length,7);for(const [variant,src] of Object.entries(FROG_ASSETS)){const markup=html(FrogMascot,{variant});assert.match(src,/^\/mascots\/frog-[a-z-]+\.png$/);assert.ok(markup.includes(`src="${src}"`));assert.match(markup,/object-contain/);assert.match(markup,/draggable="false"/);assert.doesNotMatch(markup,/<svg/);}});
test('unavailable variants have a clean badge rather than an SVG fallback',()=>{const markup=html(FrogMascot,{variant:'unavailable',alt:'Illustration unavailable'});assert.match(markup,/mascot-placeholder/);assert.doesNotMatch(markup,/<svg|<img/);});
test('sidebar contains only its logo and five navigation links',()=>{const markup=html(Shell,{route:'topics',busy:false,go:noop});const sidebar=markup.match(/<aside class="sidebar">(.*?)<\/aside>/)[1];assert.equal((sidebar.match(/data-mascot=/g)||[]).length,1);assert.match(sidebar,/data-mascot="logo"/);assert.equal((sidebar.match(/aria-current="page"/g)||[]).length,1);assert.equal((sidebar.match(/<button/g)||[]).length,6);assert.doesNotMatch(sidebar,/quiet moment|small step|Dear blank page|sidebar-note/i);});
test('all six screen layouts use their specified PNG mascot placements',()=>{const cases=[
 [Landing,{go:noop,preview:noop,signIn:noop},'writing'],[TopicLibrary,{choose:noop},'peeking'],
 [EssayEditor,{draft:blank,setDraft:noop,timed:true,busy:false,elapsed:0,onSubmit:noop,onEdit:noop,experiment:'V1_STRATIFIED',setExperiment:noop},'sleeping'],
 [Assessment,{result:grade,draft:blank,criterion:null,setCriterion:noop,selected:null,setSelected:noop,practice:noop},'encouraging'],
 [Assessment,{result:grade,draft:blank,criterion:'task_response',setCriterion:noop,selected:null,setSelected:noop,practice:noop},'pointing'],
 [ExerciseLayout,{source:'An idea from your essay',instruction:'Add an explanation and an example',question:'Explain the idea.',answer:'My revision',setAnswer:noop,check:noop,showHint:noop,feedback:{outcome:'partially_correct',explanation:'Add a more specific benefit.'}},'lilypad']
 ];for(const [Screen,props,variant] of cases){const markup=html(Screen,props);assert.ok(markup.includes(`data-mascot="${variant}"`),`${Screen.name}: ${variant}`);assert.doesNotMatch(markup,/frog-eye|frog-writing-arm|frog-face|frog-pencil|Dear blank page/);}});
test('real page URLs and legacy links resolve to all six screens',()=>{for(const route of ['landing','topics','write','feedback','skills','check','history','overview']){assert.equal(readRoute({pathname:pathFor(route),hash:''}).route,route);}for(const criterion of keys){const state=readRoute({pathname:pathFor('feedback',criterion),hash:''});assert.equal(state.criterion,criterion);assert.equal(state.route,'feedback');}assert.equal(readRoute({pathname:'/',hash:'#write'}).route,'write');assert.equal(readRoute({pathname:'/assessment/invalid',hash:''}).route,'unknown');});
test('source has no hand-drawn mascot SVG implementation',()=>{const files=[];function walk(dir){for(const name of fs.readdirSync(dir)){const file=path.join(dir,name);if(fs.statSync(file).isDirectory())walk(file);else if(/\.(?:jsx|tsx|js|ts)$/.test(name))files.push(file);}}walk(path.join(root,'frontend/src'));for(const file of files){const source=fs.readFileSync(file,'utf8');assert.doesNotMatch(source,/<svg|<path\b/,file);}});
test('assets are transparent PNGs and copied into the served build',()=>{for(const src of Object.values(FROG_ASSETS)){const publicPath=path.join(root,'frontend/public',src.slice(1));const bytes=fs.readFileSync(publicPath);assert.equal(bytes.subarray(1,4).toString(),'PNG');assert.equal(bytes[25],6,'PNG must have an RGBA channel');assert.deepEqual(fs.readFileSync(path.join(root,'frontend/dist',src.slice(1))),bytes);}});
test('HTML references the current CSS and JS build revision',()=>{const dist=path.join(root,'frontend/dist');const revision=createHash('sha256').update(fs.readFileSync(path.join(dist,'app.js'))).update(fs.readFileSync(path.join(dist,'app.css'))).digest('hex').slice(0,12);const index=fs.readFileSync(path.join(dist,'index.html'),'utf8');assert.ok(index.includes(`/app.js?v=${revision}`));assert.ok(index.includes(`/app.css?v=${revision}`));assert.match(index,/name="fogwrite-ui" content="screen-design-01"/);});
