-- RF-03 (3.2): every year of dim_data is covered by the holidays seed (at least the 8 fixed
-- national holidays and the 4 Easter-based days). A year past the end of the seed would make
-- every holiday a business day silently: regenerate it with scripts/generate_national_holidays.py.

with anos as (

    select distinct nr_ano from {{ ref('dim_data') }}

),

feriados as (

    select extract(year from dt_feriado) as nr_ano, count(*) as nr_feriados
    from {{ ref('feriados_nacionais') }}
    group by 1

)

select a.nr_ano, coalesce(f.nr_feriados, 0) as nr_feriados
from anos as a
left join feriados as f
    on f.nr_ano = a.nr_ano
where coalesce(f.nr_feriados, 0) < 12
