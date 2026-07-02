# Security Policy

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

MedCheck handles sensitive medical data queries and integrates with external APIs. We take security seriously and appreciate responsible disclosure.

### How to Report

Use [GitHub's private vulnerability reporting](https://github.com/Liohtml/MedCheck/security/advisories/new) to submit a vulnerability report confidentially.

Alternatively, contact the maintainers directly via the email listed on the GitHub profile.

### What to Include

- A clear description of the vulnerability
- Steps to reproduce the issue
- Potential impact, especially any risk to medical data confidentiality or integrity
- Suggested remediation if known

### Response Timeline

- **48 hours**: Acknowledgment of the report
- **7 days**: Initial assessment and severity classification
- **90 days**: Target for patch release (critical issues prioritized)

You will be kept informed throughout the process.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| Latest  | Yes       |
| Older   | No        |

## Sensitive Data Considerations

MedCheck processes medical and health-related queries. Any vulnerability that could expose, alter, or misroute sensitive medical data is treated as **critical severity**. Please flag such issues explicitly in your report.

### Handling of Patient Data (PHI)

- **External LLM transmission is opt-in.** The `vision_analysis` step sends
  imaging slices and clinical context to a cloud LLM provider (Claude / GPT /
  Gemini) only after explicit consent: pass `--allow-cloud-llm` to `medcheck
  analyze`, set `MEDCHECK_ALLOW_EXTERNAL_LLM=1`, or confirm the prompt in
  interactive mode. Without consent the step raises an error instead of
  transmitting data. Use the offline `local` provider to avoid transmission
  entirely (see [#18](https://github.com/Liohtml/MedCheck/issues/18)).
- **Logs are pseudonymised.** Patient names and study descriptions are never
  written to stdout/logs; a short hash-derived pseudonymous identifier of the
  patient ID is logged instead. Note this is pseudonymisation, not full
  anonymisation — hashed identifiers in low-entropy ID spaces may still be
  re-identifiable.
- **Credentials are kept out of error messages.** Portal access codes are not
  echoed into exceptions or logs.
- **Network exposure is opt-in.** The web server binds to `127.0.0.1` by
  default. When exposing it on the network, set `MEDCHECK_API_KEY` so `/api`
  endpoints require an `X-API-Key` header.
- **Generated reports contain PHI by default.** Reports (JSON/PDF/HTML) embed
  patient name, ID and birth date from the DICOM metadata unless
  `--deidentify` is passed, which replaces them with a stable pseudonym.
  Report files are written with owner-only permissions (`0600`), but the
  output directory must still be treated as PHI: do not commit it, upload it
  to CI artifacts, or share it without de-identification.
- **No silent LLM provider substitution.** If the requested LLM provider is
  unavailable, MedCheck falls back only to the on-device `local` provider (or
  fails) — it never reroutes patient data to a different cloud provider.

## Scope

In scope:
- Source code in this repository
- Default configuration and integrations
- Data handling and LLM provider integrations

Out of scope:
- Third-party data provider infrastructure
- LLM provider APIs (OpenAI, Anthropic, etc.) — report those to the respective vendors
