"""MedCheck CLI - AI-powered medical imaging analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from medcheck import __version__

app = typer.Typer(
    name="medcheck",
    help="AI-powered medical imaging analysis toolkit",
    no_args_is_help=True,
)
console = Console()

_DEFAULT_STEPS = ["ingest", "preprocess", "ml_analysis", "report"]


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


def _build_registry() -> Any:
    """Create and populate a StepRegistry with all known pipeline steps."""
    from medcheck.core.workflow import StepRegistry
    from medcheck.pipeline.ingest import IngestStep
    from medcheck.pipeline.ml_analysis import MLAnalysisStep
    from medcheck.pipeline.preprocess import PreprocessStep
    from medcheck.pipeline.report import ReportStep
    from medcheck.pipeline.vision_analysis import VisionAnalysisStep

    registry = StepRegistry()
    registry.register("ingest", IngestStep)
    registry.register("preprocess", PreprocessStep)
    registry.register("ml_analysis", MLAnalysisStep)
    registry.register("vision_analysis", VisionAnalysisStep)
    registry.register("report", ReportStep)
    return registry


def _run_pipeline(ctx: Any, workflow: Any, steps: Any) -> Any:
    """Run the pipeline and return the final context."""
    from medcheck.core.workflow import WorkflowEngine

    engine = WorkflowEngine(_build_registry())

    if workflow:
        console.print(f"Using workflow: {workflow}")
        return engine.run_from_yaml(workflow, ctx)

    if steps:
        step_list = [s.strip() for s in steps.split(",")]
        console.print(f"Steps: {step_list}")
        return engine.run(steps=step_list, context=ctx)

    console.print(f"Using default pipeline: {_DEFAULT_STEPS}")
    return engine.run(steps=_DEFAULT_STEPS, context=ctx)


def _print_summary(ctx: Any) -> None:
    """Print a summary of pipeline results."""
    console.print("\n[bold green]Analysis complete.[/bold green]")
    if ctx.report_path:
        console.print(f"  Report: {ctx.report_path}")
    if ctx.findings:
        console.print(f"  Findings: {len(ctx.findings)} structure(s) evaluated")
    if ctx.overall_impression:
        console.print(f"  Impression: {ctx.overall_impression}")


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

    # Create output dir
    Path(output).mkdir(parents=True, exist_ok=True)

    console.print("[green]Analysis configuration ready.[/green]")
    console.print(f"  Report format: {report}")
    console.print(f"  Language: {lang}")
    console.print(f"  Output: {output}")

    ctx = _run_pipeline(ctx, workflow, steps)
    _print_summary(ctx)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host (use 0.0.0.0 to expose on the network)"),
    port: int = typer.Option(8080, "--port", help="Bind port"),
) -> None:
    """Start the MedCheck web UI server."""
    import os

    import uvicorn

    from medcheck.web.app import create_app

    console.print(f"[bold blue]MedCheck v{__version__} - Web UI[/bold blue]")
    console.print(f"Starting server on http://{host}:{port}")

    # Warn loudly when exposing patient-data endpoints on the network with no auth.
    if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("MEDCHECK_API_KEY"):
        console.print(
            f"[bold yellow]WARNING:[/bold yellow] Binding to {host} with no MEDCHECK_API_KEY set. "
            "The /api endpoints will be reachable on the network without authentication. "
            "Set MEDCHECK_API_KEY to require an X-API-Key header."
        )

    uvicorn.run(create_app(), host=host, port=port)


@app.command()
def providers() -> None:
    """List registered data providers and how they are matched."""
    from rich.table import Table

    from medcheck.providers.easyradiology import EasyRadiologyProvider
    from medcheck.providers.local import LocalProvider
    from medcheck.providers.registry import ProviderRegistry

    registry = ProviderRegistry()
    registry.register(LocalProvider)
    registry.register(EasyRadiologyProvider)

    table = Table(title="Data Providers")
    table.add_column("Name", style="bold cyan")
    table.add_column("Matches")
    for name in registry.list_providers():
        cls = type(registry.get(name))
        patterns = ", ".join(cls.url_patterns) if cls.url_patterns else "local files / folders / ZIP"
        table.add_row(name, patterns)
    console.print(table)


@app.command()
def models() -> None:
    """List LLM providers, their default models, and current availability."""
    from rich.table import Table

    from medcheck.llm.claude import ClaudeProvider
    from medcheck.llm.gemini import GeminiProvider
    from medcheck.llm.local import LocalLLMProvider
    from medcheck.llm.openai_provider import OpenAIProvider

    providers_list = [ClaudeProvider(), OpenAIProvider(), GeminiProvider(), LocalLLMProvider()]

    table = Table(title="LLM Providers")
    table.add_column("Name", style="bold cyan")
    table.add_column("Default Model")
    table.add_column("Vision")
    table.add_column("Available")
    for provider in providers_list:
        available = provider.check_available()
        table.add_row(
            provider.name,
            getattr(provider, "model", "—"),
            "yes" if provider.supports_vision else "no",
            "[green]yes[/green]" if available else "[red]no[/red]",
        )
    console.print(table)
    console.print(
        "\n[dim]Availability is derived from configured API keys "
        "(ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY).[/dim]"
    )


@app.command()
def download_models() -> None:
    """Download pretrained ML models for local analysis."""
    console.print("[bold blue]MedCheck - Model Download[/bold blue]")
    console.print("[yellow]Model download coming in next release.[/yellow]")
