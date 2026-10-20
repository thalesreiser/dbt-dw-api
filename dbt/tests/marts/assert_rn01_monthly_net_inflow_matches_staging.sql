-- RF-05 / RN-01: the monthly fact agrees with the staging layer, computed independently of
-- fct_informe_diario. For every class and month of stg_cvm__informe_diario, the monthly inflows,
-- redemptions and net inflows (inflows - redemptions, a missing side as zero) equal the sums of
-- the staging rows, and there is no monthly row without staging rows. Exact comparison: both
-- sides are decimals in BRL (RN-02).

with stg as (

    select
        cnpj_fundo_classe,
        dt_mes_competencia                                              as sk_mes,
        coalesce(sum(vl_captc_dia), 0)                                  as vl_captc_mes,
        coalesce(sum(vl_resg_dia), 0)                                   as vl_resg_mes,
        sum(coalesce(vl_captc_dia, 0) - coalesce(vl_resg_dia, 0))       as vl_captc_liquida_mes
    from {{ ref('stg_cvm__informe_diario') }}
    group by cnpj_fundo_classe, dt_mes_competencia

)

select
    coalesce(s.cnpj_fundo_classe, m.cnpj_fundo_classe) as cnpj_fundo_classe,
    coalesce(s.sk_mes, m.sk_mes) as sk_mes,
    s.vl_captc_liquida_mes as vl_liquida_staging,
    m.vl_captc_liquida_mes as vl_liquida_mensal,
    s.vl_captc_mes as vl_captc_staging,
    m.vl_captc_mes as vl_captc_mensal,
    s.vl_resg_mes as vl_resg_staging,
    m.vl_resg_mes as vl_resg_mensal
from stg as s
full outer join {{ ref('fct_captacao_mensal') }} as m
    on m.cnpj_fundo_classe = s.cnpj_fundo_classe
    and m.sk_mes = s.sk_mes
where s.vl_captc_liquida_mes is distinct from m.vl_captc_liquida_mes
   or s.vl_captc_mes is distinct from m.vl_captc_mes
   or s.vl_resg_mes is distinct from m.vl_resg_mes
