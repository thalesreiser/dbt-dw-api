# Security policy

## Supported versions

This is a portfolio project. Only the `main` branch is supported; there are no releases and
no backported fixes.

| Version | Supported |
|---|---|
| `main` | Yes |
| Anything else (old commits, forks) | No |

## Reporting a vulnerability

Please report vulnerabilities **privately** through GitHub private vulnerability reporting:
open the repository **Security** tab and click **Report a vulnerability**.

- Do **not** open a public issue, pull request or discussion for a security problem.
- Include what is affected (file, endpoint or workflow), how to reproduce it and the impact you
  expect.
- Responses are **best effort**: this is a personal project maintained in spare time, so there is
  no guaranteed response or fix time. You will get an acknowledgement once the report is read.

## Scope

In scope:

- The code in this repository: dbt models, the `fundos_api` FastAPI service, scripts and the
  GitHub Actions workflows.
- Secrets or personal data accidentally committed to the repository.

Out of scope:

- The CVM open data portal and any other third-party service or dependency (report those to
  their maintainers; dependency advisories are tracked through Dependabot).
- Deployments run by third parties from this code.

## Running the API safely

The API is **read-only and designed to run locally** against a local DuckDB file. It must
**not** be exposed to the internet or to a shared network until RF-10 (API key authentication
and rate limiting) is implemented; **RF-10 is not implemented yet**. Running it on a public host
before that is outside the supported use of this project.

## Secrets

No secret, key or credential may be committed. Use your own `.env` (ignored by Git) created
from `.env.example`. Pre-commit runs gitleaks, and GitHub secret scanning with push protection
is enabled on the repository.
