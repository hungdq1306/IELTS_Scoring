import { useEffect, useState } from "react";
import { api } from "./api";

export const criteria = [
  ["task_response", "TR", "Task Response"],
  ["coherence_cohesion", "CC", "Coherence & Cohesion"],
  ["lexical_resource", "LR", "Lexical Resource"],
  ["grammatical_range_accuracy", "GRA", "Grammatical Range & Accuracy"],
];
export const band = value => value == null ? "—" : value.toFixed(1);
export const percent = value => value == null ? "-" : Math.round(value * 100) + "%";

export function useRequest(path, scopeKey = '') {
  const requestKey = path ? `${scopeKey}::${path}` : null;
  const [state, setState] = useState({ key: null, value: null, error: "" });
  useEffect(() => {
    if (!requestKey) {
      setState({ key: null, value: null, error: "" });
      return;
    }
    let active = true;
    const abort = new AbortController();
    api(path, { signal: abort.signal }).then(value => {
      if (active) setState({ key: requestKey, value, error: "" });
    }).catch(error => {
      if (active && error.name !== "AbortError") setState({ key: requestKey, value: null, error: error.message });
    });
    return () => { active = false; abort.abort(); };
  }, [requestKey, path]);
  return requestKey && state.key === requestKey ? state : { value: null, error: "", loading: Boolean(requestKey) };
}

export function Notice({ children, error = false }) {
  return <div className={error ? "notice error" : "notice"} role={error ? "alert" : "status"}>{children}</div>;
}

export function Spinner({ children }) {
  return <span className="progress" role="status"><span className="spin" aria-hidden="true" />{children}</span>;
}
