from medcheck.core.context import PipelineContext, StructureFinding
from medcheck.pipeline.reconcile import ReconcileStep, compare_reports


def test_missing_reference_report_produces_no_comparison():
    ctx = PipelineContext(official_report=" \n ", findings=[StructureFinding(name="ACL")])
    assert compare_reports(ctx) == {}
    assert ReconcileStep().run(ctx).reconciliation == {}


def test_case_insensitive_structure_matching_retains_negation_for_review():
    ctx = PipelineContext(
        official_report=" ACL intact. No PCL tear! Cartilage unremarkable\nACL shows no discontinuity ",
        findings=[StructureFinding(name="acl", status="complete tear"), StructureFinding(name="PCL")],
    )
    result = compare_reports(ctx)
    assert result["method"] == "lexical-structure-match-v1"
    assert result["comparisons"][0] == {
        "finding_index": 0,
        "structure": "acl",
        "status": "requires_review",
        "reference_passages": ["ACL intact", "ACL shows no discontinuity"],
    }
    assert result["comparisons"][1]["reference_passages"] == ["No PCL tear"]
    assert result["comparisons"][1]["status"] == "requires_review"
    assert "do not establish agreement" in result["limitation"]


def test_unmatched_synonym_and_empty_name_never_invent_agreement():
    ctx = PipelineContext(
        official_report="Anterior cruciate ligament is intact.",
        findings=[StructureFinding(name="ACL"), StructureFinding(name="")],
    )
    result = ReconcileStep().run(ctx)
    assert all(item["status"] == "not_matched" for item in result.reconciliation["comparisons"])
    assert all(item["reference_passages"] == [] for item in result.reconciliation["comparisons"])
    assert [finding.name for finding in result.findings] == ["ACL", ""]


def test_reference_without_findings_is_retained_for_manual_review():
    result = compare_reports(PipelineContext(official_report="Original report"))
    assert result["comparisons"] == []
    assert result["reference_report"] == "Original report"
