"""Deterministic label agreement against independently supplied reference labels."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_LIMITATIONS = [
    "Measures exact structure/status label agreement, not clinical diagnostic accuracy.",
    "Reference labels must be independently supplied and complete; omitted labels count as false positives.",
    "Confidence scores are uncalibrated model self-assessments and are not used as accuracy estimates.",
    "No true-negative universe is defined: specificity and overall diagnostic accuracy are not computed.",
    "Small or selected cohorts and subgroups cannot establish generalization or clinical safety.",
]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Cannot read valid JSON from {path}: {exc}") from exc


def _labels(value: Any, where: str) -> set[tuple[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"{where} must be a list of name/status objects")
    labels: set[tuple[str, str]] = set()
    names = set()
    for item in value:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip() for key in ("name", "status")
        ):
            raise ValueError(f"{where} requires nonempty string name and status")
        name, status = item["name"].strip().casefold(), item["status"].strip().casefold()
        if name in names:
            raise ValueError(f"{where} contains duplicate structure name: {name}")
        names.add(name)
        labels.add((name, status))
    return labels


def _metrics(tp: int, fp: int, fn: int, count: int, exact: int) -> dict[str, Any]:
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "case_count": count,
        "exact_match_count": exact,
        "exact_match_rate": exact / count if count else None,
    }


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return _metrics(
        sum(c["metrics"]["true_positives"] for c in cases),
        sum(c["metrics"]["false_positives"] for c in cases),
        sum(c["metrics"]["false_negatives"] for c in cases),
        len(cases),
        sum(c["exact_match"] for c in cases),
    )


def _label_objects(labels: set[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"name": name, "status": status} for name, status in sorted(labels)]


def _evaluate_case(entry: Any, directory: Path) -> dict[str, Any]:
    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
        raise ValueError("Each manifest case requires a nonempty string id")
    case_id = entry["id"].strip()
    report_name = entry.get("report")
    if not isinstance(report_name, str) or not report_name.strip():
        raise ValueError(f"Case {case_id} requires a report path")
    subgroup = entry.get("subgroup", "ungrouped")
    if not isinstance(subgroup, str) or not subgroup.strip():
        raise ValueError(f"Case {case_id} subgroup must be a nonempty string")
    path = Path(report_name)
    if not path.is_absolute():
        path = directory / path
    report = _read_json(path)
    if not isinstance(report, dict):
        raise ValueError(f"Case {case_id} report must be an object")
    expected = _labels(entry.get("expected"), f"Case {case_id} expected")
    actual = _labels(report.get("findings"), f"Case {case_id} findings")
    matches, unexpected, missing = expected & actual, actual - expected, expected - actual
    return {
        "id": case_id,
        "subgroup": subgroup.strip(),
        "expected": _label_objects(expected),
        "actual": _label_objects(actual),
        "matches": _label_objects(matches),
        "unexpected": _label_objects(unexpected),
        "missing": _label_objects(missing),
        "exact_match": expected == actual,
        "metrics": _metrics(len(matches), len(unexpected), len(missing), 1, int(expected == actual)),
    }


def _regressions(result: dict[str, Any], baseline: Any) -> list[dict[str, Any]]:
    if (
        not isinstance(baseline, dict)
        or baseline.get("schema_version") != 1
        or baseline.get("cohort_fingerprint") != result["cohort_fingerprint"]
    ):
        raise ValueError("Baseline must be an evaluation with the same cases, reference labels and subgroups")
    regressions = []
    scopes = [("aggregate", result["aggregate"], baseline.get("aggregate"))]
    previous_groups = baseline.get("subgroups", {})
    if not isinstance(previous_groups, dict):
        raise ValueError("Baseline subgroups must be an object")
    scopes += [(f"subgroup:{name}", values, previous_groups.get(name)) for name, values in result["subgroups"].items()]
    for scope, current, previous in scopes:
        if not isinstance(previous, dict):
            raise ValueError(f"Baseline missing metrics for {scope}")
        for key in ("true_positives", "false_positives", "false_negatives", "exact_match_count"):
            old = previous.get(key)
            if type(old) is not int or old < 0:
                raise ValueError(f"Baseline has invalid {scope}.{key}")
            decreased_is_bad = key in {"true_positives", "exact_match_count"}
            if (current[key] < old) if decreased_is_bad else (current[key] > old):
                regressions.append({"scope": scope, "metric": key, "baseline": old, "current": current[key]})
    return regressions


def evaluate_manifest(manifest: Path, baseline: Path | None = None) -> dict[str, Any]:
    """Evaluate reports without inference. Compare to a prior evaluation if supplied.

    Relative report paths resolve against the manifest's directory. Output omits
    timestamps and absolute paths for reproducibility. Missing denominators are
    represented as None, never silently scored as perfect agreement.
    """
    manifest = Path(manifest)
    entries = _read_json(manifest)
    if not isinstance(entries, list):
        raise ValueError("Manifest must be a JSON array")
    cases = sorted((_evaluate_case(entry, manifest.parent) for entry in entries), key=lambda case: case["id"])
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Manifest contains duplicate case ids")
    cohort = [{key: case[key] for key in ("id", "subgroup", "expected")} for case in cases]
    result: dict[str, Any] = {
        "schema_version": 1,
        "cohort_fingerprint": hashlib.sha256(json.dumps(cohort, sort_keys=True).encode()).hexdigest(),
        "aggregate": _aggregate(cases),
        "cases": cases,
        "subgroups": {
            group: _aggregate([case for case in cases if case["subgroup"] == group])
            for group in sorted({case["subgroup"] for case in cases})
        },
        "limitations": list(_LIMITATIONS),
        "baseline_compared": baseline is not None,
        "regressions": [],
        "passed": True,
    }
    if baseline is not None:
        result["regressions"] = _regressions(result, _read_json(Path(baseline)))
        result["passed"] = not result["regressions"]
    return result
