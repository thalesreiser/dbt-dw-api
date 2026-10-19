-- RF-03 (3.3): monthly net inflows fact (RN-01). Grain: one row per fund class per month
-- (cnpj_fundo_classe, sk_mes); subclass rows are rolled up into their class.
-- Design: docs/dimensional-model.md.
--
-- Built from fct_informe_diario (not from staging), so both facts agree by construction. A
-- table: it is small (one row per class per month) and a full rebuild follows every
-- reprocessed month of the daily fact.

with diario as (

    select * from {{ ref('fct_informe_diario') }}

),

-- Class totals per day: subclass rows are summed into their class (ADR 006: a CNPJ never
-- reports at class level and per subclass on the same day, so there is no double counting).
dia as (

    select
        cnpj_fundo_classe,
        dt_mes_competencia,
        sk_data,
        -- One CNPJ and date resolve to a single dim_fundo version.
        any_value(sk_fundo)                 as sk_fundo,
        sum(vl_captc_dia)                   as vl_captc_dia,
        sum(vl_resg_dia)                    as vl_resg_dia,
        sum(vl_captc_liquida_dia)           as vl_captc_liquida_dia,
        sum(vl_patrim_liq)                  as vl_patrim_liq,
        sum(nr_cotst)                       as nr_cotst
    from diario
    group by cnpj_fundo_classe, dt_mes_competencia, sk_data

)

select
    -- The dim_fundo version valid on the last reported day of the month.
    arg_max(sk_fundo, sk_data)                          as sk_fundo,
    dt_mes_competencia                                  as sk_mes,
    cnpj_fundo_classe,
    coalesce(sum(vl_captc_dia), 0)                      as vl_captc_mes,
    coalesce(sum(vl_resg_dia), 0)                       as vl_resg_mes,
    -- RN-01: net inflows = inflows - redemptions in the month.
    sum(vl_captc_liquida_dia)                           as vl_captc_liquida_mes,
    -- Semi-additive: the value on the last reported day (even if null), never a sum across days.
    arg_max_null(vl_patrim_liq, sk_data)                as vl_patrim_liq_fim_mes,
    cast(arg_max_null(nr_cotst, sk_data) as integer)    as nr_cotst_fim_mes,
    max(sk_data)                                        as dt_ultimo_informe,
    cast(count(*) as integer)                           as nr_dias_informados
from dia
group by cnpj_fundo_classe, dt_mes_competencia
