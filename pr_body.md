## Summary

This PR fixes two security issues in MedCheck, an AI-powered medical imaging analysis tool that handles patient PHI:

### Fix 1: PHI leakage via missing `.gitignore` (#114)

The CLI defaults to writing reports (JSON/PDF/HTML) to `./output/` — these reports contain full patient PHI (name, patient ID, DOB, sex, study details). The `output/` directory was **not listed in `.gitignore`**, meaning `git add .` would silently stage PHI-containing files, and a `git push` to a shared remote would leak patient data.

**Fix:** Added `output/` to `.gitignore` with a PHI warning comment, and updated the CLI `--output` help text to alert developers.

### Fix 2: Missing HTTP security headers (#109)

The FastAPI web app had no security response headers — no `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, or `Content-Security-Policy`. This is a meaningful hardening gap for an app that handles patient-derived medical imaging data, especially when exposed on the network via `MEDCHECK_HOST=0.0.0.0`.

**Fix:** Added `_SecurityHeadersMiddleware` (using `BaseHTTPMiddleware`) that sets:
- `X-Frame-Options: DENY` — prevents clickjacking
- `X-Content-Type-Options: nosniff` — prevents MIME sniffing
- `Referrer-Policy: no-referrer` — prevents patient-context URL leakage
- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` — restricts script/frame sources

## Changes

| File | Change |
|------|--------|
| `.gitignore` | Add `output/` with PHI warning comment |
| `src/medcheck/main.py` | Update `--output` help text to mention PHI |
| `src/medcheck/web/app.py` | Add `_SecurityHeadersMiddleware` class and register it |
| `tests/unit/test_web.py` | Add 3 tests for security headers |

## Verification

```
$ pytest tests/ -v
============================= 134 passed in 5.16s ==============================
```

All 134 tests pass, including the 3 new security header tests.

---

**About the Author:** Raphael Malikian — Clinical AI Solutions Architect. I specialise in building and fixing AI/ML systems for healthcare, including vector databases, RAG pipelines, and clinical NLP. If you need help with your project or think I can add value to your organisation, feel free to reach out — I'd love to connect.

📧 rtmalikian@gmail.com
🔗 GitHub: https://github.com/rtmalikian
🔗 LinkedIn: http://www.linkedin.com/in/raphael-t-malikian-mbbs-bsc-hons-71075436a

---

**Disclosure:** This code was developed with assistance from **mimo-2.5-pro** (Xiaomi) via **Hermes Agent** (Nous Research). All changes were reviewed, tested against the actual codebase, and verified for correctness.
