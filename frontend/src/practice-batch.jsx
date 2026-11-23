import { useEffect, useRef, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "./api";
import { Notice, Spinner, percent } from "./shared";
import { ExerciseLayout } from "./components/StudioScreens";

export function PracticeWorkspace({userId,result,essay,criterion,sourceQuote,clearFilter}) {
 const sid=result.submission_id,draftKey=`fogwrite:practice:${userId||'anon'}:${sid}`;
 const [batch,setBatch]=useState(null),[progress,setProgress]=useState(null),[answers,setAnswers]=useState({}),[review,setReview]=useState(null);
 const [index,setIndex]=useState(0),[tab,setTab]=useState('practice'),[state,setState]=useState('draft');
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[hint,setHint]=useState(''),[elapsed,setElapsed]=useState(0);
 const [paragraph,setParagraph]=useState(''),[revision,setRevision]=useState(''),[revisionFeedback,setRevisionFeedback]=useState(null);
 const pending=useRef(false),active=useRef(true),request=useRef(null);
 const exercises=batch?.exercises||[],current=Math.min(index,Math.max(0,exercises.length-1)),chosen=exercises[current];
 const source=batch?.errors?.find(e=>e.error_id===chosen?.source_error_id);
 const answered=exercises.filter(e=>(answers[e.exercise_id]||'').trim()).length;
 const complete=!!exercises.length&&answered===exercises.length,readonly=busy||state==='pending';
 const payload=()=>({answers:exercises.map(e=>({exercise_id:e.exercise_id,answer:answers[e.exercise_id]||''}))});
 const paragraphs=essay.split(/\r?\n(?:[ \t]*\r?\n)+/).map(p=>p.trim()).filter(Boolean);
 async function reload(){const [b,p]=await Promise.all([api(`/writing/task2/${sid}/exercises`),api(`/writing/task2/${sid}/progress`)]);if(active.current){setBatch(b);setProgress(p);}return b;}
 useEffect(()=>{
  active.current=true;let cancelled=false;
  async function load(){const b=await reload(),attempt=await api(`/writing/task2/${sid}/practice-attempt`);if(cancelled)return;
   const saved=Object.fromEntries((attempt.answers||[]).map(r=>[r.exercise_id,r.answer]));
   if(!['complete','pending'].includes(attempt.state)){try{Object.assign(saved,JSON.parse(localStorage.getItem(draftKey)||'{}'));}catch{}}
   setAnswers(Object.fromEntries((b.exercises||[]).map(e=>[e.exercise_id,saved[e.exercise_id]||''])));setReview(attempt.result||null);setState(attempt.state);
   if(sourceQuote){const i=(b.exercises||[]).findIndex(e=>b.errors?.some(r=>r.error_id===e.source_error_id&&r.original_quote.includes(sourceQuote)));if(i>=0)setIndex(i);}
  }
  load().catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});
  return()=>{cancelled=true;active.current=false;};
 },[sid]);
 useEffect(()=>{setHint('');},[chosen?.exercise_id]);
 useEffect(()=>{if(!busy)return;const start=Date.now();setElapsed(0);const t=setInterval(()=>setElapsed(Math.floor((Date.now()-start)/1000)),1000);return()=>clearInterval(t);},[busy]);
 useEffect(()=>{
  if(batch?.state!=='generating')return;
  let stopped=false;
  const poll=async()=>{
   try{
    const next=await api(`/writing/task2/${sid}/exercises`);
    if(stopped||!active.current)return;
    setBatch(next);
    if(next.state==='ready'){
     const p=await api(`/writing/task2/${sid}/progress`).catch(()=>null);
     if(!stopped&&active.current&&p)setProgress(p);
     setAnswers(prev=>Object.fromEntries((next.exercises||[]).map(e=>[e.exercise_id,prev[e.exercise_id]||''])));
    }
   }catch(e){if(!stopped&&active.current)setError(e.message);}
  };
  const timer=setInterval(poll,1500);
  return()=>{stopped=true;clearInterval(timer);};
 },[batch?.state,sid]);
 async function run(action){if(pending.current)return;pending.current=true;setBusy(true);setError('');try{await action();}catch(e){if(active.current)setError(e.message);}finally{pending.current=false;if(active.current)setBusy(false);}}
 function edit(value){const next={...answers,[chosen.exercise_id]:value};setAnswers(next);setReview(null);setState('draft');request.current=null;try{localStorage.setItem(draftKey,JSON.stringify(next));}catch{setError('Browser storage is unavailable. Save responses before leaving.');}}
 async function save(){await api(`/writing/task2/${sid}/practice-attempt`,{method:'PUT',body:JSON.stringify(payload())});}
 async function move(i){await run(async()=>{await save();setIndex(i);});}
 async function submit(){await run(async()=>{
  if(!complete)throw new Error('Finish every exercise before submitting.');const data=payload(),signature=JSON.stringify(data);
  if(request.current?.signature!==signature)request.current={signature,id:crypto.randomUUID()};
  try{const response=await api(`/writing/task2/${sid}/practice-attempt/submit`,{method:'POST',body:JSON.stringify({...data,request_id:request.current.id})});if(active.current){setReview(response);setState('complete');}await reload();}
  catch(e){const status=await api(`/writing/task2/${sid}/practice-attempt`).catch(()=>null);if(status?.state==='failed')request.current=null;if(status?.result&&active.current){setReview(status.result);setState('complete');}throw e;}
 });}
 const paragraphOptions=[...new Set((batch?.errors||[]).filter(e=>e.exercise_eligible).map(e=>e.paragraph_number))];
 return <div className="practice-workspace">
  <nav className="practice-tabs" aria-label="Learning sections">{[['practice','Exercises'],['progress','Revision & progress']].map(([key,label])=><button className={tab===key?'primary':'secondary'} key={key} onClick={()=>setTab(key)}>{label}</button>)}{(criterion||sourceQuote)&&<button className="text-button" onClick={clearFilter}>All priority skills</button>}</nav>
  {error&&<Notice error>{error}</Notice>}{(loading||busy)&&<Spinner>{loading?'Loading your practice.':`Working — ${elapsed}s`}</Spinner>}
  {state==='pending'&&!busy&&<Notice>Your complete set is being evaluated. Reload to check its status; do not submit again.</Notice>}
  {tab==='practice'&&<>
   {!loading&&batch?.state==='generating'&&<section className="empty-state surface"><h1>Preparing your practice exercises.</h1><p>Practice drills are being generated automatically in the background from your feedback.</p><Spinner>Generating practice exercises…</Spinner></section>}
   {!loading&&batch?.state!=='ready'&&batch?.state!=='generating'&&<section className="empty-state surface"><h1>Practice that follows your feedback.</h1><p>Complete every exercise, then submit the whole set for feedback.</p>{batch?.state==='failed'&&<Notice error>Automatic practice generation could not finish. You can try generating again.</Notice>}<button className="primary" disabled={busy} onClick={()=>run(async()=>{const b=await api(`/writing/task2/${sid}/exercises`,{method:'POST'});if(active.current){setBatch(b);setIndex(0);setAnswers({});setReview(null);}await reload();})}>Generate Practice Exercises <ArrowRight size={17}/></button></section>}
   {!!exercises.length&&<section className="practice-set-status surface" style={{padding:20,marginBottom:20}}><p><strong>{answered}/{exercises.length} responses written</strong> · Complete every exercise before submitting.</p><button className="secondary" disabled={readonly} onClick={()=>run(save)}>Save responses</button>{' '}<button className="primary" disabled={readonly||!complete} onClick={submit}>Submit all responses <ArrowRight size={17}/></button>{review&&<div aria-live="polite"><h2>Practice results: {review.correct_count}/{review.total} correct</h2><p>{review.summary}</p><p>Review the feedback for each exercise below.</p></div>}</section>}
   {chosen&&<ExerciseLayout deferCheck index={current} total={exercises.length} title={chosen.type==='sentence_rewriting'?'Rephrase in your own words':chosen.type==='multiple_choice'?'Choose the best fit':'Practise your writing'} source={source?.original_quote||sourceQuote||''} instruction={chosen.instruction} question={chosen.question} structurePrompt={chosen.structure_prompt} options={chosen.options} type={chosen.type} answer={answers[chosen.exercise_id]||''} setAnswer={edit} hint={hint} showHint={()=>run(async()=>{const r=await api(`/exercises/${chosen.exercise_id}/hint`,{method:'POST'});if(active.current)setHint(r.hint);})} feedback={review?.items?.find(r=>r.exercise_id===chosen.exercise_id)} busy={readonly} revision={review?()=>{setParagraph(String(source?.paragraph_number||''));setTab('progress');}:undefined}>
    <div className="exercise-navigation"><button className="secondary" disabled={readonly||current===0} onClick={()=>move(current-1)}><ChevronLeft size={16}/>Previous exercise</button><button className="secondary" disabled={readonly||current>=exercises.length-1} onClick={()=>move(current+1)}>Next exercise <ChevronRight size={16}/></button></div>
   </ExerciseLayout>}
   {!loading&&batch?.state==='ready'&&!exercises.length&&<Notice>No suitable exercises were found for this essay.</Notice>}
  </>}
  {tab==='progress'&&<section className="practice-progress surface" style={{padding:26}}><h1>Revision & progress</h1>{progress&&<><div className="metrics"><div><small>Completed correctly</small><strong>{progress.exercises_completed}/{progress.exercises_total}</strong></div><div><small>First-attempt accuracy</small><strong>{percent(progress.first_attempt_accuracy)}</strong></div><div><small>Hints used</small><strong>{progress.hints_used}</strong></div></div><p>Skills practised: {(progress.skills_practiced||[]).join(', ')||'None yet'}</p></>}
   <h2>Revise my paragraph</h2><label htmlFor="revision-paragraph">Original paragraph<select id="revision-paragraph" name="paragraph" value={paragraph} disabled={busy} onChange={e=>{setParagraph(e.target.value);setRevision('');setRevisionFeedback(null);}}><option value="">Select a paragraph</option>{paragraphOptions.map(n=><option key={n} value={n}>Paragraph {n}</option>)}</select></label>{paragraph&&<blockquote className="essay-text">{paragraphs[Number(paragraph)-1]}</blockquote>}
   <label htmlFor="revision-text">Your revision<textarea id="revision-text" name="revision" rows={6} maxLength={5000} value={revision} disabled={busy||!paragraph} onChange={e=>setRevision(e.target.value)}/></label><button className="primary" disabled={busy||!paragraph||!revision.trim()} onClick={()=>run(async()=>{const r=await api(`/writing/task2/${sid}/revision`,{method:'POST',body:JSON.stringify({paragraph_number:Number(paragraph),answer:revision,request_id:crypto.randomUUID()})});if(active.current)setRevisionFeedback(r);await reload();})}>Check revision <ArrowRight size={17}/></button>{revisionFeedback&&<Notice>{revisionFeedback.feedback.outcome}: {revisionFeedback.feedback.explanation}</Notice>}
   {progress?.revisions?.map(r=><details key={r.revision_id}><summary>Paragraph {r.paragraph_number}: {r.feedback.outcome}</summary><h3>Before</h3><p className="essay-text">{r.before}</p><h3>After</h3><p className="essay-text">{r.after}</p><p>{r.feedback.explanation}</p></details>)}
  </section>}
 </div>;
}
