from __future__ import annotations

from abc import ABC, abstractmethod

from medcheck.core.context import DicomSeries


class DataProvider(ABC):
    name: str
    url_patterns: list[str]

    @abstractmethod
    def authenticate(self, credentials: dict[str, str]) -> bool: ...

    @abstractmethod
    def fetch(self, target: str, credentials: dict[str, str]) -> list[DicomSeries]: ...
