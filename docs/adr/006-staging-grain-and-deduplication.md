# 006 - Grain and deduplication of the staging models

- **Status:** accepted
- **Date:** 2026-10-17

## Context

RF-02 asks for one `stg_` model per source with standardized columns, and the dimension layer
(RF-03, `dim_fundo`) needs exactly one row per fund and per class. Two of the three sources
repeat their natural key ([ADR 005](005-cvm-registry-after-resolution-175.md),
[data-source.md](../data-source.md)). Measured on 2026-10-17 (registry snapshot of that day,
daily report 2026-09):

| Source | Rows | Distinct key | Why the key repeats |
|---|---|---|---|
| `informe_diario` | 538,099 | 538,099 (`CNPJ_FUNDO_CLASSE`, `ID_SUBCLASSE`, `DT_COMPTC`) | does not repeat |
| `cadastro_fundos` | 90,646 | 89,502 `ID_Registro_Fundo` | one row per fund **and manager** (1,048 funds have 2-4 managers) plus 17 repeated (fund, manager) rows; the 17 fund-level columns are identical across the rows of the same id (1,058 repeated ids, 1,058 distinct fund-level tuples) |
| `cadastro_classes` | 36,869 | 36,865 `ID_Registro_Classe` | 4 ids appear twice: 1 exact duplicate, 3 differ only in the custodian or the controller |

`CNPJ_Fundo` (81,732 distinct) and `CNPJ_Classe` (36,857 distinct) are not unique either: a CNPJ
can have more than one registry id (e.g. a fund cancelled and registered again).

## Decision

- **`stg_cvm__informe_diario`:** grain (`cnpj_fundo_classe`, `id_subclasse`, `dt_competencia`),
  no rows dropped, enforced by `dbt_utils.unique_combination_of_columns` (a null
  `id_subclasse`, a class-level report, groups as one value).
- **`stg_cvm__cadastro_fundos`:** one row per `id_registro_fundo`. Rows are ranked with
  `qualify row_number() over (partition by id_registro_fundo order by cpf_cnpj_gestor nulls last,
  nm_gestor nulls last, tp_pessoa_gestor nulls last) = 1`, i.e. the manager columns describe the
  manager with the lowest CPF/CNPJ, and `nr_gestor` counts the distinct managers of the fund.
  The singular test `assert_cadastro_fundos_constant_per_id` fails if a fund-level attribute
  ever differs between rows of the same id, which would make this pick lose data.
- **`stg_cvm__cadastro_classes`:** one row per `id_registro_classe`, keeping the row with the
  lowest custodian CNPJ, then the lowest controller CNPJ (nulls last, then by name). Guarded by
  `assert_cadastro_classes_constant_per_id` on every other class attribute.
- The registry id, not the CNPJ, is the key of both registry models; resolving a daily report
  CNPJ to one registry entry (class first, then fund, ADR 005) is a modeling decision for the
  intermediate/marts layer (RF-03).

## Alternatives considered

- **Keep the multi-row grain (fund x manager) in staging:** most faithful, but every consumer
  would have to deduplicate again, and `unique` could not be tested on the registry id.
- **Separate fund-manager bridge model:** keeps every manager; not needed by any requirement
  yet (no endpoint or mart uses managers). Can be added later as
  `stg_cvm__cadastro_fundos_gestores` from the same source without changing this grain.
- **Pick by load order or `any_value`:** not deterministic across reloads; rejected.
- **Deduplicate in the loader:** hides source quirks from the tests (same reason as ADR 005).

## Consequences

- `dim_fundo` (RF-03) and the SCD2 snapshot (RF-04) can rely on `unique` registry ids.
- Only the first manager of multi-manager funds (about 1.2% of the funds) is exposed; the
  count is kept in `nr_gestor`.
- If CVM starts varying fund- or class-level attributes within an id, the guard tests fail
  and this decision must be revisited.
