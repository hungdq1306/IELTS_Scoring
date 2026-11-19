from collections import Counter, defaultdict
from math import sqrt
from random import Random
from statistics import mean, median


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def quadratic_kappa(pairs):
    if not pairs:
        return None
    gold, predicted = zip(*pairs)
    n = len(pairs)
    observed = sum((a - b) ** 2 for a, b in pairs) / n
    gold_mean, pred_mean = mean(gold), mean(predicted)
    expected = (
        sum((value - gold_mean) ** 2 for value in gold) / n
        + sum((value - pred_mean) ** 2 for value in predicted) / n
        + (gold_mean - pred_mean) ** 2
    )
    return 1 - observed / expected if expected else None


def score_metrics(pairs):
    if not pairs:
        return {"n": 0, **dict.fromkeys(("mae", "rmse", "qwk", "exact", "within_05", "within_10", "bias", "median_absolute_error"))}
    differences = [pred - gold for gold, pred in pairs]
    n = len(differences)
    return {
        "median_absolute_error": median(map(abs, differences)),
        "n": n, "mae": mean(map(abs, differences)), "rmse": sqrt(mean(d**2 for d in differences)),
        "qwk": quadratic_kappa(pairs), "exact": differences.count(0) / n,
        "within_05": sum(abs(d) <= 0.5 for d in differences) / n,
        "within_10": sum(abs(d) <= 1 for d in differences) / n, "bias": mean(differences),
    }


def intervals(pairs, samples=1000):
    if len(pairs) < 20:
        return {}
    rng = Random(42)
    metrics = defaultdict(list)
    for _ in range(samples):
        values = score_metrics(rng.choices(pairs, k=len(pairs)))
        for key in ("mae", "rmse", "qwk", "within_05", "bias"):
            if values[key] is not None:
                metrics[key].append(values[key])
    return {key: [percentile(values, .025), percentile(values, .975)] for key, values in metrics.items()}


def summarize(latest, history, expected):
    completed = [row for row in latest if row["status"] == "ok"]
    overall = [(row["gold"]["overall"], row["prediction"]["estimated_overall_band"]) for row in completed]
    fields = {
        "tr": "task_response", "cc": "coherence_cohesion",
        "lr": "lexical_resource", "gra": "grammatical_range_accuracy",
    }
    criteria = {
        key: score_metrics([(row["gold"][key], row["prediction"]["criterion_scores"][field]) for row in completed if row["gold"].get(key) is not None])
        for key, field in fields.items()
    }
    by_band, by_length, by_topic = defaultdict(list), defaultdict(list), defaultdict(list)
    confusion = defaultdict(Counter)
    errors = Counter()
    latencies = [row["prediction"]["provider_latency_ms"] for row in completed]
    for row, (gold, pred) in zip(completed, overall):
        by_band[str(gold)].append((gold, pred))
        size = row["word_count"]
        by_length["<250" if size < 250 else "250-299" if size < 300 else "300-399" if size < 400 else "400+"].append((gold, pred))
        by_topic[row["topic"] or "Unknown"].append((gold, pred))
        confusion[str(gold)][str(pred)] += 1
        errors[str(pred - gold)] += 1

    calls = [attempt for row in history for attempt in row["attempts"]]
    attempt_status = Counter(attempt["status"] for attempt in calls)
    episode_status = Counter(row["status"] for row in history)
    usage = Counter()
    for attempt in calls:
        usage.update(attempt["usage"])

    groups = lambda mapping: {key: score_metrics(value) for key, value in sorted(mapping.items())}
    return {
        "expected": expected, "attempted": len(latest), "completed": len(completed),
        "failed": len(latest) - len(completed), "unattempted": expected - len(latest),
        "excluded": sum(row["status"] == "invalid_input" for row in latest),
        "overall": score_metrics(overall), "ci95": intervals(overall), "criteria": criteria,
        "by_band": groups(by_band), "by_length": groups(by_length), "by_topic": groups(by_topic),
        "confusion": dict(confusion), "error_histogram": dict(errors),
        "latency_ms": {"mean": mean(latencies) if latencies else None, "median": percentile(latencies, .5),
                       "p90": percentile(latencies, .9), "p95": percentile(latencies, .95)},
        "provider_attempts": len(calls), "successful_api_calls": attempt_status["ok"] + attempt_status["incomplete_output"],
        "failed_api_calls": len(calls) - attempt_status["ok"] - attempt_status["incomplete_output"],
        "rate_limit_errors": attempt_status["rate_limited"] + attempt_status["daily_quota"],
        "invalid_json": episode_status["invalid_json"], "invalid_schema": episode_status["invalid_schema"],
        "usage": dict(usage), "attempt_status": dict(attempt_status), "episode_status": dict(episode_status),
    }
