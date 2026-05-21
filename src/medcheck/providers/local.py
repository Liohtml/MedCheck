from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Any, ClassVar

import pydicom

from medcheck.core.context import DicomSeries
from medcheck.providers.base import DataProvider

_SKIP_SUFFIXES = {".jpg", ".jpeg", ".png", ".txt", ".json"}


class LocalProvider(DataProvider):
    name = "local"
    url_patterns: ClassVar[list[str]] = []

    def authenticate(self, credentials: dict[str, str]) -> bool:
        return True

    def fetch(self, target: str, credentials: dict[str, str]) -> list[DicomSeries]:
        target_path = Path(target)

        if target_path.is_dir():
            return self._scan_directory(target_path)

        if target_path.suffix.lower() == ".zip" and target_path.exists():
            return self._scan_zip(target_path)

        raise ValueError(f"Target '{target}' must be a directory or ZIP file; must be a directory or ZIP")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scan_directory(self, directory: Path) -> list[DicomSeries]:
        series_map: dict[str, dict[str, Any]] = {}

        for file in directory.rglob("*"):
            if not file.is_file():
                continue
            if file.suffix.lower() in _SKIP_SUFFIXES:
                continue

            ds = self._try_read(file)
            if ds is None:
                continue

            desc = getattr(ds, "SeriesDescription", "") or ""
            series_num = int(getattr(ds, "SeriesNumber", 0) or 0)
            key = desc or str(series_num)

            if key not in series_map:
                series_map[key] = {
                    "description": desc,
                    "series_number": series_num,
                    "modality": getattr(ds, "Modality", "") or "",
                    "slices": [],
                }
            series_map[key]["slices"].append(ds)

        results = list(series_map.values())
        results.sort(key=lambda s: s["series_number"])

        return [
            DicomSeries(
                description=s["description"],
                series_number=s["series_number"],
                modality=s["modality"],
                slices=s["slices"],
            )
            for s in results
        ]

    def _scan_zip(self, zip_path: Path) -> list[DicomSeries]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    member_path = Path(tmp_dir) / member
                    # Resolve to catch ../ traversal
                    if not str(member_path.resolve()).startswith(str(Path(tmp_dir).resolve())):
                        raise ValueError(f"Unsafe path in ZIP: {member}")
                zf.extractall(tmp_dir)
            return self._scan_directory(Path(tmp_dir))

    @staticmethod
    def _try_read(path: Path) -> Any:
        try:
            ds = pydicom.dcmread(str(path), force=True)
            if not hasattr(ds, "PixelData"):
                return None
            return ds
        except Exception:
            return None
