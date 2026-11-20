import { useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { Notice, Spinner, criteria, band, useRequest } from "./shared";
import { AspectDiagnostics, ParagraphFeedback, LanguageSuggestions } from "./detailed";
import { PracticeWorkspace } from "./practice";
import { Frog, Brand } from "./mascot";
import { topics, wordCount, clock, annotations } from "./fogwrite-model";
import "./fogwrite.css";
const blank = { prompt: "", essay: "", topic: "", started: null, finished: null };
const key = "fogwrite.draft.v1";
const navItems = [["overview", "Overview", "\u2302"], ["topics", "Writing Practice", "\u270E"], ["check", "Check My Essay", "\u25A4"], ["skills", "Skill Practice", "\u25C7"], ["history", "History", "\u25F7"]];
function SamplePreview({ open }) {
  return <div className="sample-preview"><div className="preview-bar"><strong>Essay feedback</strong><span className="tag apricot">Sample</span></div><p className="serif">In my opinion, higher education should <mark>balance practical skills and academic knowledge.</mark></p><p className="serif">Universities can help students find employment. <mark className="warm">This idea needs a specific example.</mark></p><div className="sample-note"><span>✓</span><div><strong>A clear position. A stronger next step.</strong><p>See what works and where to develop your ideas.</p></div></div><button className="text-button" onClick={open}>Explore sample feedback →</button><Frog className="preview-frog" size={125} /></div>;
}
function Landing({ go, preview }) {
  return <div className="landing"><header className="landing-nav"><button className="brand-link" onClick={() => go("landing")}><Brand /></button><nav><a href="#how" onClick={(e) => {
    e.preventDefault();
    document.getElementById("how").scrollIntoView({ behavior: "smooth" });
  }}>How it works</a><button onClick={preview}>Sample feedback</button><button className="primary" onClick={() => go("overview")}>Open studio</button></nav></header><main><section className="hero"><div><h1>Small steps.<br />Stronger writing.</h1><p className="hero-description">A little focus. A clearer argument. A better next draft. Practise IELTS Writing Task 2 with feedback you can put to work.</p><div className="actions"><button className="primary" onClick={() => go("topics")}>Start a 40-minute practice →</button><button className="secondary" onClick={() => go("check")}>Check my essay</button></div><p className="quiet hero-foot">Your writing space, from first sentence to final revision.</p></div><SamplePreview open={preview} /></section><section id="how" className="how"><h2>A writing habit that goes somewhere.</h2><div className="steps">{[["Write", "Choose a prompt. Find your focus. Give yourself 40 minutes."], ["Understand", "Read your estimated band and feedback connected to your own words."], ["Improve", "Work on a specific skill, then bring it back to your paragraph."]].map(([t, p], i) => <article key={t}><span className="step-number">{i + 1}</span><h3>{t}</h3><p>{p}</p></article>)}</div></section><section className="landing-split"><div><Frog size={190} /><h2>Feedback with a place to start.</h2><p>See the sentence. Understand the suggestion. Try it yourself.</p></div><div className="feature-list">{[["Four criteria, clearly explained", "Explore Task Response, Coherence & Cohesion, Lexical Resource, and Grammar."], ["Your words, in context", "Find grounded quotes and language corrections alongside your essay."], ["Practice that follows your feedback", "Use focused exercises and paragraph revision to work on the skills you need."]].map(([a, b]) => <article key={a}><h3>{a}</h3><p>{b}</p></article>)}</div></section><section className="faq"><h2>A few things to know.</h2>{[["Is this an official IELTS score?", "No. FogWrite provides an AI estimate for Task 2 practice. An official IELTS result is determined by human examiners."], ["What happens after 40 minutes?", "You can submit, or continue with extra time clearly recorded in your session."], ["Will my draft be saved?", "Your draft is saved in this browser. Assessed essays are saved to the current browser session on this server."], ["Does AI help me during timed writing?", "The writing space stays focused. AI feedback and corrections appear after you submit."]].map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}</section><section className="last-cta"><div><h2>Your next draft starts here.</h2><p>One essay. One clear next step.</p></div><button className="primary" onClick={() => go("topics")}>Choose a topic →</button></section></main><footer><Brand /><span>Write. Understand. Improve.</span><small>Independent IELTS practice. AI estimates, not official results.</small></footer></div>;
}
const sampleEssay = "In my opinion, universities should balance practical skills and academic knowledge. Both approaches can prepare students for the future.\n\nAcademic subjects help students understand the principles behind their work. For example, engineering students need mathematics to evaluate whether a bridge design is safe.\n\nPractical skills also help students has better job opportunities. Universities can improve their courses to meet the needs of the job market.\n\nIn conclusion, universities should combine theoretical knowledge with practical training.";
const sampleResult = { sample: true, estimated_overall_band: 6.5, criterion_scores: { task_response: 6, coherence_cohesion: 6.5, lexical_resource: 6.5, grammatical_range_accuracy: 7 }, criterion_feedback: Object.fromEntries(criteria.map(([k]) => [k, { explanation: "Illustrative feedback to demonstrate the interface. This short sample has not been assessed by AI.", strengths: ["The essay presents a clear position."], weaknesses: ["Develop the supporting argument with a specific explanation and example."], evidence: [{ quote: "Universities can improve their courses to meet the needs of the job market.", explanation: "Explain how a course change would help students, then add a relevant example." }] }])), grammar_corrections: [{ original: "students has", corrected: "students have", explanation: "Use a plural verb with the plural subject \u201Cstudents\u201D." }], language_suggestions: [], aspect_reviews: [], paragraph_reviews: [], priority_improvements: ["Explain the connection between practical training and employability."], validation_warnings: [] };
function TopicLibrary({ choose }) {
  const [filter, setFilter] = useState("All"), [search, setSearch] = useState(""), [type, setType] = useState("All types"), [custom, setCustom] = useState(""), [own, setOwn] = useState(false), [selected, setSelected] = useState(null);
  const filtered = topics.filter((t) => (filter === "All" || t.topic === filter) && (type === "All types" || t.type === type) && t.prompt.toLowerCase().includes(search.toLowerCase()));
  return <><div className="page-heading"><div><h1>What will you write today?</h1><p>Choose a Task 2 prompt. Make a little room for progress.</p></div><button className="secondary" onClick={() => setOwn(!own)}>Use my own prompt</button></div>{own && <form className="surface own-prompt" onSubmit={(e) => {
    e.preventDefault();
    setSelected({ prompt: custom, topic: "Your prompt", type: "Custom" });
  }}><label htmlFor="own">Your Task 2 question</label><textarea id="own" required minLength={10} maxLength={3e3} rows={3} value={custom} onChange={(e) => setCustom(e.target.value)} /><button className="primary">Choose this prompt</button></form>}{selected ? <div className="surface session-start"><span className="tag">{selected.topic}</span><h2>Ready for a little focus?</h2><p className="serif">{selected.prompt}</p><p>40 minutes · Task 2 · At least 250 words. No AI hints during your session.</p><div className="actions"><button className="primary" onClick={() => choose(selected)}>Start writing</button><button className="secondary" onClick={() => setSelected(null)}>Choose another topic</button></div></div> : <button className="surprise" onClick={() => setSelected(topics[Math.floor(Math.random() * topics.length)])}><div><h2>Let a new idea find you.</h2><p>Pick a random prompt from the practice library.</p><strong>Surprise me →</strong></div><Frog size={120} /></button>}<div className="library-filters"><div className="filter-chips">{["All", ...new Set(topics.map((t) => t.topic))].map((t) => <button key={t} aria-pressed={filter === t} onClick={() => setFilter(t)}>{t}</button>)}</div><div className="actions"><label>Search prompts<input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a topic…" /></label><label>Essay type<select value={type} onChange={(e) => setType(e.target.value)}>{["All types", ...new Set(topics.map((t) => t.type))].map((t) => <option key={t}>{t}</option>)}</select></label></div></div><p className="quiet">{filtered.length} original practice prompts · Not past exam questions</p><div className="topic-grid">{filtered.map((t) => <article className="topic-card" key={t.id}><div><span className="tag">{t.topic}</span><span className="quiet">{t.type}</span></div><p>{t.prompt}</p><button className="text-button" onClick={() => {
    setSelected(t);
    window.scrollTo(0, 0);
  }}>Choose topic →</button></article>)}</div>{!filtered.length && <Notice>No prompts match. Try another topic or clear your search.</Notice>}</>;
}
function EssayEditor({ draft, setDraft, timed, busy, elapsed, error, onSubmit, experiment, setExperiment, storageError, onEdit }) {
  const [now, setNow] = useState(Date.now()), [confirming, setConfirm] = useState(false), [extra, setExtra] = useState(false);
  useEffect(() => {
    if (!timed) return;
    const id = setInterval(() => setNow(Date.now()), 1e3);
    return () => clearInterval(id);
  }, [timed]);
  const used = draft.started ? Math.floor(((draft.finished || now) - draft.started) / 1e3) : 0, remaining = 2400 - used, expired = timed && remaining <= 0, count = wordCount(draft.essay);
  const change = (field, value) => {
    onEdit();
    setDraft((d) => ({ ...d, [field]: value }));
  };
  return <><div className="page-heading"><div><h1>{timed ? "A little focus. Your own words." : "Bring your essay."}</h1><p>{timed ? "Writing Practice \xB7 Academic Task 2" : "Paste your question and response for an AI assessment."}</p></div><div className="session-indicators">{timed && <span className={`timer ${remaining <= 600 ? "urgent" : ""}`} role="timer">{expired ? "Extra time " + clock(used - 2400) : clock(remaining)}</span>}<span className="quiet">{storageError ? "Draft not saved" : "\u2713 Draft saved in this browser"}</span></div></div>{error && <Notice error>{error} Your draft is preserved. You can try submitting again.</Notice>}{storageError && <Notice error>Browser storage is unavailable. Copy your draft before leaving.</Notice>}{error && draft.finished && <button className="secondary" onClick={() => {
    setDraft((d) => ({ ...d, started: d.started ? d.started + Date.now() - d.finished : null, finished: null }));
  }}>Return to writing</button>}{busy && <div className="grading-status"><Spinner>Reviewing your essay… {elapsed}s</Spinner><p>Your ideas, organisation, vocabulary and grammar.</p></div>}{timed && remaining <= 600 && remaining > 0 && <Notice>{remaining <= 300 ? "Five minutes or less left." : "Ten minutes or less left."} Leave time to review your argument.</Notice>}{expired && !draft.finished && <Notice>Time’s up. Submit your essay, or <button className="text-button" onClick={() => setExtra(true)}>continue with extra time</button>. Extra time is recorded.</Notice>}<form onSubmit={(e) => {
    e.preventDefault();
    setConfirm(true);
  }}><div className="writing-layout"><aside className="surface prompt-panel"><span className="tag">Academic · Task 2</span><h2>Your question</h2>{timed ? <p className="serif">{draft.prompt}</p> : <label>Task question<textarea required minLength={10} maxLength={3e3} rows={8} value={draft.prompt} onChange={(e) => change("prompt", e.target.value)} disabled={busy} placeholder="Paste the complete question…" /></label>}<div className="prompt-guidance"><strong>Make your position clear.</strong><p>Support your ideas with reasons and relevant examples. Write at least 250 words.</p></div><Frog size={85} /></aside><section className="surface editor-panel"><div className="editor-toolbar"><strong>Your essay</strong><span>{count} words</span></div><label className="sr-only" htmlFor="essay">Your essay</label><textarea id="essay" className="essay-editor" required maxLength={16e3} value={draft.essay} onChange={(e) => change("essay", e.target.value)} disabled={busy || !!draft.finished || expired && !extra} placeholder="Start with an idea. Let the first sentence follow…" /><div className="editor-bottom"><span className="quiet">{count < 250 ? `${250 - count} words to reach 250` : "\u2713 250-word target reached"}</span><button className="primary" disabled={busy || !count || draft.prompt.trim().length < 10}>{busy ? "Assessing\u2026" : "Submit for assessment \u2192"}</button></div></section></div>{!timed && <details className="assessment-options"><summary>Assessment options</summary><label>Assessment method<select value={experiment} onChange={(e) => setExperiment(e.target.value)} disabled={busy}><option value="V1_STRATIFIED">Calibrated assessment</option><option value="FS0">Rubric only</option><option value="FS5_FULL">Lecturer reference assessment</option></select></label></details>}</form>{confirming && <div className="modal-backdrop"><section className="submit-dialog" role="dialog" aria-modal="true" aria-labelledby="submit-title" onKeyDown={(e) => {
    if (e.key === "Escape") setConfirm(false);
    if (e.key === "Tab") {
      e.preventDefault();
      const b = e.currentTarget.querySelectorAll("button");
      b[document.activeElement === b[0] ? 1 : 0].focus();
    }
  }}><h2 id="submit-title">Ready to review your writing?</h2><p>{count} words{timed ? ` \xB7 ${clock(used)} writing time` : ""}</p>{count < 250 && <Notice>Your response is under 250 words. You can still submit it.</Notice>}<p>Your draft will be sent to the AI assessment service.</p><div className="actions"><button autoFocus className="secondary" onClick={() => setConfirm(false)}>Keep writing</button><button className="primary" onClick={() => {
    setConfirm(false);
    onSubmit();
  }}>Assess my essay</button></div></section></div>}</>;
}
function Assessment({ result, draft, criterion, setCriterion, selected, setSelected, practice }) {
  const [view, setView] = useState("assessment");
  const marks = annotations(result, draft.essay, criterion);
  let cursor = 0;
  const chunks = [];
  for (const m of marks) {
    if (m.start < cursor) continue;
    chunks.push(draft.essay.slice(cursor, m.start));
    chunks.push(<button key={m.id} className={`annotation ${m.kind} ${selected?.id === m.id ? "selected" : ""}`} onClick={() => setSelected(m)} aria-label={`${m.kind}: ${m.quote}`}>{draft.essay.slice(m.start, m.end)}</button>);
    cursor = m.end;
  }
  chunks.push(draft.essay.slice(cursor));
  const detail = criterion ? result.criterion_feedback?.[criterion] : null;
  return <><div className="page-heading"><div><h1>Your writing, clearer.</h1><p>{result.sample ? "Sample feedback \xB7 Illustrative only" : `${result.word_count ?? wordCount(draft.essay)} words \xB7 AI assessment`}{draft.finished && draft.started ? ` \xB7 Writing time ${clock((draft.finished - draft.started) / 1e3)}` : ""}</p></div><button className="secondary" onClick={() => practice(null, null)}>Practise priority skills</button></div>{result.sample && <Notice>This is an interface example, not a real AI result. Submit your own essay to unlock personalised practice.</Notice>}<div className="feedback-layout"><section className="surface essay-review"><details className="review-prompt"><summary>View question</summary><p>{draft.prompt}</p></details><div className="legend"><span className="error-key">Errors</span><span className="suggestion-key">Suggestions</span><span className="evidence-key">Criterion evidence</span></div><div className="essay-text">{chunks}</div><p className="quiet">Select a marked passage to read its feedback. Unmarked text is not a guarantee of correctness.</p></section><aside className="surface feedback-panel">{selected ? <section className="annotation-detail"><button className="text-button" onClick={() => setSelected(null)}>← Back to {criterion ? "criterion" : "overview"}</button><span className={`tag ${selected.kind === "error" ? "rose" : ""}`}>{selected.kind === "error" ? "Language error" : selected.kind === "suggestion" ? "Optional improvement" : "Criterion evidence"}</span><blockquote>{selected.quote}</blockquote>{selected.corrected && <div className="suggested"><small>Suggested wording</small><p>{selected.corrected}</p></div>}<p>{selected.explanation}</p><button className="primary" onClick={() => practice(selected.criterion, selected)}>Practise this skill</button></section> : criterion ? <><button className="text-button" onClick={() => setCriterion(null)}>← Assessment overview</button><div className="criterion-tabs">{criteria.map(([k, s, n]) => <button key={k} aria-pressed={k === criterion} onClick={() => {
    setCriterion(k);
    setSelected(null);
  }} title={n}>{s}</button>)}</div><div className="criterion-title"><h2>{criteria.find((c) => c[0] === criterion)[2]}</h2><strong>{band(result.criterion_scores[criterion])}</strong></div><p>{detail?.explanation}</p><h3>What works</h3><ul>{detail?.strengths?.map((x) => <li key={x}>{x}</li>)}</ul><h3>Where to grow</h3><ul>{detail?.weaknesses?.map((x) => <li key={x}>{x}</li>)}</ul>{detail?.evidence?.map((e, i) => <button className="evidence-quote" key={i} onClick={() => {
    const mark = marks.find((m) => m.quote === e.quote);
    if (mark) {
      setSelected(mark);
      document.querySelector(".essay-review")?.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }}><q>{e.quote}</q><p>{e.explanation}</p></button>)}<AspectDiagnostics result={result} criterion={criterion} /><p className="quiet">Diagnostic aspect scores are learning aids, not separate official IELTS scores.</p><button className="primary" onClick={() => practice(criterion, null)}>Practise {criteria.find((c) => c[0] === criterion)[1]}</button></> : <><div className="band-summary"><span>Estimated Writing Band</span><strong>{band(result.estimated_overall_band)}</strong><p>AI estimate · Not an official IELTS score</p></div><div className="criterion-list">{criteria.map(([k, s, n]) => <button key={k} onClick={() => {
    setCriterion(k);
    setSelected(null);
  }}><span><small>{s}</small>{n}</span><strong>{band(result.criterion_scores[k])} ›</strong></button>)}</div><div className="next-step"><Frog size={65} /><p>One clear next step at a time.</p></div><h3>Start here</h3><ol>{result.priority_improvements?.map((x) => <li key={x}>{x}</li>)}</ol></>}</aside></div><div className="supplementary"><div className="filter-chips">{[["assessment", "Overview"], ["paragraphs", "Paragraph feedback"], ["language", "Language suggestions"]].map(([v, t]) => <button key={v} aria-pressed={view === v} onClick={() => setView(v)}>{t}</button>)}</div>{view === "paragraphs" && <ParagraphFeedback result={result} essay={draft.essay} />} {view === "language" && <LanguageSuggestions result={result} />}</div></>;
}
function App() {
  const [route, setRoute] = useState(location.hash.slice(1) || "landing"), [draft, setDraft] = useState(() => {
    try {
      return { ...blank, ...JSON.parse(localStorage.getItem(key) || "null") };
    } catch {
      return blank;
    }
  }), [result, setResult] = useState(null), [criterion, setCriterion] = useState(null), [selected, setSelected] = useState(null), [target, setTarget] = useState({}), [busy, setBusy] = useState(false), [error, setError] = useState(""), [elapsed, setElapsed] = useState(0), [experiment, setExperiment] = useState("V1_STRATIFIED"), [storageError, setStorageError] = useState(false), [revision, setRevision] = useState(0);
  const health = useRequest("/health"), history = useRequest("/practice/submissions?r=" + revision), restoring = useRef(false), feedbackScroll = useRef(0);
  useEffect(() => {
    const fn = () => {
      const next = location.hash.slice(1) || "landing";
      if (next === "main") {
        document.getElementById("main")?.focus();
        return;
      }
      setRoute(next);
    };
    addEventListener("hashchange", fn);
    return () => removeEventListener("hashchange", fn);
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(draft));
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  }, [draft]);
  useEffect(() => {
    if (!busy) return;
    const start = Date.now();
    setElapsed(0);
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1e3)), 1e3);
    return () => clearInterval(id);
  }, [busy]);
  useEffect(() => {
    if (route === "feedback" && feedbackScroll.current) requestAnimationFrame(() => window.scrollTo(0, feedbackScroll.current));
  }, [route]);
  useEffect(() => {
    const fn = (e) => {
      if (busy || draft.started && !draft.finished && draft.essay) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    addEventListener("beforeunload", fn);
    return () => removeEventListener("beforeunload", fn);
  }, [busy, draft]);
  useEffect(() => {
    let sid;
    try {
      sid = sessionStorage.getItem("fogwrite.assessment");
    } catch {
    }
    if (sid && ["feedback", "skills"].includes(route) && !result && !restoring.current) restore(sid);
  }, []);
  function go(next) {
    if (busy) return;
    setError("");
    if (route === "feedback") feedbackScroll.current = window.scrollY;
    location.hash = next;
    setRoute(next);
    if (next !== "feedback") window.scrollTo(0, 0);
  }
  function choose(t) {
    if (draft.essay && !confirm("Start a new session? This replaces your current browser draft. Assessed essays remain in History.")) return;
    setDraft({ ...blank, prompt: t.prompt, topic: t.topic, started: Date.now() });
    setResult(null);
    go("write");
  }
  async function evaluate() {
    if (busy) return;
    setBusy(true);
    setError("");
    const snapshot = { ...draft, finished: draft.finished || Date.now() };
    if (draft.started) setDraft(snapshot);
    try {
      const grade = await api("/writing/task2/evaluate", { method: "POST", body: JSON.stringify({ prompt: snapshot.prompt, essay: snapshot.essay, topic: snapshot.topic, source: null, experiment }) });
      try {
        sessionStorage.setItem("fogwrite.assessment", grade.submission_id);
        localStorage.setItem("fogwrite.timing." + grade.submission_id, JSON.stringify({ started: snapshot.started, finished: snapshot.finished }));
      } catch {
      }
      setResult(grade);
      setCriterion(null);
      setSelected(null);
      setRevision((x) => x + 1);
      location.hash = "feedback";
      setRoute("feedback");
      window.scrollTo(0, 0);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function restore(sid) {
    if (restoring.current || busy) return;
    if (draft.started && !draft.finished && draft.essay && !confirm("Open this assessment and replace the current browser draft?")) return;
    restoring.current = true;
    try {
      const r = await api(`/writing/task2/${sid}/submission`);
      let timing = {};
      try {
        timing = JSON.parse(localStorage.getItem("fogwrite.timing." + sid) || "{}");
        sessionStorage.setItem("fogwrite.assessment", sid);
      } catch {
      }
      setDraft({ ...blank, ...timing, prompt: r.prompt, essay: r.essay });
      setResult({ ...r.grade, submission_id: r.submission_id });
      setCriterion(null);
      setSelected(null);
      go("feedback");
    } catch (e) {
      setError(e.message);
    } finally {
      restoring.current = false;
    }
  }
  function preview() {
    if (draft.started && !draft.finished && draft.essay && !confirm("View the sample and replace the current browser draft?")) return;
    setDraft({ ...blank, prompt: topics[0].prompt, essay: sampleEssay });
    try {
      sessionStorage.removeItem("fogwrite.assessment");
    } catch {
    }
    setResult(sampleResult);
    setCriterion(null);
    setSelected(null);
    go("feedback");
  }
  function practice(c, annotation) {
    setTarget({ criterion: c ? criteria.find((x) => x[0] === c)?.[1] : null, source: annotation });
    go("skills");
  }
  function check() {
    if (draft.started && !draft.finished && draft.essay && !confirm("Leave timed practice and use this draft for essay checking? The timed session will end.")) return;
    setDraft((d) => ({ ...d, started: null, finished: null }));
    go("check");
  }
  const navigate = (r) => r === "check" ? check() : go(r);
  if (route === "landing") return <Landing go={navigate} preview={preview} />;
  return <div className="app-shell"><a className="skip-link" href="#main">Skip to content</a><aside className="sidebar"><button className="brand-link" onClick={() => go("landing")}><Brand /></button><nav aria-label="Studio">{navItems.map(([r, n, i]) => <button disabled={busy} key={r} aria-current={route === r || r === "topics" && route === "write" || r === "check" && route === "feedback" ? "page" : void 0} onClick={() => navigate(r)}><span aria-hidden="true">{i}</span>{n}</button>)}</nav><div className="sidebar-note"><Frog size={96} /><p>A little progress,<br />every time you write.</p></div><span className="connection"><i className={health.value?.model_configured ? "ready" : ""} />{health.error ? "Backend offline" : health.loading ? "Connecting\u2026" : health.value?.model_configured ? "AI connected" : "API key needed"}</span></aside><div className="app-content"><header className="app-topbar"><span>Write. Understand. Improve.</span><button className="text-button" disabled={busy} onClick={() => go("history")}>Your writing journal ↗</button></header><main id="main" tabIndex={-1}>{error && !["write", "check"].includes(route) && <Notice error>{error}</Notice>}
{route === "topics" && <TopicLibrary choose={choose} />}
{["write", "check"].includes(route) && (route === "write" && !draft.started ? <div className="empty-state"><Frog size={130} /><h1>Your next essay is waiting.</h1><button className="primary" onClick={() => go("topics")}>Choose a topic</button></div> : <EssayEditor {...{ draft, setDraft, busy, elapsed, error, onSubmit: evaluate, experiment, setExperiment, storageError, onEdit: () => { setResult(null); setSelected(null); setCriterion(null); setError(""); try { sessionStorage.removeItem("fogwrite.assessment"); } catch {} } }} timed={route === "write"} />)}
{route === "feedback" && (result ? <Assessment {...{ result, draft, criterion, setCriterion, selected, setSelected, practice }} /> : <div className="empty-state"><Frog size={130} /><h1>First, a little writing.</h1><p>Submit an essay or open an assessment from History.</p><button className="primary" onClick={() => go("history")}>Open history</button></div>)}
{route === "skills" && <><div className="page-heading"><div><button className="text-button" onClick={() => go("feedback")}>← Back to feedback</button><h1>{target.criterion ? `Practise ${target.criterion}` : "Turn feedback into progress."}</h1><p>Work on a skill. Bring it back to your writing.</p></div><Frog size={88} /></div>{target.source && <blockquote className="source-context"><small>From your essay</small><p>{target.source.quote}</p><p>{target.source.explanation}</p></blockquote>}{result?.submission_id ? <><div className="actions">{target.criterion && <button className="secondary" onClick={() => setTarget({})}>Show all priority skills</button>}</div><PracticeWorkspace key={`${result.submission_id}-${target.criterion || "all"}`} result={result} essay={draft.essay} criterion={target.criterion} sourceQuote={target.source?.quote} /></> : <div className="empty-state"><h2>Start with your own essay.</h2><p>Personalised exercises use a saved AI assessment. Sample feedback does not create practice.</p><button className="primary" onClick={check}>Check my essay</button></div>}</>}
{route === "history" && <><div className="page-heading"><div><h1>Your writing journal.</h1><p>Return to an essay. Notice what is changing.</p></div><button className="primary" onClick={() => go("topics")}>Write an essay</button></div>{history.loading ? <Spinner>Loading your essays…</Spinner> : history.error ? <Notice error>{history.error}</Notice> : history.value?.items?.length ? <div className="history-list">{history.value.items.map((item, i) => <button key={item.submission_id} onClick={() => restore(item.submission_id)}><span className="history-index">{history.value.items.length - i}</span><span><strong>{item.prompt}</strong><small>{new Date(item.created * 1e3).toLocaleString()}</small></span><span>→</span></button>)}</div> : <div className="empty-state"><Frog size={140} /><h2>A fresh page.</h2><p>Your assessed essays will appear here in this browser session.</p><button className="secondary" onClick={check}>Check your first essay</button></div>}</>}
{route === "overview" && <><div className="page-heading"><div><h1>A good day for a little progress.</h1><p>Welcome to your writing space.</p></div></div><div className="welcome-banner"><div><h2>One idea can become<br />a stronger essay.</h2><p>Choose a question and give your writing 40 minutes.</p><button className="primary" onClick={() => go("topics")}>Find my next topic →</button></div><Frog size={200} /></div><div className="overview-links"><button onClick={check}><h3>Already have an essay?</h3><p>Bring your own question and response.</p><span>Check my essay →</span></button><button onClick={() => go("history")}><h3>Pick up where you left off.</h3><p>{history.value?.items?.length ?? 0} assessed essays in this browser session.</p><span>Open writing journal →</span></button></div>{draft.essay && <div className="draft-resume"><div><h3>Your draft is here.</h3><p>{wordCount(draft.essay)} words · {draft.prompt.slice(0, 100)}</p></div><button className="secondary" onClick={() => go(draft.started ? "write" : "check")}>Continue draft</button></div>}<button className="text-button" onClick={preview}>Explore sample feedback</button></>}
{!["overview", "topics", "write", "check", "feedback", "skills", "history"].includes(route) && <div className="empty-state"><h1>This page has wandered off.</h1><button className="primary" onClick={() => go("overview")}>Back to your studio</button></div>}</main><footer className="app-footer"><span>FogWrite · IELTS Writing Studio</span><small>AI feedback for practice. Not an official IELTS result.</small></footer></div></div>;
}
createRoot(document.getElementById("root")).render(<App />);
