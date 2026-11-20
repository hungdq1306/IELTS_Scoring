import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { Notice, ScoreStrip, Spinner, band, useRequest } from "./shared";
import { PracticeWorkspace } from "./practice";
import "./styles.css";

const empty = {prompt: "", essay: "", topic: "", source: null};
const assessmentNames = {
  V1_STRATIFIED: "Calibrated v1 · 8 Examiner Anchors (5.0–9.0)",
  FS0: "Rubric v1 Only",
  FS5: "Lecturer · Full",
  FS5_FULL: "Lecturer · Full",
  FS5_COMPACT: "Lecturer · Compact",
};
const demo = {
  prompt: "Some people believe that cities should invest more in public transport than in building new roads. To what extent do you agree or disagree?",
  essay: `Cities often have to choose between expanding their roads and improving public transport. I largely agree that investment in buses and rail should come first, although certain roads still need maintenance.

A reliable transport system lets many commuters travel in a small amount of space. During the morning rush hour, a single bus can replace dozens of cars, which makes better use of existing streets. In addition, frequent services can give people who cannot afford a car better access to jobs. These benefits depend on practical details such as travel times, affordable fares and routes that connect residential areas with places of employment.

New roads can ease particular bottlenecks. For example, a short bypass may allow delivery trucks to avoid a congested town centre. However, large expansions can also make driving more attractive and eventually bring more traffic back onto the network. If a city mainly spends its transport budget on road capacity, its residents may have few realistic alternatives when traffic grows again.

There is also a case for treating the two forms of investment as complementary. Roads already carry emergency vehicles, delivery trucks and buses. Maintaining these routes is essential, and bus lanes on existing roads can improve reliability without needing a new rail line. Cities should therefore consider which project will move more people safely and reliably within the available budget.

In conclusion, public transport should receive the larger share of investment because it can increase access and use urban space more efficiently. Targeted road improvements still have a role when they solve a clearly identified problem.`,
  topic: "", source: null
};

function Live({ draft, setDraft, result, evaluating, failure, evaluate, setResult, setFailure, experiment, setExperiment }) {
  const [elapsed, setElapsed] = useState(0);
  const lecturer = useRequest("/fewshot/lecturer/status");
  const lecturerAvailable = lecturer.value?.validation_status !== "reference_dataset_unavailable_or_invalid"
    && (lecturer.value?.production_fewshot_ready || lecturer.value?.diagnostic_allowed);
  useEffect(() => {
    if (!evaluating) return;
    const started = Date.now();
    setElapsed(0);
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [evaluating]);
  const count = draft.essay.match(/[\p{L}\p{N}]+(?:['\u2019-][\p{L}\p{N}]+)*/gu)?.length ?? 0;
  const edit = (key, value) => {
    setDraft({...draft, [key]: value, source: null});
    setResult(null);
    setFailure("");
  };
  function reset(value) {
    setDraft(value);
    setResult(null);
    setFailure("");
  }
  return <div className={result ? "workspace live-assessed" : "workspace"}>
    <form className="panel editor" onSubmit={event => { event.preventDefault(); evaluate(draft); }}>
      <div className="panel-head"><div><h2>Essay submission</h2><p>Submit your response for criterion scores and detailed writing feedback.</p></div>
        <button type="button" className="secondary" onClick={() => reset(demo)} disabled={evaluating}>Load sample</button></div>
      <label>Assessment method
        <select value={experiment} disabled={evaluating} onChange={e => {setExperiment(e.target.value); setResult(null); setFailure("");}}>
          <option value="V1_STRATIFIED">Calibrated v1 · 8 Examiner Anchors (5.0–9.0)</option>
          <option value="FS0">Rubric v1 Only</option>
          <option value="FS5_FULL" disabled={!lecturerAvailable}>Lecturer · 5-Shot (5.0–8.0)</option>
        </select>
      </label>
      {lecturer.value && !lecturer.value.production_fewshot_ready && <p className="muted">{lecturer.value.diagnostic_allowed ? "Lecturer assessment is in preview." : "Lecturer assessment is awaiting reference verification."}</p>}
      {lecturer.error && <Notice error>Lecturer methods are unavailable. Rubric Only is still available.</Notice>}
      <label htmlFor="question">Task question</label>
      <textarea id="question" rows="3" value={draft.prompt} onChange={e => edit("prompt", e.target.value)} placeholder="Paste the exact question here..." required minLength={10} maxLength={3000} disabled={evaluating} />
      <label htmlFor="essay">Your essay</label>
      <textarea id="essay" className="essay-editor" rows="12" value={draft.essay} onChange={e => edit("essay", e.target.value)} placeholder="Write or paste your response..." required maxLength={16000} disabled={evaluating} />
      <div className="wordline"><span>{count} {count === 1 ? "word" : "words"}</span><span>Task target 250+ words</span></div>
      <div className="actions">
        <button type="submit" className="primary" disabled={evaluating || draft.prompt.trim().length < 10 || !count}>
          {evaluating ? <Spinner>Grading essay...</Spinner> : "Evaluate essay"}
        </button>
        <button type="button" className="secondary" onClick={() => reset(empty)} disabled={evaluating}>Clear</button>
      </div>
    </form>
    <section className="panel assessment" aria-busy={evaluating}>
      <div className="panel-head"><div><h2>Assessment</h2><p>Four criterion bands, writing diagnostics and paragraph feedback.</p></div></div>
      {failure && <><Notice error>{failure}</Notice><button type="button" className="secondary" disabled={evaluating} onClick={() => evaluate(draft)}>Try again</button></>}
      {evaluating && <div className="placeholder"><Spinner>Assessing your essay…</Spinner><p className="muted">{elapsed} seconds</p></div>}
      {!evaluating && !result && !failure && <div className="placeholder"><span className="paper-mark" aria-hidden="true">W</span><h3>Your assessment will appear here</h3><p>Submit an essay to see your estimated band and next steps.</p></div>}
      {result && <>
        <div className="band-hero">
          <div>
            <small>Estimated Task 2 band</small>
            <div className="band-score-row">
              <b>{band(result.estimated_overall_band)}</b>
              <span className="band-margin"> ± 0.5</span>
              <span> / 9</span>
            </div>
          </div>
          <span>AI estimate</span>
        </div>
        <p className="band-disclaimer">{result.confidence?.note || "AI estimate (±0.5 band): actual IELTS scores depend on human examiner judgment."}</p>
        <p className="meta">{assessmentNames[result.fewshot_config] || "Saved assessment"} · {(result.latency_ms / 1000).toFixed(1)} s{result.reference_example_ids?.length ? ` · ${result.reference_example_ids.length} lecturer examples` : ""}</p>
        {result.diagnostic_mode && <Notice>Preview assessment · some reference questions are unverified.</Notice>}
        <ScoreStrip values={result.criterion_scores} />
        <PracticeWorkspace key={result.submission_id || result.saved_run_id || result.latency_ms} result={result} essay={draft.essay} />
      </>}
    </section>
  </div>;
}

function Studio() {
  const [experiment, setExperiment] = useState("V1_STRATIFIED");
  const [draft, setDraft] = useState(empty);
  const [result, setResult] = useState(null);
  const [evaluating, setEvaluating] = useState(false);
  const [failure, setFailure] = useState("");
  const health = useRequest("/health");
  const saved = useRequest("/practice/submissions?r=" + (result?.submission_id || ""));
  const [restoreError, setRestoreError] = useState("");
  async function restore(sid) {
    if (!sid) return;
    setRestoreError("");
    try {
      const r = await api(`/writing/task2/${sid}/submission`);
      setDraft({prompt: r.prompt, essay: r.essay, topic: "", source: null});
      setResult({...r.grade, submission_id: r.submission_id});
      setExperiment(
        r.grade.fewshot_config === "V1_STRATIFIED"
          ? "V1_STRATIFIED"
          : r.grade.fewshot_config === "FS0"
            ? "FS0"
            : r.grade.fewshot_config?.startsWith("FS5")
              ? "FS5_FULL"
              : "V1_STRATIFIED"
      );
    } catch (e) {
      setRestoreError(e.message);
    }
  }

  async function evaluate(essay) {
    setResult(null);
    setFailure("");
    setEvaluating(true);
    try {
      const {prompt, essay: text, topic, source} = essay;
      setResult(await api("/writing/task2/evaluate", {
        method: "POST", body: JSON.stringify({prompt, essay: text, topic, source, experiment}),
      }));
    } catch (error) {
      setFailure(error.message);
    } finally {
      setEvaluating(false);
    }
  }
  return <>
    <header className="top"><div className="top-inner">
      <div className="brand"><span className="brand-icon" aria-hidden="true">W</span><span>Writing Studio</span></div>
      <span className="connection"><i className={health.value?.model_configured ? "ready" : ""} />
        {health.error ? "Offline" : health.loading ? "Connecting" : health.value?.model_configured ? "Ready" : "Setup required"}</span>
    </div></header>
    <main>
      {saved.value?.items.length > 0 && <label>Restore a saved assessment<select value="" disabled={evaluating} onChange={e => restore(e.target.value)}><option value="">Select an assessment from this browser session</option>{saved.value.items.map(item => <option value={item.submission_id} key={item.submission_id}>{new Date(item.created * 1000).toLocaleString()} / {item.prompt.slice(0, 80)}</option>)}</select></label>}
      {restoreError && <Notice error>{restoreError}</Notice>}
      <div className="intro"><p>IELTS Academic / Writing Task 2</p><h1>Writing assessment</h1></div>
      <Live {...{draft, setDraft, result, setResult, evaluating, failure, setFailure, evaluate, experiment, setExperiment}} />
    </main>
    <footer>Writing Studio  /  IELTS Task 2 practice and evaluation</footer>
  </>;
}

createRoot(document.getElementById("root")).render(<Studio />);
