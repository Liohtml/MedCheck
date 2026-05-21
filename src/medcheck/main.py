"""MedCheck CLI entry point."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="medcheck",
    help="AI-powered medical imaging analysis toolkit.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit."),
) -> None:
    """MedCheck - AI-powered medical imaging analysis toolkit."""
    if version:
        from medcheck import __version__

        typer.echo(f"medcheck {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
