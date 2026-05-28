from __future__ import annotations

import hashlib

from rich.console import Console

from medcheck.core.context import PatientInfo, PipelineContext, StudyInfo
from medcheck.core.step import PipelineStep
from medcheck.providers.easyradiology import EasyRadiologyProvider
from medcheck.providers.local import LocalProvider
from medcheck.providers.registry import ProviderRegistry

_console = Console()


class IngestStep(PipelineStep):
    """Pipeline step that loads DICOM data via the provider system."""

    name = "ingest"

    def run(self, context: PipelineContext) -> PipelineContext:
        registry = ProviderRegistry()
        registry.register(LocalProvider)
        registry.register(EasyRadiologyProvider)

        _console.print(f"[bold cyan]IngestStep[/] Resolving provider for source: {context.source!r}")

        if context.provider_name and context.provider_name != "local":
            provider = registry.get(context.provider_name)
        else:
            try:
                provider = registry.detect(context.source)
            except ValueError:
                provider = registry.get("local")

        _console.print(f"[bold cyan]IngestStep[/] Using provider: [green]{provider.__class__.__name__}[/]")

        series_list = provider.fetch(context.source, context.credentials)
        context.dicom_series = series_list

        _console.print(f"[bold cyan]IngestStep[/] Loaded {len(series_list)} series")

        # Extract patient and study info from the first available DICOM slice
        if series_list and series_list[0].slices:
            first_slice = series_list[0].slices[0]
            context.patient = PatientInfo(
                name=str(getattr(first_slice, "PatientName", "") or ""),
                patient_id=str(getattr(first_slice, "PatientID", "") or ""),
                birth_date=str(getattr(first_slice, "PatientBirthDate", "") or ""),
                sex=str(getattr(first_slice, "PatientSex", "") or ""),
            )
            context.study = StudyInfo(
                date=str(getattr(first_slice, "StudyDate", "") or ""),
                description=str(getattr(first_slice, "StudyDescription", "") or ""),
                institution=str(getattr(first_slice, "InstitutionName", "") or ""),
                manufacturer=str(getattr(first_slice, "Manufacturer", "") or ""),
                model_name=str(getattr(first_slice, "ManufacturerModelName", "") or ""),
                field_strength=str(getattr(first_slice, "MagneticFieldStrength", "") or ""),
            )
            # Avoid printing raw PHI (patient name) to stdout/logs; use a short,
            # non-reversible hash of the patient ID as a pseudonymous identifier.
            pid = context.patient.patient_id or context.patient.name
            safe_id = hashlib.sha256(pid.encode("utf-8")).hexdigest()[:8] if pid else "unknown"
            _console.print(
                f"[bold cyan]IngestStep[/] Patient: [yellow]#{safe_id}[/] | "
                f"Study: [yellow]{context.study.description}[/]"
            )

        return context

    def validate(self, context: PipelineContext) -> bool:
        return bool(context.source)
