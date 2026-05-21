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

## Scope

In scope:
- Source code in this repository
- Default configuration and integrations
- Data handling and LLM provider integrations

Out of scope:
- Third-party data provider infrastructure
- LLM provider APIs (OpenAI, Anthropic, etc.) — report those to the respective vendors
