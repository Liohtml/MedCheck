"""Local, explicitly lexical report comparison; never a diagnostic adjudicator."""

from __future__ import annotations

import re
from typing import Any

from medcheck.core.context import PipelineContext
from medcheck.core.step import PipelineStep


def compare_reports(context: PipelineContext) -> dict[str, Any]:
    reference = context.official_report.strip()
    if not reference:
        return {}
    sentences = [s.strip() for s in re.split(r"[\n.!?]+", reference) if s.strip()]
    comparisons = []
    for index, finding in enumerate(context.findings):
        name = finding.name.casefold()
        matches = [sentence for sentence in sentences if name and name in sentence.casefold()]
        comparisons.append(
            {
                "finding_index": index,
                "structure": finding.name,
                "reference_passages": matches,
                "status": "requires_review" if matches else "not_matched",
            }
        )
    return {
        "method": "lexical-structure-match-v1",
        "comparisons": comparisons,
        "reference_report": reference,
        "limitation": (
            "Text matches do not establish agreement or correctness. Synonyms and negations require human review."
        ),
    }


class ReconcileStep(PipelineStep):
    name = "reconcile"

    def run(self, context: PipelineContext) -> PipelineContext:
        context.reconciliation = compare_reports(context)
        return context
