import argparse
import csv
import json
from random import Random
from pathlib import Path
from app.config import ROOT
from benchmark import store
from benchmark.metrics import summarize, percentile, score_metrics


def paired(control, candidate):
    cm, cr, _ = store.read(control); pm, pr, _ = store.read(candidate)
    for field in ("dataset_sha256","model","split","expected","parameters","dataset","rubric_version"):
        if cm[field] != pm[field]: raise ValueError(f"Unmatched run field: {field}")
    if cm["experiment"]!="FS0" or pm["experiment"] not in {"FS1","FS2","FS5","FS5_FULL","FS5_COMPACT","FS7"}:
        raise ValueError("Paired comparison requires FS0 against a fixed few-shot configuration")
    if pm['experiment'] in {'FS5','FS5_FULL','FS5_COMPACT','FS7'} and cm['prompt_version'].split(':')[0]!=pm['prompt_version'].split(':')[0]:
        raise ValueError('FS5 comparison requires the same underlying detailed grading prompt version')
    c={r["essay_id"]:r for r in cr if r["prediction"]}
    rows=[]
    for r in pr:
        if r["essay_id"] not in c or not r["prediction"]: continue
        base=c[r["essay_id"]]
        if r["essay"]!=base["essay"] or r["gold"]!=base["gold"]: raise ValueError("Mismatched essay")
        gold=r["gold"]["overall"];b=base["prediction"]["estimated_overall_band"];p=r["prediction"]["estimated_overall_band"]
        rows.append({"essay_id":r["essay_id"],"gold":gold,"control":b,"candidate":p,
                     "control_absolute_error":abs(b-gold),"candidate_absolute_error":abs(p-gold),
                     "delta_absolute_error":abs(p-gold)-abs(b-gold)})
    deltas=[r["delta_absolute_error"] for r in rows]
    rng=Random(42)
    boots=[sum(rng.choices(deltas,k=len(deltas)))/len(deltas) for _ in range(2000)] if deltas else []
    return {"n":len(rows),"delta_mae":sum(deltas)/len(deltas) if deltas else None,
        "bootstrap95":[percentile(boots,.025),percentile(boots,.975)],
        "warning":"Exploratory, small sample; no claim of improved IELTS accuracy", "rows":rows,
        "best_cases":sorted(rows,key=lambda r:r["delta_absolute_error"])[:3],
        "worst_cases":sorted(rows,key=lambda r:r["delta_absolute_error"],reverse=True)[:3],
        "candidate_over_scored":sum(r["candidate"]>r["gold"] for r in rows),
        "candidate_under_scored":sum(r["candidate"]<r["gold"] for r in rows)}


def report():
    reports=[]
    predictions=[]
    for path in sorted((ROOT / "results").glob("fs[012]-*.sqlite3")):
        m,r,h=store.read(path)
        for row in r:
            pred=row["prediction"]
            predictions.append({"run_id":m["run_id"],"experiment":m["experiment"],"source":m["dataset"],
                "split":m["split"],"essay_id":row["essay_id"],"gold":row["gold"]["overall"],
                "prediction":pred["estimated_overall_band"] if pred else None,
                "absolute_error":abs(pred["estimated_overall_band"]-row["gold"]["overall"]) if pred else None,
                "status":row["status"],"latency_ms":pred["provider_latency_ms"] if pred else None})
        groups={"overall_outside_criterion_range":[],"overall_within_criterion_range":[]}
        versions={}
        for row in r:
            if not row["prediction"]: continue
            g=row["gold"]; vals=[g.get(k) for k in ("tr","cc","lr","gra")]
            if all(v is not None for v in vals):
                key="overall_outside_criterion_range" if not min(vals)<=g["overall"]<=max(vals) else "overall_within_criterion_range"
                groups[key].append((g["overall"],row["prediction"]["estimated_overall_band"]))
            v=row["prediction"].get("model_version") or "unreported";versions[v]=versions.get(v,0)+1
        reports.append({"path":str(path),"metadata":m,"summary":summarize(r,h,m["expected"]),
                        "label_consistency_groups":{k:score_metrics(v) for k,v in groups.items()},"response_model_versions":versions})
    comparisons=[]
    for c in reports:
        if c["metadata"]["experiment"]!="FS0":continue
        for p in reports:
            if p["metadata"]["experiment"] not in {"FS1","FS2"}:continue
            try:comparisons.append({"control":c["metadata"]["run_id"],"candidate":p["metadata"]["run_id"],**paired(Path(c["path"]),Path(p["path"]))})
            except ValueError:pass
    dest=ROOT / "results/fewshot";dest.mkdir(exist_ok=True)
    if predictions:
        with (dest / "predictions.csv").open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(predictions[0]));writer.writeheader();writer.writerows(predictions)
    (dest / "summary.json").write_text(json.dumps({"runs":reports,"paired":comparisons},indent=2),encoding="utf-8")
    lines=["# Few-shot benchmark report","","Only real stored Gemini predictions are included. Writing9 and Lexibot are proxy labels, not verified lecturer labels. Locked test remains unused.","","| Experiment | Source / split | Completed | MAE | RMSE | QWK | Within 0.5 | Mean API ms |","|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in reports:
        m,s=r["metadata"],r["summary"];o=s["overall"]
        lines.append(f"| {m['experiment']} | {m['dataset']} / {m['split']} | {s['completed']}/{s['expected']} | {o['mae']} | {o['rmse']} | {o['qwk']} | {o['within_05']} | {s['latency_ms']['mean']} |")
    lines += ["","## Paired comparisons","","Negative delta MAE favors the candidate. Bootstrap intervals are exploratory; incomplete matched samples can be biased.","", "```json",json.dumps(comparisons,indent=2),"```", "", "Complete operational counts, tokens, criterion metrics, and errors are in results/fewshot/summary.json. No configuration is automatically promoted. Review per-essay deltas sorted by magnitude for best/worst cases."]
    (ROOT / "docs/FEWSHOT_BENCHMARK_REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps([{ "run":r["metadata"]["run_id"], "completed":r["summary"]["completed"]} for r in reports]))

if __name__=="__main__":report()
