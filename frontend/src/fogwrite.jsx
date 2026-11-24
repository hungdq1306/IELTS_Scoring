import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { api } from "./api";
import { useRequest, Notice, Spinner } from "./shared";
import { LEGACY_DRAFT_KEYS, draftMode, draftRoute, draftStorageKey, hydrateDraft, normalizeDraft, resolveActiveClass, serializeDraft } from "./fogwrite-model";
import { readRoute, pathFor } from "./routes";
import { Brand, Landing, Shell, Overview, TopicLibrary, EssayEditor, Assessment, SampleExercise, EmptyState } from "./components/StudioScreens";
import { PracticeWorkspace } from "./practice-batch";
import "./fogwrite.css";
import {TourProvider,useTour} from "./components/tour/TourProvider";
import {TourStage} from "./components/tour/TourStage";
import {HelpGuide} from "./components/HelpGuide";
import {AuthProvider,useAuth} from "./auth-context";
import {ConsentScreen,ClassesScreen,ProfileScreen,AdminScreen} from "./components/AccountScreens";
import "./components/account-shell.css";
import {runtimeConfig,openSignIn} from "./pilot-auth";

const blank=normalizeDraft(null);
function purgeLegacyDrafts(){for(const key of LEGACY_DRAFT_KEYS){try{localStorage.removeItem(key);}catch{}}}
const sampleEssay="In my opinion, universities should balance practical skills and academic knowledge. Both approaches can prepare students for the future.\n\nOn the one hand, academic knowledge helps students develop a broad understanding of the world. For example, engineering students need mathematics to evaluate whether a bridge design is safe.\n\nOn the other hand, practical skills also help students has better job opportunities. Universities can improve their courses to meet the needs of the job market.\n\nOverall, I believe a balanced approach is the most effective, as it can equip students with both useful knowledge and real-world skills.";
const samplePrompt="Some people believe universities should focus on practical skills. Others value academic knowledge. Discuss both views and give your opinion.";
const sampleQuote="Universities can improve their courses to meet the needs of the job market.";
const sampleResult={sample:true,estimated_overall_band:6.5,criterion_scores:{task_response:6,coherence_cohesion:6.5,lexical_resource:6.5,grammatical_range_accuracy:7},criterion_feedback:{
 task_response:{explanation:"Bài viết bàn về cả hai quan điểm và nêu lập trường rõ. Ý cải thiện khóa học cần được giải thích và minh họa cụ thể hơn.",strengths:["Clearly presents your opinion and discusses both views."],weaknesses:["The idea about improving courses is too general and not fully explained."],evidence:[{quote:"universities should balance practical skills and academic knowledge",explanation:"The opening makes the writer’s position clear.",kind:"strength"},{quote:sampleQuote,explanation:"Explain how a course change helps students, then add a relevant example.",kind:"suggestion"}]},
 coherence_cohesion:{explanation:"Bài viết đi qua hai quan điểm rồi kết luận, nhưng một số liên kết ý và chi tiết hỗ trợ còn ngắn.",strengths:["Ideas are organised into clear paragraphs."],weaknesses:["Develop the link between the final supporting point and the conclusion."],evidence:[]},
 lexical_resource:{explanation:"Từ vựng truyền đạt được lập luận; một số cách diễn đạt còn chung chung và cần chính xác hơn.",strengths:["Uses relevant vocabulary about higher education."],weaknesses:["Replace general claims with more precise detail."],evidence:[]},
 grammatical_range_accuracy:{explanation:"Bài có nhiều kiểu câu. Cần kiểm tra hòa hợp chủ ngữ và động từ, chẳng hạn students has.",strengths:["Uses complex sentences to explain the academic example."],weaknesses:["A plural subject needs a plural verb."],evidence:[]}},
 grammar_corrections:[{original:"students has",corrected:"students have",explanation:"Chủ ngữ số nhiều cần động từ số nhiều.",label:"Subject-verb agreement"}],language_suggestions:[],priority_improvements:["Bổ sung lời giải thích và một ví dụ cụ thể."],validation_warnings:[],paragraph_reviews:[],aspect_reviews:[{"aspect_name": "Relevance to Prompt", "score": 6, "strength_vi": "Bài bàn về cả hai hướng đào tạo.", "weakness_vi": "Cần liên hệ rõ hơn từng ý với mục tiêu giáo dục."}, {"aspect_name": "Clarity of Position", "score": 6.5, "strength_vi": "Quan điểm kết hợp hai hướng được nêu rõ.", "weakness_vi": "Phần thân chưa giải thích sâu cách cân bằng."}, {"aspect_name": "Depth of Ideas", "score": 5.5, "strength_vi": "Có ý chính về kiến thức và việc làm.", "weakness_vi": "Ý cải thiện khóa học còn chung chung."}, {"aspect_name": "Relevant & Specific Examples", "score": 6, "strength_vi": "Ví dụ kỹ thuật liên quan đến lập luận.", "weakness_vi": "Phần kỹ năng thực hành thiếu ví dụ cụ thể."}, {"aspect_name": "Logical Organization", "score": 6.5, "strength_vi": "Hai quan điểm được chia thành các đoạn.", "weakness_vi": "Chuyển ý giữa các lợi ích còn ngắn."}, {"aspect_name": "Effective Introduction & Conclusion", "score": 6.5, "strength_vi": "Mở và kết bài thể hiện cùng một lập trường.", "weakness_vi": "Kết bài có thể tổng hợp cụ thể hơn."}, {"aspect_name": "Supported Main Points", "score": 6, "strength_vi": "Mỗi đoạn có một chủ điểm.", "weakness_vi": "Luận điểm về việc làm cần được phát triển."}, {"aspect_name": "Cohesive Devices Usage", "score": 6.5, "strength_vi": "Có các từ nối giúp theo dõi lập luận.", "weakness_vi": "Một số chuyển tiếp còn dựa vào công thức."}, {"aspect_name": "Paragraphing", "score": 6.5, "strength_vi": "Các ý được nhóm theo quan điểm.", "weakness_vi": "Độ phát triển giữa hai đoạn chưa đồng đều."}, {"aspect_name": "Vocabulary Range", "score": 6.5, "strength_vi": "Có từ vựng phù hợp về giáo dục.", "weakness_vi": "Một số cụm như improve their courses chưa cụ thể."}, {"aspect_name": "Lexical Accuracy", "score": 6.5, "strength_vi": "Ý nghĩa phần lớn rõ ràng.", "weakness_vi": "Cần diễn đạt lợi ích với độ chính xác cao hơn."}, {"aspect_name": "Spelling and Word Formation", "score": 7, "strength_vi": "Không thấy lỗi chính tả nổi bật trong ví dụ.", "weakness_vi": "Mẫu ngắn chưa thể hiện nhiều dạng từ."}, {"aspect_name": "Sentence Structure Variety", "score": 7, "strength_vi": "Có cả câu đơn và câu phức.", "weakness_vi": "Cấu trúc ở phần kết còn đơn giản."}, {"aspect_name": "Grammar Accuracy", "score": 6.5, "strength_vi": "Nhiều câu được kiểm soát tốt.", "weakness_vi": "students has cần sửa thành students have."}, {"aspect_name": "Punctuation Usage", "score": 7, "strength_vi": "Dấu câu giúp nhận biết ranh giới ý.", "weakness_vi": "Chưa có nhiều bằng chứng về cấu trúc dấu câu phức tạp."}]};

function SignInNotice({close}){
 const ref=useRef(null);
 useEffect(()=>{ref.current?.showModal();return()=>ref.current?.close();},[]);
 return <dialog className="submit-dialog" ref={ref} onCancel={close}><button className="dialog-close" onClick={close} aria-label="Close sign-in information"><X size={19}/></button><h2>Your writing stays with this browser.</h2><p>Account sign-in is not available in this pilot. You can write, receive feedback and revisit assessments in the current browser session.</p><button className="primary" autoFocus onClick={close}>Continue in this browser <ArrowRight size={16}/></button></dialog>;
}
function App(){
 const auth=useAuth();
 const tour=useTour();
 const initial=useRef(readRoute(location)).current;
 const [route,setRoute]=useState(initial.route),[criterion,setCriterionValue]=useState(initial.criterion);
 const [draft,setDraft]=useState(blank),[hydratedUserId,setHydratedUserId]=useState(null);
 const [result,setResult]=useState(null),[assessmentDraft,setAssessmentDraft]=useState(null),[selected,setSelected]=useState(null),[target,setTarget]=useState({});
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[elapsed,setElapsed]=useState(0),[experiment,setExperiment]=useState('V1_STRATIFIED'),[storageError,setStorageError]=useState(false),[revision,setRevision]=useState(0),[signIn,setSignIn]=useState(false);
 const pending=useRef(false),feedbackScroll=useRef(0),restoreOnMount=useRef(false),inflightController=useRef(null);
 const draftUserId=auth.status==='ready'?(auth.account?.id||auth.user?.id||null):auth.status==='demo'?'demo':null;
 const activeSessionRef=useRef({gen:0,userId:draftUserId});
 const activeDraft=(draftUserId&&hydratedUserId===draftUserId&&draft.userId===draftUserId)?draft:blank;
 const canRequest=!tour.isOpen&&(auth.status==='demo'||auth.status==='ready'&&!auth.needsConsent);
 const journal=useRequest(canRequest?'/practice/submissions?r='+revision:null,draftUserId||'');
 const previousAccount=useRef(undefined);
 useEffect(()=>{purgeLegacyDrafts();},[]);
 useEffect(()=>{
  if(auth.status==='loading')return;
  const id=auth.account?.id||null;
  if(previousAccount.current!==undefined&&previousAccount.current!==id){
   inflightController.current?.abort();inflightController.current=null;
   pending.current=false;setBusy(false);setError('');
   setResult(null);setAssessmentDraft(null);setSelected(null);setTarget({});
   try{sessionStorage.removeItem('fogwrite.assessment');}catch{}
  }
  previousAccount.current=id;
 },[auth.status,auth.account?.id]);
 useEffect(()=>{
  activeSessionRef.current={gen:activeSessionRef.current.gen+1,userId:draftUserId};
  inflightController.current?.abort();inflightController.current=null;
  pending.current=false;setBusy(false);setError('');
  if(!draftUserId){
   setHydratedUserId(null);setDraft(blank);return;
  }
  purgeLegacyDrafts();
  const key=draftStorageKey(draftUserId);
  let raw=null;
  try{raw=key?localStorage.getItem(key):null;}catch{raw=null;}
  setDraft(hydrateDraft(raw,draftUserId));
  setHydratedUserId(draftUserId);
 },[draftUserId]);
 useEffect(()=>{const signedOut=()=>{activeSessionRef.current={gen:activeSessionRef.current.gen+1,userId:null};inflightController.current?.abort();inflightController.current=null;pending.current=false;setBusy(false);setHydratedUserId(null);setDraft(blank);setResult(null);setAssessmentDraft(null);setSelected(null);setTarget({});try{sessionStorage.removeItem('fogwrite.assessment');}catch{}navigate('landing');};addEventListener('fogwrite:signed-out',signedOut);return()=>removeEventListener('fogwrite:signed-out',signedOut);},[]);
 useEffect(()=>{const refresh=()=>setRevision(n=>n+1);addEventListener('fogwrite:account',refresh);return()=>removeEventListener('fogwrite:account',refresh);},[]);
 useEffect(()=>{const onLocation=()=>{if(location.hash==='#main'){document.getElementById('main')?.focus();return;}const next=readRoute(location);setRoute(next.route);setCriterionValue(next.criterion);setSelected(null);};addEventListener('popstate',onLocation);addEventListener('hashchange',onLocation);return()=>{removeEventListener('popstate',onLocation);removeEventListener('hashchange',onLocation);};},[]);
 useEffect(()=>{
  if(!draftUserId||hydratedUserId!==draftUserId||draft.userId!==draftUserId)return;
  const key=draftStorageKey(draftUserId);if(!key)return;
  try{
   if(draft.prompt||draft.essay||draft.started)localStorage.setItem(key,JSON.stringify(serializeDraft(draft,draftUserId)));
   else localStorage.removeItem(key);
   setStorageError(false);
  }catch{setStorageError(true);}
 },[draft,draftUserId,hydratedUserId]);
 useEffect(()=>{if(!busy)return;const start=Date.now();setElapsed(0);const t=setInterval(()=>setElapsed(Math.floor((Date.now()-start)/1000)),1000);return()=>clearInterval(t);},[busy]);
 useEffect(()=>{const leave=e=>{if(busy||activeDraft.started&&!activeDraft.finished&&activeDraft.essay){e.preventDefault();e.returnValue='';}};addEventListener('beforeunload',leave);return()=>removeEventListener('beforeunload',leave);},[busy,activeDraft]);
 useEffect(()=>{if(!canRequest||restoreOnMount.current)return;restoreOnMount.current=true;let sid;try{sid=sessionStorage.getItem('fogwrite.assessment');}catch{}if(sid&&['feedback','skills'].includes(initial.route))restore(sid,true);},[canRequest]);
 function navigate(next,key=null){history.pushState({},'',pathFor(next,key));setRoute(next);setCriterionValue(key);setSelected(null);setError('');window.scrollTo(0,next==='feedback'?feedbackScroll.current:0);}
 function go(next){
  if(pending.current)return;
  if(route==='feedback')feedbackScroll.current=window.scrollY;
  if(next==='check'){
   if(activeDraft.started&&!activeDraft.finished&&activeDraft.essay&&!confirm('Leave timed practice and use this draft for essay checking? The timed session will end.'))return;
   setDraft(d=>({...d,userId:draftUserId,mode:'check',started:null,finished:null,remainingSec:null,updatedAt:Date.now()}));
  }else if(next==='write'&&draftMode(activeDraft)==='practice'&&!activeDraft.started&&activeDraft.remainingSec!==null){
   const duration=activeDraft.timerDurationSec||2400;
   setDraft(d=>({...d,userId:draftUserId,mode:'practice',started:Date.now()-Math.max(0,(duration-d.remainingSec)*1000)}));
  }
  navigate(next);
 }
 function continueDraft(){
  if(!activeDraft.essay||(draftUserId&&activeDraft.userId!==draftUserId))return;
  if(activeDraft.classId&&auth.user?.id&&(auth.account?.classes||[]).some(c=>c.id===activeDraft.classId&&c.active!==false)){
   try{localStorage.setItem('fogwrite.class.'+auth.user.id,activeDraft.classId);window.dispatchEvent(new Event('fogwrite:class-changed'));}catch{}
  }
  go(draftRoute(activeDraft));
 }
 function changeCriterion(key){if(pending.current)return;setCriterionValue(key);setSelected(null);history.pushState({},'',pathFor('feedback',key));}
 function clearAssessment(){setResult(null);setAssessmentDraft(null);setSelected(null);setCriterionValue(null);setTarget({});setError('');try{sessionStorage.removeItem('fogwrite.assessment');}catch{}}
 function choose(topic){
  if(pending.current)return;
  if(activeDraft.essay&&!confirm('Start a new session? This replaces your current browser draft. Assessed essays remain in History.'))return;
  clearAssessment();
  const active=resolveActiveClass(auth.account?.classes||[],auth.user?.id||'');
  const now=Date.now();
  setDraft({...blank,userId:draftUserId,mode:'practice',classId:active?.id||null,promptId:topic.id??null,prompt:topic.prompt,topic:topic.topic,started:now,timerDurationSec:2400,remainingSec:2400,updatedAt:now});
  navigate('write');
 }
 async function evaluate(){
  if(pending.current)return;
  const selectedClass=auth.status==='ready'?resolveActiveClass(auth.account?.classes||[],auth.user?.id||''):null;
  if(auth.status==='ready'&&!selectedClass){setError('Join an active class in My Classes before submitting.');return;}
  const {gen,userId}=activeSessionRef.current;
  const controller=new AbortController();
  inflightController.current=controller;
  pending.current=true;setBusy(true);setError('');
  const snapshot={...activeDraft,finished:activeDraft.finished||Date.now()};
  if(activeDraft.started)setDraft(snapshot);
  const method=auth.status==='ready'||auth.config?.mode==='clerk'?'V1_STRATIFIED':experiment;
  try{
   const grade=await api('/writing/task2/evaluate',{method:'POST',signal:controller.signal,body:JSON.stringify({prompt:snapshot.prompt,essay:snapshot.essay,topic:snapshot.topic,source:null,experiment:method,...(selectedClass?{class_id:selectedClass.id}:{})})});
   if(activeSessionRef.current.gen!==gen||activeSessionRef.current.userId!==userId)return;
   try{sessionStorage.setItem('fogwrite.assessment',grade.submission_id);localStorage.setItem('fogwrite.timing.'+grade.submission_id,JSON.stringify({started:snapshot.started,finished:snapshot.finished}));}catch{}
   setDraft(current=>current.updatedAt===snapshot.updatedAt&&current.prompt===snapshot.prompt&&current.essay===snapshot.essay?{...blank,userId}:current);
   setResult(grade);setAssessmentDraft({...snapshot,...grade.cached_content});setTarget({});setRevision(n=>n+1);feedbackScroll.current=0;navigate('feedback');
  }catch(e){
   if(e.name!=='AbortError'&&activeSessionRef.current.gen===gen&&activeSessionRef.current.userId===userId)setError(e.message);
  }finally{
   if(inflightController.current===controller)inflightController.current=null;
   if(activeSessionRef.current.gen===gen&&activeSessionRef.current.userId===userId){pending.current=false;setBusy(false);}
  }
 }
 async function restore(sid,onMount=false){
  if(pending.current)return;
  const {gen,userId}=activeSessionRef.current;
  const controller=new AbortController();
  inflightController.current=controller;
  pending.current=true;setBusy(true);setError('');
  try{
   const saved=await api('/writing/task2/'+encodeURIComponent(sid)+'/submission',{signal:controller.signal});
   if(activeSessionRef.current.gen!==gen||activeSessionRef.current.userId!==userId)return;
   let timing={};try{timing=JSON.parse(localStorage.getItem('fogwrite.timing.'+sid)||'{}');sessionStorage.setItem('fogwrite.assessment',sid);}catch{}
   const snapshot=normalizeDraft({...timing,userId,classId:saved.class_id,prompt:saved.prompt,essay:saved.essay});
   setAssessmentDraft(snapshot);setResult(saved.status==='FAILED'?{failed:true,...saved}:{...saved.grade,submission_id:saved.submission_id});setTarget({});feedbackScroll.current=0;
   if(saved.status==='FAILED')navigate('feedback');else if(onMount){setRoute(initial.route);setCriterionValue(initial.criterion);}else navigate('feedback');
  }catch(e){
   if(e.name!=='AbortError'&&activeSessionRef.current.gen===gen&&activeSessionRef.current.userId===userId)setError(e.message);
  }finally{
   if(inflightController.current===controller)inflightController.current=null;
   if(activeSessionRef.current.gen===gen&&activeSessionRef.current.userId===userId){pending.current=false;setBusy(false);}
  }
 }
 function preview(){if(pending.current)return;setAssessmentDraft({...blank,prompt:samplePrompt,essay:sampleEssay});setResult(sampleResult);setTarget({});feedbackScroll.current=0;navigate('feedback');}
 function practice(key,annotation){setTarget({criterion:key,source:annotation});go('skills');}
 function editFailed(){setDraft({...assessmentDraft,userId:draftUserId,mode:'check',started:null,finished:null,remainingSec:null,updatedAt:Date.now()});clearAssessment();navigate('check');}
 let page;
 if(route==='guide')page=<HelpGuide go={go} preview={preview}/>;
 else if(route==='overview')page=<Overview draft={activeDraft} currentUserId={draftUserId} count={journal.value?.items?.length} go={go} onContinueDraft={continueDraft} preview={preview}/>;
 else if(route==='topics')page=<TopicLibrary choose={choose}/>;
 else if(['write','check'].includes(route))page=route==='write'&&!activeDraft.started?<EmptyState title="Your next essay is waiting." text="Choose a question to start a timed writing session." action="Choose a topic" onAction={()=>go('topics')}/>:<EssayEditor {...{draft:activeDraft,setDraft,busy,elapsed,error,onSubmit:evaluate,experiment,setExperiment,storageError,onEdit:clearAssessment,go,draftUserId}} timed={route==='write'}/>;
 else if(route==='feedback')page=result?.failed?<section className="surface" style={{padding:26}}><h1>Your saved essay</h1><Notice error>{result.error_message||'AI grading could not finish.'}{result.error_code&&` (${result.error_code})`}{result.credit_refunded&&' Your grading credit was refunded.'}</Notice><h2>Task question</h2><p className="essay-text">{assessmentDraft?.prompt}</p><h2>Your essay</h2><p className="essay-text">{assessmentDraft?.essay}</p><button className="primary" onClick={editFailed}>Edit &amp; Resubmit <ArrowRight size={17}/></button></section>:result?<>{result.reused&&<Notice>{result.notice}</Notice>}<Assessment {...{result,draft:assessmentDraft||activeDraft,criterion,setCriterion:changeCriterion,selected,setSelected,practice}}/></>:<EmptyState title="First, a little writing." text="Submit an essay or open a saved assessment from History." action="Open history" onAction={()=>go('history')}/>;
 else if(route==='skills')page=<><button className="text-button back-link" onClick={()=>go('feedback')}><ArrowLeft size={16}/>Back to feedback</button>{result?.sample?<SampleExercise source={target.source?.quote} criterion={target.criterion}/>:result?.submission_id?<PracticeWorkspace key={`${draftUserId||'anon'}-${result.submission_id}-${target.criterion||'all'}-${target.source?.id||'all'}`} userId={draftUserId} result={result} essay={(assessmentDraft||activeDraft).essay} criterion={target.criterion} sourceQuote={target.source?.quote} clearFilter={()=>setTarget({})}/>:<EmptyState title="Start with your own essay." text="Personalised exercises use a saved assessment. You can also explore the labelled sample." action="Check my essay" onAction={()=>go('check')}/>}</>;
 else if(route==='classes'||route==='join')page=auth.status==='ready'?<ClassesScreen go={go}/>:<EmptyState title="Sign in to use classes."/>;
 else if(route==='profile')page=auth.status==='ready'?<ProfileScreen/>:<EmptyState title="Sign in to view your profile."/>;
 else if(route==='admin')page=<AdminScreen go={go}/>;
 else if(route==='history')page=<section data-tour="writing-journal"><div className="page-heading"><div><h1>Your writing journal.</h1><p>Return to an essay. Notice what is changing.</p></div><button className="primary" onClick={()=>go('topics')}>Write an essay <ArrowRight size={17}/></button></div>{journal.loading?<Spinner>Loading your essays…</Spinner>:journal.error?<Notice error>{journal.error}</Notice>:journal.value?.items?.length?<div className="history-list surface">{journal.value.items.map((item,i)=><button key={item.submission_id} disabled={busy} onClick={()=>restore(item.submission_id)}><span className="history-index">{journal.value.items.length-i}</span><span><strong>{item.prompt}</strong><small>{new Date(item.created*1000).toLocaleString()}</small></span><ArrowRight size={18}/></button>)}</div>:<EmptyState title="A fresh page." text="Your assessed essays will appear here in your writing journal." action="Check your first essay" onAction={()=>go('check')}/>}</section>;
 else page=<EmptyState title="This page has wandered off." text="Return to the studio to continue writing." action="Back to your studio" onAction={()=>go('overview')}/>;
 if(tour.isOpen)return <TourStage/>;
 if(auth.status==='loading')return <div className="auth-loading" role="status"><img src="/mascots/frog-logo.png" alt=""/><h1>FogWrite</h1><Spinner>Opening your writing studio…</Spinner></div>;
 if(['error','expired'].includes(auth.status))return <div className="auth-loading"><h1>Your writing is safe.</h1><Notice error>{auth.error}</Notice><button className="primary" onClick={()=>auth.retry().catch(e=>setError(e.message))}> {'Try again'}</button><button className="secondary" onClick={()=>auth.signOut().catch(e=>setError(e.message))}>Sign out</button>{error&&<Notice error>{error}</Notice>}</div>;
 if(auth.status==='visitor'&&route==='guide')return <div className="public-guide"><header className="public-guide-bar"><button onClick={()=>navigate('landing')} aria-label="FogWrite home"><Brand/></button><button className="secondary" onClick={()=>auth.signIn().catch(e=>setError(e.message))}>Sign in</button></header>{error&&<Notice error>{error}</Notice>}<HelpGuide go={go} preview={preview}/></div>;
 if(auth.status==='visitor')return route==='feedback'&&result?.sample?<div className="visitor-preview"><button className="text-button" onClick={()=>navigate('landing')}><ArrowLeft size={16}/>Back to FogWrite</button><Assessment result={result} draft={assessmentDraft} criterion={criterion} setCriterion={changeCriterion} selected={selected} setSelected={setSelected} practice={()=>auth.signIn()}/></div>:<><Landing go={next=>next==='guide'?go(next):auth.signIn().catch(e=>setError(e.message))} preview={preview} signIn={()=>auth.signIn().catch(e=>setError(e.message))}/>{error&&<Notice error>{error}</Notice>}</>;
 if(auth.status==='ready'&&auth.needsConsent)return <Shell route="consent" busy={false} go={()=>{}}><ConsentScreen/></Shell>;
 if(auth.status==='ready'&&route==='landing')page=<Overview draft={activeDraft} currentUserId={draftUserId} count={journal.value?.items?.length} go={go} onContinueDraft={continueDraft} preview={preview}/>;
 const showLanding=auth.status!=='ready'&&route==='landing';
 return <>{showLanding?<Landing go={go} preview={preview} signIn={()=>runtimeConfig().then(c=>c.mode==='clerk'?openSignIn():setSignIn(true)).catch(e=>setError(e.message))}/>:<Shell route={auth.status==='ready'&&route==='landing'?'overview':route} busy={busy} go={go}>{auth.config?.offline_preview&&<aside className="guide-demo" role="note"><strong>Offline demo</strong>Explore sample feedback, topics and saved drafts. Real AI grading and classroom accounts are unavailable in this preview.</aside>}{busy&&!['write','check'].includes(route)&&<div className="restore-status"><Spinner>Opening your assessment…</Spinner></div>}{error&&!['write','check'].includes(route)&&<Notice error>{error}</Notice>}{page}</Shell>}{signIn&&<SignInNotice close={()=>setSignIn(false)}/>}</>;
}
createRoot(document.getElementById('root')).render(<AuthProvider><TourProvider><App/></TourProvider></AuthProvider>);
