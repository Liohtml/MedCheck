# Report regression evaluation

Evaluate saved JSON reports against independently supplied reference labels.
This operation never calls an LLM, creates reference labels, or transmits data.
Keep the reference cohort fixed when comparing pipeline or model versions.

Create a JSON manifest:

```json
[
  {
    "id": "case-001",
    "report": "reports/case-001.json",
    "subgroup": "knee",
    "expected": [
      {"name": "ACL", "status": "normal"},
      {"name": "PCL", "status": "abnormal"}
    ]
  }
]
```

Report paths resolve relative to the manifest directory, regardless of the
working directory. Absolute paths are accepted for trusted local manifests.
Each report must contain a `findings` array of objects with nonempty `name` and
`status` strings. Case IDs and structure names within each case must be unique.
Duplicate/conflicting labels are rejected, including names that differ only by
case or surrounding whitespace. `expected` must be supplied explicitly; an
empty list means there are no expected labels, not an unlabelled case.

```bash
medcheck evaluate manifest.json --output evaluation.json
medcheck evaluate manifest.json --output candidate.json --baseline evaluation.json
```

For Python usage:

```python
from pathlib import Path
from medcheck.evaluation import evaluate_manifest

result = evaluate_manifest(Path("manifest.json"), baseline=Path("evaluation.json"))
```

## Interpretation

Names and statuses are compared after stripping surrounding whitespace and
Unicode case folding. There is no synonym matching, inference or free-text
interpretation. Every exact `(name, status)` match counts as one true positive;
an unexpected pair counts as a false positive and a missing reference pair as a
false negative. A wrong status for the right structure therefore produces both
one false positive and one false negative. These are **label agreement counts**,
not counts of clinically diagnosed diseases.

The output provides each case's matches, missing and unexpected labels, precision,
recall, F1 and exact set agreement. Aggregate precision, recall and F1 use pooled
micro counts. Subgroup metrics use the same definitions; cases without a subgroup
are grouped under `ungrouped`. Empty denominators produce JSON `null`. An empty
reference and empty prediction match exactly, but have undefined precision/recall.
An empty cohort has no exact-match rate. Output is deterministic and omits
run timestamps and report paths.

Baseline comparison requires the same normalized case IDs, reference labels and
subgroups, verified by a cohort fingerprint. Predictions may change. Increases
in false-positive or missing-label counts, decreases in matches or exact case
matches, either overall or within any subgroup, are flagged in `regressions`.
An unchanged aggregate cannot hide a subgroup regression. A baseline mismatch
or malformed input is an error. `passed` means no configured regression was
found; it does not mean the reports are correct or the model is safe. Without a
baseline, `passed` simply means the evaluation completed.

## Limits

Supply complete labels prepared independently of model predictions. Partial
reference annotation incorrectly counts unannotated predictions as false
positives. No true-negative universe is defined, so specificity and overall
clinical accuracy are intentionally absent. Confidence scores are uncalibrated
model self-assessments and are not used as accuracy estimates. This tool does not
measure image localization, free-text correctness, clinical severity, calibration,
statistical significance or generalization. Small or selected subgroups are
particularly limited. Clinical validation requires a separately designed study.
