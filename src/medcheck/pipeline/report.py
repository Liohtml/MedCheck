"""ReportStep: generates JSON, PDF, or HTML reports from a PipelineContext."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from medcheck.core.context import PipelineContext
from medcheck.core.step import PipelineStep
from medcheck.i18n import get_strings

# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------


def generate_json_report(ctx: PipelineContext) -> str:
    """Build a structured report dict and return it as a JSON string."""
    get_strings(ctx.report_language)
    findings_list: list[dict[str, Any]] = []
    for f in ctx.findings:
        findings_list.append(
            {
                "name": f.name,
                "status": f.status,
                "findings": f.findings,
                "confidence": f.confidence,
                "slices_evaluated": f.slices_evaluated,
                "secondary_signs": f.secondary_signs,
            }
        )

    # Summarise anomaly scores per series (keep lists JSON-serialisable)
    anomaly_summary: dict[str, Any] = {}
    for series, scores in (ctx.anomaly_scores or {}).items():
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        anomaly_summary[series] = scores

    top_slices_summary: dict[str, Any] = {}
    for series, slices in (ctx.top_slices or {}).items():
        if hasattr(slices, "tolist"):
            slices = slices.tolist()
        top_slices_summary[series] = slices

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language": ctx.report_language,
        "patient": {
            "name": ctx.patient.name,
            "patient_id": ctx.patient.patient_id,
            "birth_date": ctx.patient.birth_date,
            "sex": ctx.patient.sex,
            "age": ctx.patient.age,
        },
        "study": {
            "date": ctx.study.date,
            "description": ctx.study.description,
            "institution": ctx.study.institution,
            "manufacturer": ctx.study.manufacturer,
            "model_name": ctx.study.model_name,
            "field_strength": ctx.study.field_strength,
        },
        "detected_anatomy": ctx.detected_anatomy,
        "findings": findings_list,
        "anomaly_scores": anomaly_summary,
        "top_slices": top_slices_summary,
        "overall_impression": ctx.overall_impression,
        "clinical_correlation": ctx.clinical_correlation,
        "limitations": ctx.limitations,
    }
    return json.dumps(report, indent=2)


# ---------------------------------------------------------------------------
# PDF report (reportlab)
# ---------------------------------------------------------------------------


def generate_pdf_report(ctx: PipelineContext) -> str:
    """Generate a simple PDF report using reportlab. Returns the file path."""
    i18n = get_strings(ctx.report_language)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output_dir = ctx.output_dir or "."
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pdf_path = str(Path(output_dir) / f"report_{timestamp}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=12,
    )
    story.append(Paragraph(i18n["report_title"], title_style))
    story.append(Spacer(1, 0.3 * cm))

    # Patient / Study info
    story.append(Paragraph(i18n["patient_info"], styles["Heading2"]))
    patient_data = [
        [i18n["field_name"], ctx.patient.name],
        [i18n["field_id"], ctx.patient.patient_id],
        [i18n["field_dob"], ctx.patient.birth_date],
        [i18n["field_sex"], ctx.patient.sex],
        [i18n["field_age"], ctx.patient.age],
        [i18n["field_study_date"], ctx.study.date],
        [i18n["field_study_desc"], ctx.study.description],
        [i18n["field_institution"], ctx.study.institution],
    ]
    pt = Table(patient_data, colWidths=[5 * cm, 12 * cm])
    pt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(pt)
    story.append(Spacer(1, 0.4 * cm))

    # Findings
    story.append(Paragraph(i18n["headings_findings"], styles["Heading2"]))
    if ctx.findings:
        headers = [
            i18n["headings_structure"],
            i18n["headings_status"],
            i18n["headings_confidence"],
            i18n["headings_details"],
        ]
        rows = [headers] + [
            [
                f.name,
                f.status,
                f"{f.confidence:.0%}",
                f.findings,
            ]
            for f in ctx.findings
        ]
        ft = Table(rows, colWidths=[4 * cm, 3 * cm, 3 * cm, 7 * cm])
        ft.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3FB")]),
                ]
            )
        )
        story.append(ft)
    else:
        story.append(Paragraph(i18n["no_findings"], styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))

    # Overall Impression
    story.append(Paragraph(i18n["headings_impression"], styles["Heading2"]))
    story.append(Paragraph(ctx.overall_impression or "—", styles["Normal"]))
    story.append(Spacer(1, 0.3 * cm))

    # Clinical Correlation
    if ctx.clinical_correlation:
        story.append(Paragraph(i18n["headings_correlation"], styles["Heading2"]))
        story.append(Paragraph(ctx.clinical_correlation, styles["Normal"]))
        story.append(Spacer(1, 0.3 * cm))

    # Limitations
    if ctx.limitations:
        story.append(Paragraph(i18n["headings_limitations"], styles["Heading2"]))
        for lim in ctx.limitations:
            story.append(Paragraph(f"• {lim}", styles["Normal"]))
        story.append(Spacer(1, 0.3 * cm))

    # Disclaimer
    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=styles["Normal"],
        fontSize=7,
        textColor=colors.grey,
        spaceBefore=12,
    )
    story.append(
        Paragraph(
            i18n["disclaimer"],
            disclaimer_style,
        )
    )

    doc.build(story)
    return pdf_path


# ---------------------------------------------------------------------------
# HTML report (stub)
# ---------------------------------------------------------------------------


def generate_html_report(ctx: PipelineContext) -> str:
    """Generate a simple HTML report. Returns the file path."""
    i18n = get_strings(ctx.report_language)
    output_dir = ctx.output_dir or "."
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    html_path = str(Path(output_dir) / f"report_{timestamp}.html")

    findings_rows = ""
    for f in ctx.findings:
        findings_rows += (
            f"<tr><td>{html.escape(str(f.name))}</td>"
            f"<td>{html.escape(str(f.status))}</td>"
            f"<td>{f.confidence:.0%}</td>"
            f"<td>{html.escape(str(f.findings))}</td></tr>\n"
        )

    limitations_items = "".join(f"<li>{html.escape(str(lim))}</li>" for lim in ctx.limitations)

    # Fetch the localized table header cleanly from the catalog string dictionary
    lang_check = i18n.get("field_key", "Field")
    th_field = html.escape(lang_check)
    th_value = html.escape(i18n["field_value"])

    html_content = f"""<!DOCTYPE html>
<html lang="{html.escape(ctx.report_language)}">
<head>
  <meta charset="UTF-8" />
  <title>{html.escape(i18n["report_title"])}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2em; color: #222; }}
    h1 {{ color: #4472C4; }}
    h2 {{ color: #2E5090; border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 1em; }}
    th {{ background: #4472C4; color: white; padding: 6px 8px; text-align: left; }}
    td {{ padding: 5px 8px; border: 1px solid #ccc; }}
    tr:nth-child(even) {{ background: #EEF3FB; }}
    .disclaimer {{ font-size: 0.75em; color: #888; margin-top: 2em; border-top: 1px solid #ccc; padding-top: 0.5em; }}
  </style>
</head>
<body>
  <h1>{html.escape(i18n["report_title"])}</h1>

  <h2>{html.escape(i18n["patient_info"])}</h2>
  <table>
    <tr><th>{th_field}</th><th>{th_value}</th></tr>
    <tr><td>{html.escape(i18n["field_name"])}</td><td>{html.escape(ctx.patient.name)}</td></tr>
    <tr><td>{html.escape(i18n["field_id"])}</td><td>{html.escape(ctx.patient.patient_id)}</td></tr>
    <tr><td>{html.escape(i18n["field_dob"])}</td><td>{html.escape(ctx.patient.birth_date)}</td></tr>
    <tr><td>{html.escape(i18n["field_sex"])}</td><td>{html.escape(ctx.patient.sex)}</td></tr>
    <tr><td>{html.escape(i18n["field_age"])}</td><td>{html.escape(ctx.patient.age)}</td></tr>
    <tr><td>{html.escape(i18n["field_study_date"])}</td><td>{html.escape(ctx.study.date)}</td></tr>
    <tr><td>{html.escape(i18n["field_study_desc"])}</td><td>{html.escape(ctx.study.description)}</td></tr>
    <tr><td>{html.escape(i18n["field_institution"])}</td><td>{html.escape(ctx.study.institution)}</td></tr>
  </table>

  <h2>{html.escape(i18n["headings_findings"])}</h2>
  <table>
    <tr>
      <th>{html.escape(i18n["headings_structure"])}</th>
      <th>{html.escape(i18n["headings_status"])}</th>
      <th>{html.escape(i18n["headings_confidence"])}</th>
      <th>{html.escape(i18n["headings_details"])}</th>
    </tr>
    {findings_rows or f"<tr><td colspan='4'>{html.escape(i18n['no_findings'])}</td></tr>"}
  </table>

  <h2>{html.escape(i18n["headings_impression"])}</h2>
  <p>{html.escape(ctx.overall_impression or "—")}</p>

  <h2>{html.escape(i18n["headings_correlation"])}</h2>
  <p>{html.escape(ctx.clinical_correlation or "—")}</p>

  <h2>{html.escape(i18n["headings_limitations"])}</h2>
  <ul>{limitations_items or f"<li>{html.escape(i18n['none_specified'])}</li>"}</ul>

  <p class="disclaimer">
    {html.escape(i18n["disclaimer"])}
  </p>
</body>
</html>
"""
    Path(html_path).write_text(html_content, encoding="utf-8")
    return html_path


# ---------------------------------------------------------------------------
# ReportStep
# ---------------------------------------------------------------------------


class ReportStep(PipelineStep):
    """Pipeline step that generates a report in the requested format."""

    name: str = "report"

    def validate(self, context: PipelineContext) -> bool:
        # Works even with an empty context; always valid.
        return True

    def run(self, context: PipelineContext) -> PipelineContext:
        fmt = (context.report_format or "json").lower()
        output_dir = context.output_dir or "."
        os.makedirs(output_dir, exist_ok=True)

        if fmt == "pdf":
            path = generate_pdf_report(context)
        elif fmt == "html":
            path = generate_html_report(context)
        else:
            # Default: JSON
            json_str = generate_json_report(context)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = str(Path(output_dir) / f"report_{timestamp}.json")
            Path(path).write_text(json_str, encoding="utf-8")

        context.report_path = path
        return context
