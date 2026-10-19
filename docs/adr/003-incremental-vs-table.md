# 003 - Incremental vs table materialization

- **Status:** accepted
- **Date:** 2026-10-19

## Context

`fct_informe_diario` (RF-03) has the grain of the CVM daily report: about 538,000 rows per
reference month (2026-08: 538,169; 2026-09: 538,099), so years of history mean tens of millions
of rows. The raw layer is loaded by month (`scripts/direct_load.py` replaces the `competencia`
partition and stamps it with `_loaded_at`). CVM republishes the file of the current month every
day, and occasionally corrects earlier months, so a month already in the fact can come back with
changed, new or withdrawn rows. The other marts are small (`dim_fundo` ~82,000 rows,
`dim_data` a few hundred, `fct_captacao_mensal` ~25,600 rows per month).

## Decision

- `fct_informe_diario` is `incremental` with `incremental_strategy = 'delete+insert'` and
  `unique_key = 'dt_mes_competencia'`: the reference month is the unit of reprocessing.
- The `is_incremental()` filter selects every month whose latest load in staging
  (`max(_loaded_at)`) differs from the one stored in the fact, or that is not in the fact yet.
  Those months are deleted from the fact and inserted again as a whole; unchanged months are
  not touched. This covers the republished current month, a corrected older month and a
  backfill of an older month, which a "latest month only" filter would miss.
- The fact keeps `dt_mes_competencia` and `_loaded_at` for that purpose.
- Everything else stays `table`, including `fct_captacao_mensal`, which is rebuilt from the daily
  fact in about a second per month loaded.
- `dbt build --full-refresh` rebuilds the fact from scratch. It is needed after a change in
  `dim_fundo` that should move existing facts to another version (for example a CNPJ that was
  on the unknown member and appears later in the registry), since months whose load did not
  change are not reprocessed.

## Alternatives considered

- **`table` for the fact.** Simplest and always consistent, and fast today (about 3 s for two
  months in DuckDB), but the cost grows with every month loaded and the RF-03 plan
  (`dimensional-model.md`) asks for an incremental daily fact. Rejected.
- **`merge` / `delete+insert` on the row grain** (`cnpj_fundo_classe`, `id_subclasse`,
  `dt_competencia`). Updates changed rows but never removes a row CVM withdrew from a
  republished month, and the grain has a nullable column (`id_subclasse`), which makes key
  matching awkward. Rejected in favour of replacing the whole month.
- **`append` with a filter on `dt_competencia > max(dt_competencia)`.** Cheapest, but loses every
  republication of the current month. Rejected.
- **`insert_overwrite` by partition.** Not supported by dbt-duckdb 1.8; `delete+insert` by month
  has the same effect.

## Consequences

- An incremental run with no new load is a no-op (0 months selected) and leaves the fact
  identical; CI runs `dbt build --select fct_informe_diario` a second time and checks that the
  row count does not change. The singular test `assert_fct_informe_diario_matches_staging`
  proves, month by month, that the fact has the same rows as staging from the latest load.
- Simulated republication (2026-09 with a new `_loaded_at` and 10 rows withdrawn): only 2026-09
  was reprocessed (538,099 -> 538,089 rows), 2026-08 was untouched, and a full refresh gave the
  same counts.
- `sk_fundo` lookups are frozen for months that are not reprocessed; a `dim_fundo` change only
  reaches old months after a full refresh (see above). With the SCD2 history (3.4) new versions
  start on the snapshot date, so older facts keep the same version anyway.
