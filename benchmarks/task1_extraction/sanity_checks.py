"""No LLM calls. Check declared grids, arithmetic and unsupported process terms."""
import re
from .schemas import SanityReport, Task1ExtractionResult


def is_total(name):
    return name.strip().casefold() in {"total", "grand total"}


def run_sanity_checks(raw: Task1ExtractionResult) -> SanityReport:
    report = SanityReport(table_count=len(raw.numeric_tables))
    warnings = report.sanity_warnings
    def warn(message):
        if message not in warnings:
            warnings.append(message)
    if raw.visual_category not in {"map", "process"} and not raw.numeric_tables:
        warn("incomplete_grid_shape: numeric chart has no tables")
        report.grid_shape_valid = False
    if raw.visual_category in {"map", "process"} and not raw.spatial_or_process_steps:
        warn("missing_diagram_steps")
    if raw.visual_category in {"map", "process"} and raw.has_explicit_labels:
        warn("invalid_explicit_labels_for_diagram")
    if raw.visual_category == "mixed" and not (raw.numeric_tables or raw.spatial_or_process_steps):
        warn("empty_mixed_panels")
    if len({t.table_id for t in raw.numeric_tables}) != len(raw.numeric_tables):
        warn("duplicate_table_id")
    for table in raw.numeric_tables:
        n = len(table.columns)
        report.declared_cells += n * len(table.rows)
        report.non_null_cells += sum(v is not None for row in table.rows for v in row.values[:n])
        malformed = (not n or not table.rows or len(set(table.columns)) != n or
            len({r.series_name for r in table.rows}) != len(table.rows) or any(
                len(row.values) != n or len(row.raw_labels) != n or any(v is None for v in row.values)
                for row in table.rows))
        if malformed:
            warn(f"incomplete_grid_shape: {table.table_id}")
            report.grid_shape_valid = False
        if not n or not table.rows or any(len(r.values) != n for r in table.rows):
            continue
        total_indices = [i for i, c in enumerate(table.columns) if is_total(c)]
        regular_indices = [i for i in range(n) if i not in total_indices]
        components = [r for r in table.rows if not (r.is_total_row or is_total(r.series_name))]
        totals = [r for r in table.rows if r.is_total_row or is_total(r.series_name)]
        def sum_warning(values, where):
            if not values or any(v is None for v in values):
                return
            total = sum(values)
            if abs(total - 100) > 1.5:
                warn(f"percentage_sum_anomaly: sum={total:.1f}% ({table.table_id}, {where})")
        if table.is_percentage_distribution:
            if len(components) == 1 and len(regular_indices) > 1:
                sum_warning([components[0].values[i] for i in regular_indices], components[0].series_name)
            else:
                for i in regular_indices:
                    sum_warning([r.values[i] for r in components], table.columns[i])
        def mismatch(actual, expected):
            return abs(actual - expected) > .015 * max(abs(actual), 1e-9)
        for total_row in totals:
            for i in regular_indices:
                values = [r.values[i] for r in components]
                actual = total_row.values[i]
                if actual is not None and values and all(v is not None for v in values):
                    if mismatch(actual, sum(values)):
                        warn(f"total_row_mismatch: {table.table_id}, {table.columns[i]}: printed={actual:g}, sum={sum(values):g}")
        for i in total_indices:
            for row in table.rows:
                actual = row.values[i]
                values = [row.values[j] for j in regular_indices]
                if actual is not None and values and all(v is not None for v in values):
                    if mismatch(actual, sum(values)):
                        warn(f"total_column_mismatch: {table.table_id}, {row.series_name}: printed={actual:g}, sum={sum(values):g}")
    # A return arrow is not evidence of a closed-loop engineering mechanism.
    if raw.visual_category in {"map", "process", "mixed"}:
        labels = " ".join(label for step in raw.spatial_or_process_steps for label in step.verbatim_labels).casefold()
        descriptions = " ".join([raw.extraction_notes, *raw.key_overview_points,
            *(step.observed_change_or_action for step in raw.spatial_or_process_steps)]).casefold()
        for pattern, root in ((r"closed[- ]loop", "closed"), (r"\bpump(?:ed|ing|s)?\b", "pump"), (r"\bautomat\w*", "automat")):
            if re.search(pattern, descriptions) and root not in labels:
                warn(f"unverified_diagram_mechanism: {root}")
    return report
