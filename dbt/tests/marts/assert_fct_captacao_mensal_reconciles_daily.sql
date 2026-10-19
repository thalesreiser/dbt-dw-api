-- RF-03 (3.3) / RN-01: monthly net inflows equal the sum of the daily rows of the class in the
-- month (subclasses included), and every (class, month) of the daily fact has exactly one
-- monthly row. Exact comparison: both sides are decimals.

with diario as (

    select
        cnpj_fundo_classe,
        dt_mes_competencia                  as sk_mes,
        sum(vl_captc_liquida_dia)           as vl_captc_liquida_mes,
        count(distinct sk_data)             as nr_dias_informados
    from {{ ref('fct_informe_diario') }}
    group by cnpj_fundo_classe, dt_mes_competencia

)

select
    coalesce(d.cnpj_fundo_classe, m.cnpj_fundo_classe) as cnpj_fundo_classe,
    coalesce(d.sk_mes, m.sk_mes) as sk_mes,
    d.vl_captc_liquida_mes as vl_diario,
    m.vl_captc_liquida_mes as vl_mensal
from diario as d
full outer join {{ ref('fct_captacao_mensal') }} as m
    on m.cnpj_fundo_classe = d.cnpj_fundo_classe
    and m.sk_mes = d.sk_mes
where d.vl_captc_liquida_mes is distinct from m.vl_captc_liquida_mes
   or d.nr_dias_informados is distinct from m.nr_dias_informados
   or m.vl_captc_liquida_mes is distinct from m.vl_captc_mes - m.vl_resg_mes
