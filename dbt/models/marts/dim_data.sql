-- RF-03 (3.2): calendar dimension. Grain: one row per calendar day (sk_data), from the first
-- reference month loaded to the end of the current year. Design: docs/dimensional-model.md.
--
-- The spine starts at a fixed lower bound (the first year of the holidays seed) and is then cut
-- at the first month loaded, so the range follows the data. fl_dia_util = weekday that is not a
-- national holiday (seed feriados_nacionais; no state or municipal holidays).

with spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2000-01-01' as date)",
        end_date="cast(date_trunc('year', current_date) + interval 1 year as date)"
    ) }}

),

primeiro_mes as (

    select min(dt_mes_competencia) as dt_inicio
    from {{ ref('stg_cvm__informe_diario') }}

),

dias as (

    select cast(s.date_day as date) as dt
    from spine as s
    cross join primeiro_mes as p
    where cast(s.date_day as date) >= p.dt_inicio

),

-- Two holidays can fall on the same date (Good Friday was Tiradentes in 2000): one row per date.
feriados as (

    select
        dt_feriado,
        string_agg(nm_feriado, ' / ' order by nm_feriado) as nm_feriado
    from {{ ref('feriados_nacionais') }}
    group by dt_feriado

)

select
    d.dt                                                    as sk_data,
    cast(date_trunc('month', d.dt) as date)                 as sk_mes,
    cast(extract(year from d.dt) as integer)                as nr_ano,
    cast(extract(quarter from d.dt) as integer)             as nr_trimestre,
    cast(extract(month from d.dt) as integer)               as nr_mes,
    cast(extract(day from d.dt) as integer)                 as nr_dia,
    -- ISO weekday: 1 = Monday ... 7 = Sunday
    cast(isodow(d.dt) as integer)                           as nr_dia_semana,
    cast(date_trunc('month', d.dt) as date)                 as dt_inicio_mes,
    cast(last_day(d.dt) as date)                            as dt_fim_mes,
    isodow(d.dt) in (6, 7)                                  as fl_fim_de_semana,
    f.dt_feriado is not null                                as fl_feriado,
    f.nm_feriado,
    isodow(d.dt) not in (6, 7) and f.dt_feriado is null     as fl_dia_util
from dias as d
left join feriados as f
    on f.dt_feriado = d.dt
