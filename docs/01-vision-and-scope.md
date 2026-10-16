# 01 - Vision and scope

**Problem:** turn raw data into an analytical model that is reliable, tested and consumable by applications.

**Goal:** model a dimensional data warehouse with dbt on top of the investment fund data, with quality tests and documentation, and serve it through a REST API.

**Data source:** gold or silver layer from P1 (`aws-fundos-pipeline`); if P1 is not ready, a script loads the CVM open data directly.

| In scope | Out of scope |
|---|---|
| Dimensional modeling, dbt tests, snapshots, documentation, read-only API, contract tests, container | Front end, end-user authentication, production deployment |

## Success metrics (targets)
- `dbt build` without failures
- 100% of mart models documented and tested
- p95 below 300 ms on the time-series endpoints under local load
- OpenAPI published

## Stakeholders (simulated roles)
| Role | Main interest |
|---|---|
| Technical recruiter / manager | Clear evidence of stack, quality and autonomy within 5 minutes of reading |
| Code reviewer (engineer) | Tested, organized, reproducible code with justified decisions |
| Data consumer (analyst) | Reliable, documented data that is easy to query |
| Thales (developer and operator) | Low cost, reproducible runs, simple maintenance |
