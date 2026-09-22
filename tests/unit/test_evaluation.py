import json

import pytest

from medcheck.evaluation import evaluate_manifest


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _label(name, status="normal"):
    return {"name": name, "status": status}


def test_micro_metrics_and_subgroups(tmp_path, monkeypatch):
    _write(tmp_path / "a.json", {"findings": [_label(" ACL "), _label("pcl", "abnormal")]})
    _write(tmp_path / "b.json", {"findings": [_label("meniscus")]})
    manifest = _write(
        tmp_path / "manifest.json",
        [
            {"id": "b", "report": "b.json", "expected": [_label("meniscus")], "subgroup": "b"},
            {"id": "a", "report": "a.json", "expected": [_label("acl"), _label("pcl")], "subgroup": "a"},
        ],
    )
    monkeypatch.chdir(tmp_path.parent)
    result = evaluate_manifest(manifest)
    assert result["aggregate"] == {
        "true_positives": 2,
        "false_positives": 1,
        "false_negatives": 1,
        "precision": 2 / 3,
        "recall": 2 / 3,
        "f1": 2 / 3,
        "case_count": 2,
        "exact_match_count": 1,
        "exact_match_rate": 0.5,
    }
    assert result["subgroups"]["a"]["recall"] == 0.5
    assert result["cases"][0]["missing"] == [_label("pcl")]
    assert result["cases"][0]["unexpected"] == [_label("pcl", "abnormal")]
    assert result == evaluate_manifest(manifest)


def test_empty_cohort_and_empty_reference(tmp_path):
    manifest = _write(tmp_path / "manifest.json", [])
    result = evaluate_manifest(manifest)
    assert result["aggregate"]["precision"] is None
    assert result["aggregate"]["recall"] is None
    assert result["aggregate"]["exact_match_rate"] is None
    _write(tmp_path / "a.json", {"findings": []})
    _write(manifest, [{"id": "a", "report": "a.json", "expected": []}])
    result = evaluate_manifest(manifest)
    assert result["aggregate"]["f1"] is None
    assert result["cases"][0]["exact_match"]


def test_baseline_regression_and_same_cohort_requirement(tmp_path):
    report = _write(tmp_path / "a.json", {"findings": [_label("acl")]})
    manifest = _write(tmp_path / "manifest.json", [{"id": "a", "report": "a.json", "expected": [_label("acl")]}])
    baseline = _write(tmp_path / "baseline.json", evaluate_manifest(manifest))
    assert evaluate_manifest(manifest, baseline)["passed"]
    _write(report, {"findings": [_label("acl", "abnormal")]})
    result = evaluate_manifest(manifest, baseline)
    assert not result["passed"]
    assert any(r["metric"] == "false_negatives" for r in result["regressions"])
    _write(manifest, [{"id": "different", "report": "a.json", "expected": [_label("acl")]}])
    with pytest.raises(ValueError, match="same cases"):
        evaluate_manifest(manifest, baseline)


def test_subgroup_regression_not_hidden_by_aggregate(tmp_path):
    a = _write(tmp_path / "a.json", {"findings": [_label("acl")]})
    b = _write(tmp_path / "b.json", {"findings": []})
    manifest = _write(
        tmp_path / "manifest.json",
        [
            {"id": "a", "report": "a.json", "expected": [_label("acl")], "subgroup": "left"},
            {"id": "b", "report": "b.json", "expected": [_label("acl")], "subgroup": "right"},
        ],
    )
    baseline = _write(tmp_path / "baseline.json", evaluate_manifest(manifest))
    _write(a, {"findings": []})
    _write(b, {"findings": [_label("acl")]})
    result = evaluate_manifest(manifest, baseline)
    assert not result["passed"]
    assert all(r["scope"] == "subgroup:left" for r in result["regressions"])


@pytest.mark.parametrize("where", ["expected", "findings"])
def test_duplicate_structure_labels_rejected(tmp_path, where):
    labels = [_label("ACL"), _label(" acl ", "abnormal")]
    _write(tmp_path / "a.json", {"findings": labels if where == "findings" else []})
    manifest = _write(
        tmp_path / "manifest.json",
        [
            {"id": "a", "report": "a.json", "expected": labels if where == "expected" else []},
        ],
    )
    with pytest.raises(ValueError, match="duplicate structure"):
        evaluate_manifest(manifest)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        "",
        [{"id": "a", "report": "missing.json", "expected": []}],
        [{"id": "", "report": "a.json", "expected": []}],
        [{"id": "a", "report": None, "expected": []}],
        [{"id": "a", "report": "a.json", "expected": [{"name": "acl", "status": 1}]}],
    ],
)
def test_malformed_manifest_or_missing_report(tmp_path, value):
    _write(tmp_path / "a.json", {"findings": []})
    with pytest.raises(ValueError):
        evaluate_manifest(_write(tmp_path / "manifest.json", value))


def test_duplicate_case_ids(tmp_path):
    _write(tmp_path / "a.json", {"findings": []})
    case = {"id": "a", "report": "a.json", "expected": []}
    with pytest.raises(ValueError, match="duplicate case"):
        evaluate_manifest(_write(tmp_path / "manifest.json", [case, case]))


def test_invalid_json_and_report_shape(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("not JSON")
    with pytest.raises(ValueError, match="valid JSON"):
        evaluate_manifest(manifest)
    _write(tmp_path / "a.json", [])
    _write(manifest, [{"id": "a", "report": "a.json", "expected": []}])
    with pytest.raises(ValueError, match="report must be an object"):
        evaluate_manifest(manifest)


@pytest.mark.parametrize("mutation", ["subgroups", "aggregate", "negative_count", "bool_count"])
def test_corrupt_baseline_metrics_rejected(tmp_path, mutation):
    _write(tmp_path / "a.json", {"findings": []})
    manifest = _write(tmp_path / "manifest.json", [{"id": "a", "report": "a.json", "expected": []}])
    baseline = evaluate_manifest(manifest)
    if mutation == "subgroups":
        baseline["subgroups"] = []
    elif mutation == "aggregate":
        baseline["aggregate"] = None
    else:
        baseline["aggregate"]["true_positives"] = -1 if mutation == "negative_count" else True
    path = _write(tmp_path / "baseline.json", baseline)
    with pytest.raises(ValueError, match="Baseline"):
        evaluate_manifest(manifest, path)


@pytest.mark.parametrize("field,value", [("subgroup", ""), ("expected", None)])
def test_invalid_reference_definition_rejected(tmp_path, field, value):
    _write(tmp_path / "a.json", {"findings": []})
    case = {"id": "a", "report": "a.json", "expected": []}
    case[field] = value
    with pytest.raises(ValueError):
        evaluate_manifest(_write(tmp_path / "manifest.json", [case]))


def test_absolute_report_path_supported(tmp_path):
    report = _write(tmp_path / "report.json", {"findings": []})
    manifest = _write(tmp_path / "manifest.json", [{"id": "a", "report": str(report), "expected": []}])
    assert evaluate_manifest(manifest)["cases"][0]["exact_match"]
