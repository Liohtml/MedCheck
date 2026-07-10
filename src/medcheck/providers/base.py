from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from medcheck.core.context import DicomSeries


class DataProvider(ABC):
    name: str
    # Domains this provider handles (e.g. "example.net"). Matched by the
    # registry against a target URL's hostname: exact match or subdomain.
    url_patterns: ClassVar[list[str]]

    @abstractmethod
    def authenticate(self, credentials: dict[str, str]) -> bool: ...

    @abstractmethod
    def fetch(self, target: str, credentials: dict[str, str]) -> list[DicomSeries]: ...
