{% docs __overview__ %}
# fundos_dw: CVM investment funds warehouse

Data warehouse of the CVM (Brazilian Securities Commission) investment fund open data, built
with dbt on DuckDB and served by a read-only REST API (`fundos_api`).

**Layers** (RNF-05, `docs/naming-conventions.md`):

| Layer | Models | Materialization |
|---|---|---|
| sources (`raw`) | `cvm.informe_diario`, `cvm.cadastro_fundos`, `cvm.cadastro_classes` | loaded as-is by `scripts/direct_load.py` |
| staging | `stg_cvm__*`: renamed, typed, standardized, one per source | view |
| intermediate | `int_fundo_classe__unificado`: fund and class registries at the daily report key | view |
| snapshot | `snp_cvm__fundo_classe`: SCD type 2 history of the unified registry | snapshot |
| seed | `feriados_nacionais`: national holidays (business days) | table |
| marts | `dim_fundo`, `dim_data`, `fct_informe_diario`, `fct_captacao_mensal` (star schema) | table / incremental |
| exposure | `fundos_api`: the REST API that reads the marts | |

Open the lineage graph (bottom-right button) to follow a mart back to its sources. Design:
`docs/dimensional-model.md`; requirements: `docs/02-analysis-and-prioritization.md`.
{% enddocs %}

{% docs cnpj_fundo_classe %}
Reporting CNPJ, 14 characters without punctuation: the CNPJ of the class, else of the fund when
it reports without a class (not adapted to CVM Resolution 175). Natural key of the fund/class
and the key of the daily report; same name, type and meaning in every model that carries it.
{% enddocs %}

{% docs sk_fundo_fk %}
FK to `dim_fundo.sk_fundo`: the version of the same `cnpj_fundo_classe` valid on the fact date,
i.e. the date in [`dt_valido_de`, `dt_valido_ate`); the unknown member
(`cnpj_fundo_classe = '00000000000000'`) when there is none.
{% enddocs %}

{% docs dt_valido_de %}
Start of the version (inclusive): date of the snapshot's `dbt_valid_from`. The first version of
every CNPJ starts at 1900-01-01 (no registry history before the first snapshot), so older facts
resolve to the oldest known version.
{% enddocs %}

{% docs dt_valido_ate %}
End of the version (exclusive): date of the snapshot's `dbt_valid_to`, equal to the
`dt_valido_de` of the next version; null for the current version. Validity is
[`dt_valido_de`, `dt_valido_ate`).
{% enddocs %}

{% docs fl_versao_atual %}
True for the current version of the CNPJ (`dbt_valid_to` is null); exactly one per CNPJ.
{% enddocs %}

{% docs sk_data %}
The calendar date, used as the surrogate key of `dim_data` (type `date`, readable and joinable
without a lookup; `docs/naming-conventions.md`).
{% enddocs %}

{% docs rn_01_captacao_liquida %}
Net inflows (RN-01): inflows minus redemptions, a missing side counted as zero. Additive across
funds and days; RF-09 ranks funds by its monthly sum.
{% enddocs %}

{% docs dbt_updated_at %}
Timestamp dbt records for the version (with the `check` strategy, the time of the snapshot run
that wrote it).
{% enddocs %}

{% docs _loaded_at %}
Load timestamp (UTC) of the rows in the raw layer (`scripts/direct_load.py`); drives
`dbt source freshness` and the incremental filter of `fct_informe_diario`.
{% enddocs %}
