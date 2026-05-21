"""VisionAnalysisStep - LLM-based vision analysis of MRI slices.

Selects representative slices per series, encodes them as PNG bytes,
and delegates to the best available LLM provider for structured analysis.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from medcheck.core.context import ClinicalContext, PipelineContext
from medcheck.core.step import PipelineStep
from medcheck.llm.base import AnnotatedImage
from medcheck.llm.router import LLMRouter

if TYPE_CHECKING:
    pass

_ANATOMY_HINTS: dict[str, str] = {
    "knee": (
        "Focus on: ACL, PCL, MCL, LCL integrity; menisci (medial/lateral) for tears or extrusion; "
        "cartilage surfaces; bone marrow oedema; Baker's cyst; patellar tendon."
    ),
    "shoulder": (
        "Focus on: rotator cuff tendons (supraspinatus, infraspinatus, subscapularis, teres minor); "
        "labrum (SLAP, Bankart); AC joint; biceps tendon; glenohumeral cartilage; Hill-Sachs/Bankart lesions."
    ),
    "spine": (
        "Focus on: disc height and signal; disc herniation/protrusion/extrusion; neural foramina; "
        "spinal canal stenosis; vertebral body signal; facet joints; paraspinal muscles."
    ),
    "hip": (
        "Focus on: labrum; cartilage (femoral head, acetabulum); femoroacetabular impingement; "
        "iliopsoas/gluteal tendons; bone marrow; AVN signs."
    ),
    "wrist": (
        "Focus on: TFCC; intrinsic ligaments (scapholunate, lunotriquetral); carpal alignment; "
        "cartilage; extensor/flexor tendons; median nerve (carpal tunnel)."
    ),
    "ankle": (
        "Focus on: ATFL, CFL, deltoid ligament; Achilles tendon; peroneal tendons; tibiotalar cartilage; "
        "sinus tarsi; os trigonum."
    ),
    "brain": (
        "Focus on: signal abnormalities (T2/FLAIR hyperintensity); diffusion restriction; "
        "mass effect; midline shift; herniation; vascular territories; white/grey matter differentiation."
    ),
}

_JSON_SCHEMA = """
{
  "structures": [
    {
      "name": "<structure name>",
      "status": "<intact|partial tear|complete tear|degenerated|herniated|abnormal|normal|...>",
      "findings": "<detailed description>",
      "confidence": <0.0-1.0>,
      "slices_evaluated": <int>,
      "secondary_signs": ["<sign1>", ...]
    }
  ],
  "overall_impression": "<concise summary>",
  "clinical_correlation": "<clinical interpretation>",
  "limitations": ["<limitation1>", ...]
}
"""


def build_prompt(clinical_context: ClinicalContext | None, anatomy: str | None) -> str:
    """Build a structured medical imaging analysis prompt.

    Parameters
    ----------
    clinical_context:
        Optional ClinicalContext with symptoms, trauma history, etc.
    anatomy:
        Detected anatomy region (e.g. "knee", "shoulder").

    Returns
    -------
    str
        Fully-formed prompt for the LLM vision model.
    """
    anatomy_label = (anatomy or "musculoskeletal region").lower()
    anatomy_hint = _ANATOMY_HINTS.get(
        anatomy_label, f"Thoroughly evaluate all visible structures in the {anatomy_label}."
    )

    lines: list[str] = [
        "You are an expert radiologist and medical imaging analyst specialising in MRI interpretation.",
        "",
        f"## Study Region: {anatomy_label.title()}",
        "",
        "## Task",
        f"Analyse the provided MRI images of the {anatomy_label} and produce a structured report.",
        "",
        "## Anatomy-Specific Instructions",
        anatomy_hint,
        "",
    ]

    # Clinical context block
    if clinical_context is not None:
        lines += [
            "## Clinical Context",
        ]
        if clinical_context.symptoms:
            lines.append(f"- Symptoms: {clinical_context.symptoms}")
        if clinical_context.trauma:
            lines.append(f"- Trauma/Mechanism: {clinical_context.trauma}")
        if clinical_context.trauma_date:
            lines.append(f"- Trauma date: {clinical_context.trauma_date}")
        if clinical_context.suspected_diagnosis:
            lines.append(f"- Suspected diagnosis: {clinical_context.suspected_diagnosis}")
        if clinical_context.patient_age:
            lines.append(f"- Patient age: {clinical_context.patient_age}")
        if clinical_context.patient_sex:
            lines.append(f"- Patient sex: {clinical_context.patient_sex}")
        lines.append("")
    else:
        lines += [
            "## Clinical Context",
            "No clinical context provided. Perform a comprehensive evaluation of all visible structures.",
            "",
        ]

    lines += [
        "## Output Format",
        "Respond with ONLY valid JSON matching the following schema (no markdown fences, no extra text):",
        _JSON_SCHEMA.strip(),
        "",
        "## Important Notes",
        "- Base findings solely on the images provided.",
        "- Assign a confidence score (0.0-1.0) per structure.",
        "- List any technical limitations (field strength, motion artefact, slice thickness, etc.).",
        "- Do NOT hallucinate findings not visible in the images.",
        "- This report is generated by an AI assistant and MUST be reviewed by a qualified radiologist"
        " before any clinical use.",
    ]

    return "\n".join(lines)


def _volume_slice_to_png_bytes(slice_array: np.ndarray) -> bytes:
    """Convert a 2-D numpy array (single MRI slice) to PNG bytes."""
    arr = slice_array.astype(np.float32)
    lo, hi = arr.min(), arr.max()
    if hi - lo > 0:
        arr = (arr - lo) / (hi - lo) * 255.0
    else:
        arr = np.zeros_like(arr)
    img = Image.fromarray(arr.astype(np.uint8), mode="L").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _select_slice_indices(volume: np.ndarray, top_slices: list[int] | None, n: int = 5) -> list[int]:
    """Return up to *n* slice indices: prefer top_slices, else evenly spaced."""
    n_slices = volume.shape[0]
    if top_slices:
        return list(top_slices[:n])
    # Evenly-spaced fallback
    step = max(1, n_slices // n)
    return list(range(0, n_slices, step))[:n]


class VisionAnalysisStep(PipelineStep):
    """Pipeline step: send top MRI slices to an LLM for structured vision analysis."""

    name = "vision_analysis"

    def validate(self, context: PipelineContext) -> bool:
        """Require at least one loaded volume."""
        return bool(context.volumes)

    def run(self, context: PipelineContext) -> PipelineContext:
        """Execute vision analysis and populate context with findings."""
        anatomy = context.detected_anatomy or "musculoskeletal region"
        prompt = build_prompt(context.clinical_context, anatomy)

        # Build AnnotatedImage list from all series
        images: list[AnnotatedImage] = []
        for series_name, volume in context.volumes.items():
            top = context.top_slices.get(series_name)
            indices = _select_slice_indices(volume, list(top) if top else None)
            for idx in indices:
                png_bytes = _volume_slice_to_png_bytes(volume[idx])
                images.append(
                    AnnotatedImage(
                        series_name=series_name,
                        slice_index=idx,
                        image_bytes=png_bytes,
                        description=f"Series: {series_name} | Slice {idx + 1}/{volume.shape[0]}",
                    )
                )

        # Route to best available LLM provider
        router = self._get_router()
        provider = router.select(preferred="claude")
        result = provider.analyze_images(images, prompt, context.clinical_context)

        # Populate context from result
        context.findings = result.structures
        context.overall_impression = result.overall_impression
        context.clinical_correlation = result.clinical_correlation
        context.limitations = result.limitations

        return context

    def _get_router(self) -> LLMRouter:
        """Create an LLMRouter and register all available providers."""
        from medcheck.llm.claude import ClaudeProvider
        from medcheck.llm.gemini import GeminiProvider
        from medcheck.llm.openai_provider import OpenAIProvider

        router = LLMRouter()
        router.register(ClaudeProvider())
        router.register(OpenAIProvider())
        router.register(GeminiProvider())
        return router
