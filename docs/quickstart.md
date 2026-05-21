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

## Web UI

Once the server is running (`medcheck serve` or `docker compose up`), open:

```
http://localhost:8080
```

Upload an image, select the anatomy region, and click **Analyze**. Results are displayed as structured JSON and a plain-language summary.
