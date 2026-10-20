-- RF-07: dim_fundo.fl_informa_recente agrees with the daily fact. A row fails when the flag is
-- true but the CNPJ has no report in the latest month of fct_informe_diario, or false while it
-- has one (the unknown member is always false). Computed independently of the model, which
-- reads staging to avoid a dependency cycle with the fact.

with mes_recente as (

    select max(dt_mes_competencia) as dt_mes_competencia
    from {{ ref('fct_informe_diario') }}

),

cnpjs_recentes as (

    select distinct f.cnpj_fundo_classe
    from {{ ref('fct_informe_diario') }} as f
    inner join mes_recente as m
        on f.dt_mes_competencia = m.dt_mes_competencia

)

select
    d.sk_fundo,
    d.cnpj_fundo_classe,
    d.fl_informa_recente
from {{ ref('dim_fundo') }} as d
left join cnpjs_recentes as r
    on d.cnpj_fundo_classe = r.cnpj_fundo_classe
where d.fl_informa_recente
    is distinct from (d.tp_registro <> 'DESCONHECIDO' and r.cnpj_fundo_classe is not null)
