# 03 - Specification

> Phase 3 (ISO/IEC/IEEE 29148). Requirements with ID, verifiable acceptance criteria and data model.
> Priorities and the full requirement list are in [02](02-analysis-and-prioritization.md); how
> each criterion was executed is in [05](05-validation.md).

## User stories (INVEST + Gherkin)

Personas from [01](01-vision-and-scope.md): the **analyst** (consumes the data), the
**reviewer** (checks quality) and the **operator** (Thales, runs the environment).

```gherkin
Feature: Warehouse sources and staging
  Scenario: RF-01 - source tables are available in dbt
    Given the operator ran `make load` for a CVM reference month
    When `dbt source freshness` and `make row-counts` run
    Then cvm.informe_diario, cvm.cadastro_fundos and cvm.cadastro_classes exist
    And each has at least one row and a fresh `_loaded_at`

  Scenario: RF-02 - every source has a staging model
    Given the raw CVM tables
    When `make staging` runs
    Then each source has one stg_cvm__* view with typed, renamed columns
    And the staging tests (keys, not_null, accepted_values, valid CNPJ) pass

Feature: Dimensional model and history
  Scenario: RF-03 - facts reference dimensions with no orphans
    Given the staging models are built
    When `make marts` runs
    Then every sk_fundo and sk_data of fct_informe_diario and fct_captacao_mensal exists in its dimension

  Scenario: RF-04 - a registry change keeps both versions
    Given a fund class with one version in the snapshot
    When its name changes in the registry and the snapshot runs again
    Then dim_fundo has two versions with contiguous [dt_valido_de, dt_valido_ate) ranges
    And only the new one has fl_versao_atual = true

Feature: Data quality and documentation
  Scenario: RF-05 - a test fails on invalid data
    Given a copy of the warehouse with a row that breaks RN-01 (or a null key, an orphan, a future date)
    When `dbt test` runs
    Then exactly the tests guarding that rule fail

  Scenario: RF-06 - every mart is documented with lineage
    When `make docs docs-coverage` runs
    Then every model, snapshot, seed, exposure and column has a description
    And the lineage graph links the sources to the fundos_api exposure

Feature: Read-only API
  Scenario: RF-07 - list funds by status, paginated
    Given the API key in the X-API-Key header
    When the analyst calls GET /v1/fundos?situacao=EM FUNCIONAMENTO NORMAL&limit=2
    Then the response is 200 with at most 2 items, all with that status, and the total of matches

  Scenario: RF-08 - time series of one fund
    When the analyst calls GET /v1/fundos/{cnpj}/serie?inicio=...&fim=...
    Then the daily points are returned ordered by date ascending
    But an unknown CNPJ gives 404 and an invalid period gives 422

  Scenario: RF-09 - net inflow ranking of a month
    When the analyst calls GET /v1/rankings/captacao?mes=YYYY-MM&top=N
    Then the N funds with the largest net inflows (inflows - redemptions) are returned in order

  Scenario: RF-10 - key and rate limit
    When a /v1/* route is called without a key, or with a wrong key
    Then the response is 401
    When a key exceeds RATE_LIMIT_REQUESTS in the window
    Then the response is 429 with Retry-After

  Scenario: RF-11 - the API honours its OpenAPI contract
    When Schemathesis generates valid and invalid requests for every operation
    Then no response is a 5xx or deviates from the documented status, schema or headers

Feature: Operation
  Scenario: RNF-04 - the whole environment runs with Docker Compose
    Given Docker, a copy of .env.example as .env and network access to dados.cvm.gov.br
    When the operator runs `make up`
    Then the warehouse service loads the CVM months and `dbt build` passes
    And the API answers /health with status ok on 127.0.0.1:8000
```

## Data model

The marts the API reads (schema `marts`). Full design, grain, additivity and lineage in
[dimensional-model.md](dimensional-model.md); every column is also described in the
[dbt docs](https://thalesreiser.github.io/dbt-dw-api/).

| Table | Column | Type | Description | Rule |
|---|---|---|---|---|
| `dim_fundo` | `sk_fundo` | varchar (PK) | Surrogate key of a fund/class version (MD5 of CNPJ + `dt_valido_de`), plus one unknown member (CNPJ `00000000000000`) | unique, not null |
| `dim_fundo` | `cnpj_fundo_classe` | varchar(14) | Reporting CNPJ: the class, or the fund when it has no class | 14 digits, valid check digits; unique among current versions |
| `dim_fundo` | `tp_registro` | varchar | `CLASSE`, `FUNDO` (fund without class) or `DESCONHECIDO` (unknown member) | accepted values |
| `dim_fundo` | `nm_denominacao_social` | varchar | Legal name of the class (or fund) | public registry data |
| `dim_fundo` | `tp_fundo`, `tp_classe` | varchar | Fund type (e.g. `FIF`, `FIDC`) and class type | API filters |
| `dim_fundo` | `sit_fundo_classe` | varchar | Registry status as published by CVM | accepted values; API filter `situacao` |
| `dim_fundo` | `cpf_cnpj_gestor`, `nm_gestor` | varchar | Manager; may identify a natural person | **never exposed by the API** (LGPD) |
| `dim_fundo` | `fl_informa_recente` | boolean | Has a daily report in the latest month loaded | matches the fact |
| `dim_fundo` | `dt_valido_de`, `dt_valido_ate`, `fl_versao_atual` | date, date, boolean | SCD2 validity `[de, ate)`; one current version per CNPJ | no overlaps, contiguous (RF-04) |
| `dim_data` | `sk_data` | date (PK) | Calendar day | unique, not null |
| `dim_data` | `sk_mes` | date | First day of the month | RN-02 |
| `dim_data` | `fl_dia_util`, `fl_feriado` | boolean | Business day: not a weekend nor a national holiday (seed `feriados_nacionais`) | national holidays only |
| `fct_informe_diario` | `sk_fundo`, `sk_data` | FK | Version valid on the date (else unknown member), report day | `relationships` (no orphans) |
| `fct_informe_diario` | `id_subclasse` | varchar | Subclass, null for a class without subclasses | part of the grain |
| `fct_informe_diario` | `vl_quota` | decimal(p,12) | Share value | non-negative |
| `fct_informe_diario` | `vl_patrim_liq`, `vl_total` | decimal(p,2) | Net assets and total portfolio, BRL | RN-02 |
| `fct_informe_diario` | `vl_captc_dia`, `vl_resg_dia` | decimal(p,2) | Inflows and redemptions of the day, BRL | non-negative (RN-02) |
| `fct_informe_diario` | `vl_captc_liquida_dia` | decimal(p,2) | Net inflow of the day | = inflows - redemptions (RN-01) |
| `fct_informe_diario` | `nr_cotst` | integer | Number of shareholders (aggregate count only) | non-negative |
| `fct_informe_diario` | `dt_mes_competencia`, `_loaded_at` | date, timestamp | Reference month and load time | incremental unit (ADR 003) |
| `fct_captacao_mensal` | `sk_fundo`, `sk_mes` | FK | Fund/class version and month | `relationships` (no orphans) |
| `fct_captacao_mensal` | `vl_captc_mes`, `vl_resg_mes`, `vl_captc_liquida_mes` | decimal(p,2) | Monthly inflows, redemptions and net inflows | RN-01; reconciles with the daily fact |
| `fct_captacao_mensal` | `vl_patrim_liq_fim_mes`, `nr_cotst_fim_mes` | decimal(p,2), integer | Net assets and shareholders on the last reported day | semi-additive |
| `fct_captacao_mensal` | `dt_ultimo_informe`, `nr_dias_informados` | date, integer | Last reported day and number of reported days in the month | within the month |

Grain: `fct_informe_diario` = 1 row per class (or subclass) per day; `fct_captacao_mensal` =
1 row per class per month; `dim_fundo` = 1 row per reporting CNPJ per version; `dim_data` =
1 row per calendar day.
