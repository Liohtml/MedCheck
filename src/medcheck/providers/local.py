from __future__ import annotations

import stat
import tempfile
import zipfile
from pathlib import Path
from typing import Any, ClassVar

import pydicom

from medcheck.core.context import DicomSeries
from medcheck.providers.base import DataProvider

_SKIP_SUFFIXES = {".jpg", ".jpeg", ".png", ".txt", ".json"}

# ZIP-bomb guards for archive extraction.
_ZIP_MAX_MEMBERS = 10_000
_ZIP_MAX_TOTAL_UNCOMPRESSED = 10 * 1024**3  # 10 GiB — generous for full MRI studies
_ZIP_MAX_COMPRESSION_RATIO = 200  # DICOM compresses well, but not this well


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
            resolved_tmp = Path(tmp_dir).resolve()
            with zipfile.ZipFile(zip_path, "r") as zf:
                infos = zf.infolist()
                if len(infos) > _ZIP_MAX_MEMBERS:
                    raise ValueError(f"ZIP contains too many members ({len(infos)} > {_ZIP_MAX_MEMBERS})")
                total_uncompressed = 0
                for info in infos:
                    member_path = Path(tmp_dir) / info.filename
                    # Resolve to catch ../ traversal (robust against prefix tricks).
                    if not member_path.resolve().is_relative_to(resolved_tmp):
                        raise ValueError(f"Unsafe path in ZIP: {info.filename}")
                    # Reject symlink members: extractall() would materialise the link
                    # and later members could write through it to escape tmp_dir.
                    unix_mode = info.external_attr >> 16
                    if unix_mode and stat.S_ISLNK(unix_mode):
                        raise ValueError(f"ZIP member is a symlink (not allowed): {info.filename}")
                    # ZIP-bomb guards: cap total size and per-member compression ratio.
                    total_uncompressed += info.file_size
                    if total_uncompressed > _ZIP_MAX_TOTAL_UNCOMPRESSED:
                        raise ValueError("ZIP uncompressed size exceeds the allowed limit")
                    if info.compress_size > 0 and info.file_size / info.compress_size > _ZIP_MAX_COMPRESSION_RATIO:
                        raise ValueError(f"ZIP member has suspicious compression ratio: {info.filename}")
                zf.extractall(tmp_dir)
            return self._scan_directory(Path(tmp_dir))

    @staticmethod
    def _try_read(path: Path) -> Any:
        try:
            # force=False: require a valid DICOM preamble/DICM marker so arbitrary
            # (potentially hostile) files are rejected instead of best-effort parsed.
            ds = pydicom.dcmread(str(path), force=False)
            if not hasattr(ds, "PixelData"):
                return None
            return ds
        except Exception:
            return None
