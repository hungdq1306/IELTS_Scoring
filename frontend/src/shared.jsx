import { useEffect, useState } from "react";
import { AspectDiagnostics, LanguageSuggestions, ParagraphFeedback, WritingChecks } from "./detailed";
import { api } from "./api";

export const criteria = [
  ["task_response", "TR", "Task Response"],
  ["coherence_cohesion", "CC", "Coherence & Cohesion"],
  ["lexical_resource", "LR", "Lexical Resource"],
  ["grammatical_range_accuracy", "GRA", "Grammatical Range & Accuracy"],
];
export const splitNames = {lexibot: "Lexibot", smoke: "Smoke", dev: "Development", test_locked: "Locked test"};
export const band = value => value == null ? "—" : value.toFixed(1);
export const decimal = value => value == null ? "—" : value.toFixed(2);
export const percent = value => value == null ? "—" : Math.round(value * 100) + "%";
export const timing = value => value == null ? "—" : (value / 1000).toFixed(1) + " s";

export function useRequest(path) {
  const [state, setState] = useState({ path: null, value: null, error: "" });
  useEffect(() => {
    if (!path) return;
    const abort = new AbortController();
    api(path, { signal: abort.signal }).then(value => setState({path, value, error: ""}))
      .catch(error => {
        if (error.name !== "AbortError") setState({path, value: null, error: error.message});
      });
    return () => abort.abort();
  }, [path]);
  return state.path === path ? state : {value: null, error: "", loading: Boolean(path)};
}

export function Notice({ children, error = false }) {
  return <div className={error ? "notice error" : "notice"} role={error ? "alert" : "status"}>{children}</div>;
}

export function Spinner({ children }) {
  return <span className="progress" role="status"><span className="spin" aria-hidden="true" />{children}</span>;
}

export function ScoreStrip({ values, reference = false }) {
  return <div className="scores">{criteria.map(([key, short, name]) =>
    <div key={key} title={name}><small>{short}</small><b>{band(values[reference ? short.toLowerCase() : key])}</b></div>
  )}</div>;
}

function Points({ items, title }) {
  return items.length > 0 && <div><h4>{title}</h4><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>;
}


export function Feedback({ result, essay }) {
  const [section, setSection] = useState("assessment");
  const sections = {assessment: "Band assessment", corrections: "Language corrections", paragraphs: "Paragraph feedback", priorities: "Improvement plan"};
  return <div className="feedback">
    <WritingChecks result={result} />
    {result.validation_warnings.length > 0 && <details className="assessment-metadata"><summary>Assessment notes</summary><p>{result.validation_warnings.join(" ")}</p></details>}
    <div className="feedback-tabs" role="group" aria-label="Assessment sections">
      {Object.entries(sections).map(([key, title]) => <button key={key}
        aria-pressed={section === key} onClick={() => setSection(key)}>{title}</button>)}
    </div>
    <div className="feedback-content">
      {section === "assessment" && <div className="criterion-cards">{criteria.map(([key, short, name]) => {
        const detail = result.criterion_feedback[key];
        return <article className="criterion-card" key={key}>
          <div className="criterion-heading"><h3><span className="pill">{short}</span>{name}</h3><b>{band(result.criterion_scores[key])}<small> / 9</small></b></div>
          <p>{detail.explanation}</p>
          <div className="strength-weakness"><Points items={detail.strengths} title="Strengths" />
            <Points items={detail.weaknesses} title="Areas to improve" /></div>
          {detail.evidence.map((example, index) => <blockquote key={index}><strong>"{example.quote}"</strong><p>{example.explanation}</p></blockquote>)}
          <AspectDiagnostics result={result} criterion={key} />
        </article>;
      })}</div>}
      {section === "corrections" && <div className="language-feedback">
        <section><h3>Grammar corrections</h3>
          {result.grammar_corrections.length ? result.grammar_corrections.map((item, index) =>
            <div className="correction" key={index}>
              <div className="edit-pair"><div><small>Original wording</small><del>{item.original}</del></div>
                <div><small>Suggested correction</small><strong>{item.corrected}</strong></div></div>
              <p>{item.explanation}</p>
            </div>) : <p className="muted">No grounded grammar corrections returned.</p>}
        </section><LanguageSuggestions result={result} />
      </div>}
      {section === "paragraphs" && <ParagraphFeedback result={result} essay={essay} />}
      {section === "priorities" && <section><h3>Priority improvements</h3>
        <ol className="priority-list">{result.priority_improvements.map((item, index) => <li key={index}>{item}</li>)}</ol>
      </section>}
    </div>
    <details className="assessment-metadata"><summary>Assessment details</summary>
      <p>{result.model_version || result.model}</p><p>{result.rubric_version}</p>
      <p>{result.prompt_version} · Total processing time {timing(result.latency_ms)}</p>
    </details>
  </div>;
}
