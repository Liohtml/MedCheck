"""Shared pytest fixtures for MedCheck test suite."""

from __future__ import annotations

import pathlib

import pytest


@pytest.fixture
def fixtures_dir() -> pathlib.Path:
    """Return the path to the test fixtures directory."""
    return pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_dicom_dir(fixtures_dir: pathlib.Path) -> pathlib.Path:
    """Return the path to the sample DICOM files directory."""
    dicom_dir = fixtures_dir / "dicom"
    dicom_dir.mkdir(parents=True, exist_ok=True)
    return dicom_dir
