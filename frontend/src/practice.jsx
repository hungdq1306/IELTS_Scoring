import { useEffect, useState } from "react";
import { api } from "./api";
import { Feedback, Notice, Spinner, percent } from "./shared";

const title = text => text.replaceAll("_", " ");
const id = () => crypto.randomUUID();

function ExerciseCard({ exercise, source, busy, run, reload }) {
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [hint, setHint] = useState("");
  useEffect(() => {
    let active=true;
    if (exercise.attempts) api(`/exercises/${exercise.exercise_id}/feedback`).then(r => {if(active)setFeedback(r);}).catch(()=>{});
    return () => {active=false;};
  }, [exercise.exercise_id]);
  async function check() {
    await run(async () => {
      const result=await api(`/exercises/${exercise.exercise_id}/answer`, {method:"POST", body:JSON.stringify({answer,request_id:id()})});
      setFeedback(result);await reload();
    });
  }
  return <article className="practice-card">
    <p className="meta">{title(exercise.type)} / Level {exercise.difficulty} / {title(exercise.skill)} / {exercise.attempts} attempts</p>
    {source && <details><summary>From your essay · Paragraph {source.paragraph_number}</summary><blockquote>{source.original_quote}</blockquote></details>}
    <h3>{exercise.instruction}</h3><p className="essay-text">{exercise.question}</p>
    <p className="muted">Learning objective: {exercise.learning_objective}</p>
    {exercise.type === "multiple_choice" ? <fieldset disabled={busy}><legend>Your answer</legend>
      {exercise.options.map(option => <label className="practice-option" key={option}><input type="radio" name={exercise.exercise_id} value={option} checked={answer===option} onChange={() => setAnswer(option)} /> {option}</label>)}
    </fieldset> : <label>Your response<textarea rows={exercise.type.includes("paragraph") || exercise.type==="error_imitation" ? 6 : 3} value={answer} maxLength={5000} disabled={busy} onChange={e => setAnswer(e.target.value)} placeholder={exercise.type==="error_identification" ? "Copy the phrase that contains the error." : "Write your correction or revision. Alternative valid wording is welcome."} /></label>}
    <div className="actions"><button className="primary" disabled={busy || !answer.trim()} onClick={check}>Check Answer</button>
      <button className="secondary" disabled={busy} onClick={() => run(async () => {const r=await api(`/exercises/${exercise.exercise_id}/hint`,{method:"POST"});setHint(r.hint);await reload();})}>Show Hint</button></div>
    {hint && <Notice>{hint}</Notice>}
    {feedback && <section aria-live="polite"><h3>{title(feedback.outcome)}</h3><p>{feedback.explanation}</p>
      <p><strong>Reference answer:</strong> {feedback.correct_answer}</p>
      {feedback.accepted_alternatives.length>0 && <p>Other accepted examples: {feedback.accepted_alternatives.join(" / ")}</p>}
      {feedback.suggested_improvement && <p>{feedback.suggested_improvement}</p>}
      <p className="meta">Attempt {feedback.attempt_number} · AI feedback</p>
    </section>}
  </article>;
}

export function PracticeWorkspace({ result, essay }) {
  const sid=result.submission_id;
  const [tab,setTab]=useState("feedback");
  const [batch,setBatch]=useState(null);
  const [progress,setProgress]=useState(null);
  const [index,setIndex]=useState(0);
  const [busy,setBusy]=useState(false);
  const [failure,setFailure]=useState("");
  const [elapsed,setElapsed]=useState(0);
  const [paragraph,setParagraph]=useState("");
  const [revision,setRevision]=useState("");
  const [revisionFeedback,setRevisionFeedback]=useState(null);
  const paragraphs=essay.split(/\r?\n(?:[ \t]*\r?\n)+/).map(p=>p.trim()).filter(Boolean);
  async function reload() {
    if(!sid)return;
    const [b,p]=await Promise.all([api(`/writing/task2/${sid}/exercises`),api(`/writing/task2/${sid}/progress`)]);
    setBatch(b);setProgress(p);
  }
  useEffect(()=>{let active=true;if(sid)reload().catch(e=>{if(active)setFailure(e.message);});return()=>{active=false;};},[sid]);
  useEffect(()=>{if(!busy)return;const started=Date.now();setElapsed(0);const timer=setInterval(()=>setElapsed(Math.floor((Date.now()-started)/1000)),1000);return()=>clearInterval(timer);},[busy]);
  async function run(action) {if(busy)return;setBusy(true);setFailure("");try{await action();}catch(e){setFailure(e.message);}finally{setBusy(false);}}
  const exercises=batch?.exercises || [];
  const chosen=exercises[Math.min(index,Math.max(0,exercises.length-1))];
  const paragraphOptions=[...new Set((batch?.errors || []).filter(e=>e.exercise_eligible).map(e=>e.paragraph_number))];
  return <div className="practice-workspace">
    <nav className="actions" aria-label="Learning sections">
      {[['feedback','Writing Feedback'],['practice','Practice Your Mistakes'],['progress','Revision & Progress']].map(([key,label])=><button key={key} className={tab===key ? "primary" : "secondary"} aria-current={tab===key ? "page":undefined} onClick={()=>setTab(key)}>{label}</button>)}
    </nav>
    {tab==="feedback" && <Feedback result={result} essay={essay} />}
    {tab!=="feedback" && <>
      {!sid && <Notice>This older assessment has no saved submission. Grade an essay again to enable practice.</Notice>}
      {failure && <Notice error>{failure}</Notice>}
      {busy && <Spinner>Working… {elapsed}s</Spinner>}
    </>}
    {tab==="practice" && sid && <>
      {batch?.state!=="ready" && <button className="primary" disabled={busy} onClick={()=>run(async()=>{setBatch(await api(`/writing/task2/${sid}/exercises`,{method:"POST"}));setIndex(0);await reload();})}>Generate Practice Exercises</button>}
      {batch?.message && batch.state==='failed' && <Notice error>Practice could not be generated. Please try again.</Notice>}
      {exercises.length>0 && <>
        <p>Exercise {Math.min(index+1,exercises.length)} of {exercises.length} / {progress?.exercises_completed || 0} completed</p>
        <ExerciseCard key={chosen.exercise_id} exercise={chosen} source={batch.errors.find(e=>e.error_id===chosen.source_error_id)} busy={busy} run={run} reload={reload} />
        <div className="actions"><button className="secondary" disabled={busy || index===0} onClick={()=>setIndex(index-1)}>Previous Exercise</button><button className="secondary" disabled={busy || index>=exercises.length-1} onClick={()=>setIndex(index+1)}>Next Exercise</button></div>
      </>}
      {batch?.state==="ready" && !exercises.length && <Notice>No suitable exercises found for this essay.</Notice>}
    </>}
    {tab==="progress" && sid && <>
      {progress && <>
        <div className="metrics"><div><small>Completed</small><b>{progress.exercises_completed}/{progress.exercises_total}</b></div><div><small>First-attempt accuracy</small><b>{percent(progress.first_attempt_accuracy)}</b></div><div><small>Without hints</small><b>{percent(progress.unassisted_first_attempt_accuracy)}</b></div><div><small>Hints used</small><b>{progress.hints_used}</b></div></div>
        <p>Skills practiced: {progress.skills_practiced.map(title).join(", ") || "None yet"}</p>
        <p>Skills requiring practice: {progress.skills_requiring_practice.map(title).join(", ") || "None recorded"}</p>
        <p>Errors successfully corrected in exercises: {progress.errors_successfully_corrected}</p>
        <p>Common categories: {Object.entries(progress.common_error_categories).map(([k,v])=>`${title(k)} (${v})`).join(", ") || "No approved diagnoses"}</p>
        <p>Repeated patterns in this essay: {Object.entries(progress.repeated_error_patterns).map(([k,v])=>`${title(k)} (${v})`).join(", ") || "No repeated pattern recorded"}</p>
      </>}
      <h3>Revise My Paragraph</h3>
      <label>Original paragraph<select value={paragraph} disabled={busy} onChange={e=>{setParagraph(e.target.value);setRevision("");setRevisionFeedback(null);}}><option value="">Select a paragraph</option>{paragraphOptions.map(n=><option key={n} value={n}>Paragraph {n}</option>)}</select></label>
      {paragraph && <blockquote className="essay-text">{paragraphs[Number(paragraph)-1]}</blockquote>}
      <label>Your revision<textarea rows={6} maxLength={5000} value={revision} disabled={busy || !paragraph} onChange={e=>setRevision(e.target.value)} /></label>
      <button className="primary" disabled={busy || !paragraph || !revision.trim()} onClick={()=>run(async()=>{const r=await api(`/writing/task2/${sid}/revision`,{method:"POST",body:JSON.stringify({paragraph_number:Number(paragraph),answer:revision,request_id:id()})});setRevisionFeedback(r);await reload();})}>Check Revision</button>
      {revisionFeedback && <Notice>{title(revisionFeedback.feedback.outcome)}: {revisionFeedback.feedback.explanation}</Notice>}
      {progress?.revisions?.length>0 && <><h3>Saved revisions</h3>{progress.revisions.map(r=><details key={r.revision_id}><summary>Paragraph {r.paragraph_number}: {title(r.feedback.outcome)}</summary><h4>Before</h4><p className="essay-text">{r.before}</p><h4>After</h4><p className="essay-text">{r.after}</p><p>{r.feedback.explanation}</p></details>)}</>}
    </>}
  </div>;
}
