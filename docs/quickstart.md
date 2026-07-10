# Quick Start

## Docker (recommended)

### Lite image (~500 MB — cloud APIs only)

```bash
docker build --target lite -t medcheck:lite .
docker run -p 8080:8080 --env-file .env medcheck:lite
```

Or with Docker Compose:

```bash
docker compose up
```

### Full image (~10 GB — includes local ML models)

```bash
docker build --target full -t medcheck:full .
docker run -p 8080:8080 --env-file .env medcheck:full
```

---

## pip / uv install

```bash
pip install medcheck
# or
uv add medcheck
```

---

## CLI examples

### Analyze a local DICOM/NIfTI file

```bash
medcheck analyze path/to/knee.dcm --anatomy knee
```

### Analyze via a PACS/portal URL

```bash
medcheck analyze https://portal.example.com/study/12345 --anatomy shoulder
```

### Interactive mode (prompt-driven)

```bash
medcheck interactive
```

---

## Web UI (preview)

Once the server is running (`medcheck serve` or `docker compose up`), open:

```
http://localhost:8080
```

> **Note:** the web wizard is a preview. Running an analysis from the browser is
> not yet available — the Analyze step returns `501 Not Implemented` until
> [#157](https://github.com/Liohtml/MedCheck/issues/157) lands. Use the CLI
> (`medcheck analyze SOURCE`, see above) to run analyses today.
