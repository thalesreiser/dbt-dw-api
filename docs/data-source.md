# Data source: CVM open data (RF-01, R-04, R-P3-01)

P3 normally consumes the Parquet produced by P1 ([aws-fundos-pipeline](https://github.com/thalesreiser/aws-fundos-pipeline)).
While P1 is not ready (risk R-P3-01), `scripts/direct_load.py` loads the CVM open data straight
into the DuckDB `raw` schema. This page records what the source looks like today (R-04: check the
source first) and how it maps to the raw tables declared in `dbt/models/staging/_sources.yml`.

**Checked on:** 2026-10-16, with `curl -sI`, the directory listings and the first lines of each file.

## Files

| File | URL | Size (compressed / CSV) | Update |
|---|---|---|---|
| Daily report, one zip per month | `https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_YYYYMM.zip` | ~11-12 MB / ~54 MB (2026-09: 538,072 rows) | current and previous months republished daily; older years under `.../DADOS/HIST/` |
| Fund/class/subclass registry (Resolution 175) | `https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip` | 7 MB / 45 MB (3 CSVs) | daily |
| Legacy fund registry | `https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv` | 17 MB | daily, but frozen in practice (see below) |
| Legacy registry history | `https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip` | 18 MB | not used |

All files: CSV, `;` separator, header on the first line, **latin-1** encoding, dates `YYYY-MM-DD`,
decimal point `.`.

## Layouts

**`inf_diario_fi_YYYYMM.csv`** (raw table `raw.informe_diario`)

```
TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST
CLASSES - FIF;00.017.024/0001-53;;2026-09-01;1107741.39;44.636723400000;1214792.63;0.00;0.00;1
```

- After CVM Resolution 175 the key columns were renamed: `CNPJ_FUNDO` -> `CNPJ_FUNDO_CLASSE`,
  `TP_FUNDO` -> `TP_FUNDO_CLASSE`, and `ID_SUBCLASSE` was added. The loader maps the old names
  to the new ones, so older months land in the same columns (`ID_SUBCLASSE` stays null).
- `CNPJ_FUNDO_CLASSE` is formatted (`00.000.000/0000-00`). In 2026-09: 25,576 distinct CNPJs;
  `TP_FUNDO_CLASSE` is `CLASSES - FIF` (537,677 rows), `CLASSE FIF/FAPI` (273) or `FI` (122).
- Grain: one row per (`CNPJ_FUNDO_CLASSE`, `ID_SUBCLASSE`, `DT_COMPTC`); verified unique for
  2026-09 and enforced by a source test. 20,185 rows carry a subclass id.

**`registro_fundo_classe.zip`** contains:

| Member | Raw table | Rows (2026-10-16) | Key columns |
|---|---|---|---|
| `registro_fundo.csv` | `raw.cadastro_fundos` | 90,624 | `ID_Registro_Fundo`, `CNPJ_Fundo` (digits only), `Denominacao_Social`, `Situacao`, `Tipo_Fundo`, `Data_Adaptacao_RCVM175`, administrator and manager |
| `registro_classe.csv` | `raw.cadastro_classes` | 36,872 | `ID_Registro_Fundo`, `ID_Registro_Classe`, `CNPJ_Classe` (digits only), `Tipo_Classe`, `Denominacao_Social`, `Situacao`, `Classificacao_Anbima` |
| `registro_subclasse.csv` | not loaded yet | 10,699 | `ID_Registro_Classe`, `ID_Subclasse` |

Source quirks (handled in staging, not in raw): `registro_fundo.csv` has one row per fund **and
manager**, so `ID_Registro_Fundo` repeats (81,710 distinct CNPJs); a handful of
`ID_Registro_Classe` values repeat as well.

## Key mapping after Resolution 175

Daily report CNPJs of 2026-09 (25,576) against each registry, after stripping punctuation:

| Registry | Matches |
|---|---|
| `registro_classe.CNPJ_Classe` | 25,360 (99.2%) |
| `registro_fundo.CNPJ_Fundo` | 25,547 (99.9%) |
| class **or** fund | **25,576 (100%)** |
| legacy `cad_fi.csv` | 1,460 (5.7%) |

The legacy `cad_fi.csv` is no longer maintained for active funds (only 22 rows are
`EM FUNCIONAMENTO NORMAL`; adapted funds moved to the new registry) and contains stray bytes
(`0x83`) that DuckDB's latin-1 reader rejects. Decision: use `registro_fundo_classe.zip`
([ADR 005](adr/005-cvm-registry-after-resolution-175.md)).

## How the loader stores it

- Raw tables keep the CVM column names and every value as `VARCHAR`; typing and renaming to
  snake_case Portuguese happen in staging (RF-02).
- Extra columns: `competencia` (reference month `YYYY-MM`, daily report only), `_source`
  (`cvm` or `p1-parquet`), `_source_file` and `_loaded_at` (UTC load timestamp, used by
  `dbt source freshness`).
- Files are transcoded latin-1 -> UTF-8 in Python before DuckDB reads them.
- Idempotency: a reload replaces the reference months it contains in `raw.informe_diario`;
  the registry tables are full snapshots replaced on every load.
- Default: only the previous (last complete) reference month, about 19 MB of downloads.

## P1 Parquet (`--source p1-parquet`)

Expected layout under `--path`: `informe_diario/**/*.parquet`, `cadastro_fundos/**/*.parquet`
and `cadastro_classes/**/*.parquet` (Hive partitions allowed). Columns are assumed to keep the
CVM names; `competencia` is taken from a column/partition of that name or derived from
`DT_COMPTC`. Values are cast to `VARCHAR` so both sources produce the same raw contract. To be
revisited when P1 publishes its gold/silver contract.

## Reachability

The CI job `sources` downloads the real files from a GitHub-hosted runner on every push/PR, so a
CVM outage or a layout change shows up as a red build instead of a silent gap.
