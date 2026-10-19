# 007 - Registry snapshot: source, change detection and hard deletes

- **Status:** accepted
- **Date:** 2026-10-19

## Context

RF-04 asks for the history of registry changes (SCD type 2): given a change in the registry,
both versions must exist with their validity. The CVM registry is a daily full extract with no
change timestamp per row, and after Resolution 175 it is split into fund and class files
([ADR 005](005-cvm-registry-after-resolution-175.md)). `dim_fundo` is keyed on the reporting
CNPJ (`cnpj_fundo_classe`), built from `int_fundo_classe__unificado`, which was ephemeral; dbt
snapshots cannot select from an ephemeral model. Task 3.3 resolves facts to `dim_fundo` with the
half-open interval `dt >= dt_valido_de and (dt_valido_ate is null or dt < dt_valido_ate)`.

## Decision

1. **One snapshot of the unified registry**, `snp_cvm__fundo_classe` (schema `snapshots`), over
   `int_fundo_classe__unificado`, now materialized as a view (schema `intermediate`). The
   snapshot has the same grain and key as `dim_fundo`, so the dimension is a thin layer on top.
2. **`check` strategy** with an explicit `check_cols` list: every attribute of the unified row
   (names, registry ids, status, types, classifications, administrator, manager, registration
   date). There is no reliable `updated_at` in the source, so `timestamp` is not an option.
3. **`invalidate_hard_deletes = false`.** A CNPJ that disappears from the registry keeps its
   last version open. The registry keeps cancelled funds, so a disappearance is more likely an
   extract problem than a business event, and facts that still report the CNPJ must keep
   resolving to a current version (one current version per CNPJ is a tested rule).
4. **Validity in `dim_fundo`:** dates of `dbt_valid_from` / `dbt_valid_to`; the first version
   of each CNPJ starts at 1900-01-01 (no history before the first snapshot); several versions
   opened on the same day collapse into the last one of that day, so `sk_fundo =
   hash(cnpj_fundo_classe, dt_valido_de)` stays unique and stable.

## Alternatives considered

- **Two snapshots (fund and class files) joined in the mart.** Closer to the sources, but the
  SCD2 join of two histories (interval intersection) is complex and error-prone for a gain the
  API does not need.
- **Keep the model ephemeral and repeat its SQL inside the snapshot.** Duplicates the
  unification rules in two places.
- **`invalidate_hard_deletes = true`.** Records the disappearance, but leaves CNPJs with no
  current version, so new facts of such a CNPJ would fall to the unknown member.

## Consequences

- History accumulates only where the DuckDB file persists. CI starts from an empty file every
  run, so it proves the mechanism with a simulation (`scripts/simulate_scd2_change.py`, which
  changes one class name on a copy of the warehouse and asserts two contiguous versions), not
  real history.
- The first version is an approximation: facts older than the first snapshot are attributed to
  the registry as first seen, not as it really was then.
- A change of any tracked attribute, including the kept registry id after a re-registration,
  opens a new version; intraday changes are not kept.
- Removals from the registry are not visible in `dim_fundo`; if they matter later, switch to
  `invalidate_hard_deletes = true` and resolve facts of closed CNPJs to their last version.
