"""MedCheck CLI - AI-powered medical imaging analysis."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from medcheck import __version__

app = typer.Typer(
    name="medcheck",
    help="AI-powered medical imaging analysis toolkit",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"MedCheck v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, is_eager=True, help="Show version"
    ),
) -> None:
    pass


@app.command()
def analyze(
    source: str = typer.Argument(..., help="DICOM folder, ZIP file, or portal URL"),
    provider: str | None = typer.Option(None, "--provider", "-p", help="Data provider (auto-detected if omitted)"),
    code: str | None = typer.Option(None, "--code", help="Access code (for portal providers)"),
    dob: str | None = typer.Option(None, "--dob", help="Date of birth (for portal providers)"),
    symptoms: str | None = typer.Option(None, "--symptoms", help="Patient symptoms"),
    trauma: str | None = typer.Option(None, "--trauma", help="Trauma mechanism/history"),
    trauma_date: str | None = typer.Option(None, "--trauma-date", help="Date of trauma"),
    diagnosis: str | None = typer.Option(None, "--diagnosis", help="Suspected diagnosis"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM provider: claude, openai, gemini, local"),
    steps: str | None = typer.Option(None, "--steps", help="Comma-separated pipeline steps"),
    workflow: str | None = typer.Option(None, "--workflow", "-w", help="Path to workflow YAML"),
    report: str = typer.Option("pdf", "--report", "-r", help="Report format: pdf, html, json"),
    lang: str = typer.Option("en", "--lang", "-l", help="Report language: en, de"),
    output: str = typer.Option("./output", "--output", "-o", help="Output directory"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive mode"),
) -> None:
    """Analyze medical images from DICOM files or radiology portals."""
    from medcheck.core.context import ClinicalContext, PipelineContext

    console.print(f"[bold blue]MedCheck v{__version__}[/bold blue]")
    console.print(f"Source: {source}")

    # Build context
    ctx = PipelineContext()
    ctx.source = source
    ctx.provider_name = provider or ""
    ctx.credentials = {}
    if code:
        ctx.credentials["code"] = code
    if dob:
        ctx.credentials["dob"] = dob
    ctx.report_format = report
    ctx.report_language = lang
    ctx.output_dir = output

    # Clinical context
    if symptoms or trauma or diagnosis:
        ctx.clinical_context = ClinicalContext(
            symptoms=symptoms or "",
            trauma=trauma or "",
            trauma_date=trauma_date or "",
            suspected_diagnosis=diagnosis or "",
        )

    # Interactive mode: prompt for missing info
    if interactive:
        if not ctx.source:
            ctx.source = typer.prompt("DICOM source (folder/ZIP/URL)")
        if not ctx.clinical_context:
            s = typer.prompt("Symptoms (or press Enter to skip)", default="")
            t = typer.prompt("Trauma history (or press Enter to skip)", default="")
            if s or t:
                ctx.clinical_context = ClinicalContext(symptoms=s, trauma=t)

    # Determine pipeline steps
    if workflow:
        console.print(f"Using workflow: {workflow}")
        # WorkflowEngine will handle YAML parsing
    elif steps:
        step_list = [s.strip() for s in steps.split(",")]
        console.print(f"Steps: {step_list}")
    else:
        console.print("Using default pipeline")

    # Create output dir
    Path(output).mkdir(parents=True, exist_ok=True)

    console.print("[green]Analysis configuration ready.[/green]")
    console.print(f"  Report format: {report}")
    console.print(f"  Language: {lang}")
    console.print(f"  Output: {output}")

    # Note: Full pipeline execution will be wired up when all steps are integrated
    console.print("[yellow]Pipeline execution coming in next release.[/yellow]")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8080, "--port", help="Bind port"),
) -> None:
    """Start the MedCheck web UI server."""
    console.print(f"[bold blue]MedCheck v{__version__} - Web UI[/bold blue]")
    console.print(f"Starting server on http://{host}:{port}")
    console.print("[yellow]Web UI coming in next release.[/yellow]")


@app.command()
def download_models() -> None:
    """Download pretrained ML models for local analysis."""
    console.print("[bold blue]MedCheck - Model Download[/bold blue]")
    console.print("[yellow]Model download coming in next release.[/yellow]")
