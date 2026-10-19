# Naming conventions (RNF-05)

One convention for every layer of the warehouse, applied from staging onwards. Identifiers are
lower-case `snake_case`; table and column names mirror the CVM domain in Portuguese
(`fundo` = fund, `classe` = class, `cota` = share, `captação` = inflow, `resgate` = redemption),
while code, comments and documentation are in English.

## Layers and models

| Layer | Folder | Schema | Materialization | Model name | Example |
|---|---|---|---|---|---|
| Sources | `dbt/models/staging/_sources.yml` | `raw` | loaded by `scripts/direct_load.py` | CVM table name | `raw.informe_diario` |
| Staging | `dbt/models/staging/` | `staging` | view | `stg_<source>__<table>` | `stg_cvm__informe_diario` |
| Intermediate | `dbt/models/intermediate/` | (none) | ephemeral | `int_<entity>__<transformation>` | `int_fundo_classe__unificado` |
| Marts | `dbt/models/marts/` | `marts` | table / incremental | `dim_<entity>`, `fct_<process>` | `dim_fundo`, `fct_informe_diario` |
| Seeds | `dbt/seeds/` | `seeds` | seed (CSV) | `<entity in Portuguese, plural>` | `feriados_nacionais` |
| Snapshots (planned) | `dbt/snapshots/` | to be set in RF-04 | snapshot (SCD2) | `snp_<source>__<table>` | `snp_cvm__cadastro_classes` |

- **Staging** is the only layer that reads `source()`: one model per source table, no joins, no
  business rules. It renames, casts, standardizes and, where the source repeats a key,
  deduplicates deterministically to the documented grain ([ADR 006](adr/006-staging-grain-and-deduplication.md)).
- Every model has a YAML entry next to it (`_<source>__models.yml` in staging, `_int__models.yml` in intermediate, `_marts.yml` in
  marts) describing the model, its **grain**, and every column.
- Singular tests live in `dbt/tests/<layer>/` and are named `assert_<what_must_hold>.sql`;
  generic tests live in `dbt/tests/generic/`.
- Schemas are the layer names themselves (`staging`, `marts`), via `dbt/macros/generate_schema_name.sql`.

## Column prefixes

| Prefix | Meaning | Type | Standardization | Example |
|---|---|---|---|---|
| `id_` | Identifier assigned by the source (registry id, subclass id) | `varchar` | trimmed, blank -> null | `id_registro_fundo`, `id_subclasse` |
| `sk_` | Surrogate key created in the marts | `varchar` (hash); `date` for the date dimension | `dbt_utils.generate_surrogate_key` | `sk_fundo`, `sk_data` |
| `cnpj_` | CNPJ (legal entity tax id) | `varchar(14)` | punctuation removed, upper case, left-padded to 14; test `valid_cnpj` | `cnpj_fundo_classe` |
| `cpf_cnpj_` | CPF (11 digits, natural person) or CNPJ | `varchar` | punctuation removed, no padding; test `valid_cpf_cnpj` | `cpf_cnpj_gestor` |
| `cd_` | Code assigned by an authority, not used as a key | `varchar` | trimmed | `cd_cvm` |
| `nm_` | Name or free text | `varchar` | trimmed, whitespace runs collapsed, case and accents kept | `nm_denominacao_social` |
| `tp_` | Categorical type/class code | `varchar` | upper case, accents removed, whitespace collapsed; `accepted_values` test | `tp_fundo`, `tp_publico_alvo` |
| `sit_` | Status (situação) | `varchar` | same as `tp_` | `sit_fundo` |
| `fl_` | Boolean flag | `boolean` | CVM `S`/`N` -> `true`/`false`; `N/A` and blanks -> null | `fl_exclusivo` |
| `dt_` | Calendar date | `date` | ISO `YYYY-MM-DD`; a malformed value fails the build | `dt_competencia` |
| `vl_` | Monetary value in BRL | `decimal(18,2)`; share value `decimal(27,12)` | point as decimal separator, sign kept | `vl_patrim_liq`, `vl_quota` |
| `nr_` | Count or number of items | `integer` | | `nr_cotst`, `nr_gestor` |
| `_` (leading underscore) | Lineage metadata added by the loader | as loaded | kept unchanged | `_source`, `_source_file`, `_loaded_at` |

Rules:

- The part after the prefix keeps the CVM name in lower case (`VL_PATRIM_LIQ` -> `vl_patrim_liq`,
  `NR_COTST` -> `nr_cotst`); a prefix is added where CVM has none (`CAPTC_DIA` -> `vl_captc_dia`,
  `Situacao` -> `sit_fundo`, `Data_Registro` -> `dt_registro`).
- `dt_competencia` is the reference date of a daily report; `dt_mes_competencia` is the first day
  of the reference month of the source file.
- CNPJs are stored without punctuation; formatting (`00.000.000/0000-00`) is a presentation
  concern. The alphanumeric CNPJ (12 alphanumeric characters + 2 check digits, issued from July
  2026) is accepted by the same rule and test.
- Precision: CVM publishes share values with 12 decimal places (up to 11 integer digits in
  2026-09), hence `decimal(27,12)`; every other amount has 2 decimal places and fits
  `decimal(18,2)` (largest in 2026-09: 14 integer digits).
- Tables use singular entity names (`dim_fundo`, not `dim_fundos`), except the staging models,
  which keep the source table name.

The helpers that implement these rules are in `dbt/macros/staging_helpers.sql`
(`clean_text`, `clean_name`, `clean_code`, `clean_cnpj`, `clean_cpf_cnpj`, `to_date`,
`to_decimal`, `to_integer`, `to_flag`).
