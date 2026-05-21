# Custom Data Providers

A **DataProvider** is responsible for loading image data (DICOM, NIfTI, PNG stacks, etc.) from a given source and returning it in the format expected by the MedCheck pipeline.

---

## Interface

```python
from medcheck.providers.base import DataProvider, ImageBundle

class DataProvider:
    """Abstract base class for all data providers."""

    def can_handle(self, source: str) -> bool:
        """Return True if this provider can load from `source`."""
        ...

    def load(self, source: str) -> ImageBundle:
        """Load and return an ImageBundle from `source`."""
        ...
```

`ImageBundle` is a dataclass:

```python
@dataclass
class ImageBundle:
    series: list[np.ndarray]   # list of 2-D slice arrays
    metadata: dict             # DICOM tags or equivalent key/value pairs
    anatomy: str | None        # optional hint, e.g. "knee"
```

---

## Example: HTTP portal provider

```python
from medcheck.providers.base import DataProvider, ImageBundle
import httpx, pydicom, numpy as np, io

class PortalProvider(DataProvider):
    def can_handle(self, source: str) -> bool:
        return source.startswith("https://portal.example.com/")

    def load(self, source: str) -> ImageBundle:
        resp = httpx.get(source, timeout=30)
        resp.raise_for_status()
        ds = pydicom.dcmread(io.BytesIO(resp.content))
        return ImageBundle(
            series=[ds.pixel_array.astype(np.float32)],
            metadata={str(tag): str(ds[tag].value) for tag in ds},
            anatomy=None,
        )
```

---

## Registration

Register your provider so MedCheck discovers it automatically:

```python
# In your package's __init__.py or a plugin entry point:
from medcheck.providers import registry
from mypackage.portal_provider import PortalProvider

registry.register(PortalProvider())
```

Or via `pyproject.toml` entry points:

```toml
[project.entry-points."medcheck.providers"]
portal = "mypackage.portal_provider:PortalProvider"
```

---

## Auto-detection

When `medcheck analyze <source>` is called, the provider registry iterates registered providers in order and calls `can_handle(source)`. The first provider that returns `True` is used. Built-in providers (local filesystem, HTTP) are registered with lower priority than user-supplied ones, so custom providers take precedence.
