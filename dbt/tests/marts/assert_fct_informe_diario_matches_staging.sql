-- RF-03 (3.3) / ADR 003: the incremental fact holds exactly the staging rows, month by month,
-- from the latest load of each month. Fails on a missing or extra month, a different row count
-- (a duplicated or lost row after an incremental run) or a month left on an older load.
-- Run after a second `dbt build --select fct_informe_diario`, it proves the run is idempotent.

with stg as (

    select dt_mes_competencia, count(*) as nr_linhas, max(_loaded_at) as _loaded_at
    from {{ ref('stg_cvm__informe_diario') }}
    group by dt_mes_competencia

),

fct as (

    select dt_mes_competencia, count(*) as nr_linhas, max(_loaded_at) as _loaded_at
    from {{ ref('fct_informe_diario') }}
    group by dt_mes_competencia

)

select
    coalesce(s.dt_mes_competencia, f.dt_mes_competencia) as dt_mes_competencia,
    s.nr_linhas as nr_linhas_staging,
    f.nr_linhas as nr_linhas_fato,
    s._loaded_at as _loaded_at_staging,
    f._loaded_at as _loaded_at_fato
from stg as s
full outer join fct as f
    on f.dt_mes_competencia = s.dt_mes_competencia
where s.nr_linhas is distinct from f.nr_linhas
   or s._loaded_at is distinct from f._loaded_at
