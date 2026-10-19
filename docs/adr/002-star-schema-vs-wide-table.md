# 002 - Star schema vs wide table

- **Status:** accepted
- **Date:** 2026-10-17

## Context

RF-03 asks for a dimensional model that serves three API questions: the list of funds with
filters (RF-07), the time series of one fund (RF-08) and the monthly net-inflow ranking (RF-09).
Risk R-P3-02 is rework caused by a poorly defined model, so the grain has to be settled before
coding (task 3.1). Facts of the problem, measured on 2026-09:

- The daily report has ~540k rows per month at the grain (class or subclass, day). It is keyed
  by a CNPJ that is a class CNPJ (99.07% of the CNPJs) or, for funds without a class, a fund
  CNPJ (0.93%) ([ADR 005](005-cvm-registry-after-resolution-175.md)).
- The registry (~37k classes, ~90k funds) changes over time (name, status, administrator,
  manager). RF-04 asks for that history as SCD type 2, so a 2024 fact keeps pointing to the
  fund as it was in 2024.
- The warehouse is DuckDB, a columnar engine that joins a fact to a small dimension cheaply
  ([ADR 001](001-duckdb-vs-athena.md)).
- The project is a portfolio piece: the model must read as textbook Kimball and be easy to
  test (`relationships`, grain uniqueness).

## Decision

A Kimball **star schema** in the `marts` layer, detailed in
[dimensional-model.md](../dimensional-model.md):

- Facts `fct_informe_diario` (one row per class/subclass per day) and `fct_captacao_mensal`
  (one row per class per month, built from the daily fact).
- Dimensions `dim_fundo`, a single dimension at class grain with fund attributes denormalized,
  fund-only rows for funds without a class, and an unknown member. It is SCD2 from the snapshot
  of task 3.4. Plus `dim_data`, a calendar that also plays the month role.
- Subclass as a degenerate dimension in the daily fact; no bridge table, since a class belongs
  to exactly one fund.
- Hash surrogate key `sk_fundo = generate_surrogate_key([cnpj_fundo_classe, dt_valido_de])`
  per version; `sk_data` is the date itself.

## Alternatives considered

- **One wide denormalized table** (daily report with every registry column): no joins for the
  API. But the ~30 registry columns are repeated on every daily row. Applying SCD2 means
  rewriting history in the big table. Two grains (daily and monthly) would need two wide tables
  that duplicate the registry logic. And "list the funds" would have to run a distinct over the
  fact. DuckDB makes the star's joins cheap, so the benefit is small. Rejected. Wide views or
  API-specific models on top of the star stay possible if latency (RNF-01) requires them.
- **Data Vault 2.0** (hubs, links, satellites): strong at auditable history from many sources,
  but here there are three sources from one publisher. It triples the number of models and
  still needs a star for consumption. Rejected as over-engineering for the scope.
- **Staging plus views only** (no marts): least work, but no surrogate keys, no conformed
  dimension, no SCD2 (RF-04) and no place for the class-or-fund resolution (ADR 005). Every
  consumer would repeat the join rules. It does not meet RF-03. Rejected.
- **Snowflake (separate fund and class dimensions):** normalizes the fund-to-class hierarchy,
  but the fact carries a single CNPJ that is a class or a fund. Fund-only reports would need a
  nullable class key, and the API would need two joins. Rejected in favor of one dimension at
  class grain.

## Consequences

- The grain of each fact is tested with `dbt_utils.unique_combination_of_columns`, and every
  foreign key with `relationships` (RF-03 acceptance: no orphans, guaranteed by the unknown
  member).
- `dim_fundo` depends on `int_fundo_classe__unificado`, which applies the class-first,
  then-fund resolution and the one-entry-per-CNPJ rule. The snapshot (3.4) is taken on that
  model.
- Facts point to the dimension version valid on the fact date. History before the first
  snapshot is approximated by the oldest known version (`dt_valido_de = 1900-01-01`).
- Semi-additive measures (net assets, shareholders) must be aggregated at the last day of the
  period; the monthly fact precomputes them for the ranking and the series.
- Implementation follows in tasks 3.2 (dimensions), 3.3 (facts) and 3.4 (SCD2 snapshot).
