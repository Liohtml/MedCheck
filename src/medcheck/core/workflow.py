from __future__ import annotations

from typing import Any

import yaml
from rich.console import Console

from medcheck.core.context import PipelineContext
from medcheck.core.step import PipelineStep

console = Console()


class StepRegistry:
    """Registry that maps step names to PipelineStep subclasses."""

    def __init__(self) -> None:
        self._steps: dict[str, type[PipelineStep]] = {}

    def register(self, name: str, step_class: type[PipelineStep]) -> None:
        """Register a step class under the given name."""
        self._steps[name] = step_class

    def get(self, name: str) -> type[PipelineStep]:
        """Return the step class for *name*, raising KeyError if not found."""
        if name not in self._steps:
            raise KeyError(name)
        return self._steps[name]

    def list_steps(self) -> list[str]:
        """Return registered step names in insertion order."""
        return list(self._steps.keys())


class WorkflowEngine:
    """Orchestrates sequential execution of pipeline steps."""

    def __init__(self, registry: StepRegistry) -> None:
        self.registry = registry

    def run(
        self,
        steps: list[str],
        context: PipelineContext,
        step_configs: dict[str, Any] | None = None,
    ) -> PipelineContext:
        """Instantiate and run each step in *steps* order.

        Args:
            steps: Ordered list of step names to execute.
            context: The shared pipeline context passed through all steps.
            step_configs: Optional per-step configuration dicts keyed by name.

        Returns:
            The (potentially mutated) context after all steps have run.

        Raises:
            KeyError: If a step name is not found in the registry.
        """
        step_configs = step_configs or {}

        for name in steps:
            step_class = self.registry.get(name)  # raises KeyError if unknown
            step_instance = step_class()
            console.print(f"[bold blue]▶ Running step:[/bold blue] {name}")
            if not step_instance.validate(context):
                console.print(f"[yellow]Skipping {name}: prerequisites not met[/yellow]")
                continue
            context.step_config = step_configs.get(name, {})
            context = step_instance.run(context)
            console.print(f"[bold green]✔ Completed step:[/bold green] {name}")

        return context

    def run_from_yaml(
        self,
        yaml_path: str,
        context: PipelineContext,
    ) -> PipelineContext:
        """Load a workflow YAML file and run its steps.

        Expected YAML format::

            name: my_workflow
            steps:
              - step_name:          # value may be null or a config dict
              - another_step:
                  param: value

        Args:
            yaml_path: Path to the YAML workflow definition file.
            context: The shared pipeline context.

        Returns:
            The context after all steps have run.
        """
        with open(yaml_path, encoding="utf-8") as fh:
            workflow_def = yaml.safe_load(fh)

        raw_steps: list[Any] = workflow_def.get("steps", [])

        step_names: list[str] = []
        step_configs: dict[str, Any] = {}

        for entry in raw_steps:
            if isinstance(entry, str):
                step_names.append(entry)
            elif isinstance(entry, dict):
                for step_name, cfg in entry.items():
                    step_names.append(step_name)
                    if cfg is not None:
                        step_configs[step_name] = cfg

        workflow_name = workflow_def.get("name", yaml_path)
        console.print(f"[bold cyan]Workflow:[/bold cyan] {workflow_name}")

        return self.run(steps=step_names, context=context, step_configs=step_configs)
