import argparse
import json
from pathlib import Path

from benchmark import store
from benchmark.metrics import summarize

INTERPRETATION = (
    "MAE is the average absolute band error. RMSE gives larger misses more weight. "
    "QWK measures squared-distance-weighted agreement beyond chance and can be undefined. "
    "Exact, ±0.5, and ±1.0 are shares of valid predictions. Bias is predicted minus reference "
    "band on average. Bootstrap intervals are unstratified 95% percentile intervals "
    "over completed essays (1,000 draws, seed 42, minimum n=20)."
)


def charts(rows, summary, destination):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    valid = [row for row in rows if row["status"] == "ok"]
    if not valid:
        return
    gold = [row["gold"]["overall"] for row in valid]
    pred = [row["prediction"]["estimated_overall_band"] for row in valid]
    latencies = [row["prediction"]["provider_latency_ms"] for row in valid]

    def save(name, xlabel, ylabel):
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.tight_layout()
        plt.savefig(destination / (name + ".png"), dpi=150)
        plt.close()

    plt.scatter(gold, pred, alpha=0.4)
    plt.plot([0, 9], [0, 9], linestyle="--", color="#555")
    save("gold_vs_predicted", "Reference band", "Predicted band")
    plt.hist([b - a for a, b in zip(gold, pred)], bins=[i / 2 - .25 for i in range(-18, 20)])
    save("error_histogram", "Predicted minus reference band", "Essays")
    bands = sorted(set(gold + pred))
    matrix = [[summary["confusion"].get(str(a), {}).get(str(b), 0) for b in bands] for a in bands]
    plt.imshow(matrix, cmap="Blues")
    plt.xticks(range(len(bands)), bands)
    plt.yticks(range(len(bands)), bands)
    plt.colorbar(label="Essays")
    save("confusion_matrix", "Predicted band", "Reference band")
    for key, filename, label in [("by_band", "per_band_mae", "Reference band"), ("criteria", "criterion_mae", "Criterion")]:
        plt.bar(list(summary[key]), [s["mae"] for s in summary[key].values()])
        save(filename, label, "MAE")
    plt.hist(latencies, bins=min(12, len(valid)))
    save("latency_distribution", "Successful provider call latency (ms)", "Essays")


def report(path: Path, output: Path, lexibot_source: Path | None = None):
    meta, latest, history = store.read(path)
    summary = summarize(latest, history, meta["expected"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps({"run": meta, "summary": summary}, indent=2), encoding="utf-8")
    with (output / "attempts.jsonl").open("w", encoding="utf-8") as clean, (output / "raw_responses.jsonl").open("w", encoding="utf-8") as raw:
        for essay_id, payload, response in store.export(path):
            clean.write(payload + "\n")
            raw.write(json.dumps({"essay_id": essay_id, "response": response}, ensure_ascii=False) + "\n")
    if meta["dataset"] == "Lexibot":
        from benchmark.lexibot import OUTPUT, compare
        paired = compare(path, lexibot_source or OUTPUT)
        (output / "lexibot_comparison.json").write_text(
            json.dumps(paired, indent=2, ensure_ascii=False), encoding="utf-8",
        )
    charts(latest, summary, output)
    overall = summary["overall"]
    headline = f"# Run {meta['run_id']}\n\n"
    text = (
        headline + f"Model: {meta['model']}\n\nDataset: {meta['dataset']} ({meta['dataset_revision'] or 'revision unavailable'})\n\n"
        f"Split: {meta['split']}\n\n"
        f"Attempted: {summary['attempted']} · Completed: {summary['completed']} · Failed: {summary['failed']} · "
        f"Excluded: {summary['excluded']} · Unattempted: {summary['unattempted']}\n\n"
        f"## Overall\n\n{json.dumps(overall)}\n\n{INTERPRETATION}\n\n"
        f"## Limitations\n\n{meta['label_provenance']}\n\n"
        "See summary.json for criterion metrics, confidence intervals, operational counts, bias by band, topic and length. "
        "Account quota consumption and monetary cost are unavailable from the response. Provider attempts and reported tokens are logged. "
        "Small groups are descriptive. Length and topic associations cannot establish causation.\n"
    )
    (output / "REPORT.md").write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Export benchmark predictions, metrics, and charts.")
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lexibot-source", type=Path, help="Folder containing the normalized Lexibot references")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Benchmark database does not exist.")
    report(args.database, args.output or args.database.with_suffix(""), args.lexibot_source)


if __name__ == "__main__":
    main()
