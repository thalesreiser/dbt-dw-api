# 005 - Fund registry source after CVM Resolution 175

- **Status:** accepted
- **Date:** 2026-10-16

## Context

RF-01 needs two sources: the daily report (`informe_diario`) and the fund registry
(`cadastro_fundos`). CVM Resolution 175 split funds into classes and subclasses. Since then:

- the daily report key is `CNPJ_FUNDO_CLASSE` (formerly `CNPJ_FUNDO`), which holds the CNPJ of
  the class for adapted funds and the CNPJ of the fund otherwise;
- CVM publishes a new registry, `registro_fundo_classe.zip` (`registro_fundo.csv`,
  `registro_classe.csv`, `registro_subclasse.csv`), while the legacy `cad_fi.csv` is still
  online but effectively frozen.

Measured on 2026-10-16 with the 2026-09 daily report (25,576 distinct CNPJs): the legacy
`cad_fi.csv` matches only 5.7% of them; class CNPJs match 99.2%, fund CNPJs 99.9%, and class or
fund 100%. Details in [data-source.md](../data-source.md).

## Decision

- Load `registro_fundo.csv` into `raw.cadastro_fundos` and `registro_classe.csv` into a new
  source table `raw.cadastro_classes`. Do not load the legacy `cad_fi.csv`.
- Keep raw tables faithful to the source (CVM column names, `VARCHAR`), as full snapshots.
- Map the daily report to the registry in staging: `CNPJ_FUNDO_CLASSE` with punctuation removed
  joins to `cadastro_classes.CNPJ_Classe`, falling back to `cadastro_fundos.CNPJ_Fundo` for funds
  that report without a class.
- Subclasses (`registro_subclasse.csv`) are out of scope for now; the daily report already
  carries `ID_SUBCLASSE`.

## Alternatives considered

- **Legacy `cad_fi.csv`:** same layout as before and a single file, but covers 5.7% of the
  reporting funds and has bytes DuckDB's latin-1 reader rejects. Rejected.
- **Only `registro_classe.csv`:** simpler, but misses the 0.8% of daily report rows keyed by a
  fund CNPJ and the fund-level attributes (administrator, manager, adaptation date).
- **Join fund and class in the loader:** would hide source quirks (one row per manager,
  repeated ids) inside the extract step instead of in tested dbt models.

## Consequences

- `_sources.yml` declares three tables: `informe_diario`, `cadastro_fundos`, `cadastro_classes`.
- Staging must deduplicate `cadastro_fundos` (one row per fund and manager) and resolve the
  class-or-fund key; `dim_fundo` (RF-03) and the SCD2 snapshot (RF-04) are built on that.
- The P1 Parquet contract should expose the same two registry tables, or the loader mapping for
  `p1-parquet` must be revisited.
