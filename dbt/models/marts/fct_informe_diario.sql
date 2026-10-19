-- RF-03 (3.3): daily report fact. Grain: one row per fund class (or subclass) per day
-- (cnpj_fundo_classe, id_subclasse, sk_data), the grain of stg_cvm__informe_diario (ADR 006).
-- Design: docs/dimensional-model.md.
--
-- Incremental (ADR 003): delete+insert by reference month. A run reprocesses every month whose
-- load (_loaded_at) differs from the one already in the fact, or that is not in it yet, and
-- replaces those months as a whole. CVM republishes the current month (and corrections of
-- earlier ones), so a reloaded month is rebuilt, rows that disappeared from it are removed, and
-- unchanged months are left alone. `dbt build --full-refresh` rebuilds everything.

{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='dt_mes_competencia',
        on_schema_change='fail'
    )
}}

with informe as (

    select * from {{ ref('stg_cvm__informe_diario') }}

    {% if is_incremental() %}
    -- Months loaded (or reloaded) since the last run of this model.
    where dt_mes_competencia in (
        select s.dt_mes_competencia
        from (
            select dt_mes_competencia, max(_loaded_at) as _loaded_at
            from {{ ref('stg_cvm__informe_diario') }}
            group by dt_mes_competencia
        ) as s
        left join (
            select dt_mes_competencia, max(_loaded_at) as _loaded_at
            from {{ this }}
            group by dt_mes_competencia
        ) as t
            on t.dt_mes_competencia = s.dt_mes_competencia
        where t._loaded_at is distinct from s._loaded_at
    )
    {% endif %}

),

dim_fundo as (

    select
        sk_fundo,
        cnpj_fundo_classe,
        dt_valido_de,
        -- Open-ended current version; a plain bound keeps the join a hash join.
        coalesce(dt_valido_ate, cast('9999-12-31' as date)) as dt_valido_ate_excl
    from {{ ref('dim_fundo') }}

),

-- Facts whose CNPJ (or date) matches no dim_fundo version point to the unknown member.
desconhecido as (

    select sk_fundo
    from {{ ref('dim_fundo') }}
    where tp_registro = 'DESCONHECIDO'

)

select
    -- The dim_fundo version valid on the report date: [dt_valido_de, dt_valido_ate).
    coalesce(f.sk_fundo, u.sk_fundo)                    as sk_fundo,
    i.dt_competencia                                    as sk_data,
    i.cnpj_fundo_classe,
    i.id_subclasse,
    i.vl_total,
    i.vl_quota,
    i.vl_patrim_liq,
    i.vl_captc_dia,
    i.vl_resg_dia,
    -- RN-01: net inflows = inflows - redemptions (a missing side counts as zero).
    coalesce(i.vl_captc_dia, 0) - coalesce(i.vl_resg_dia, 0) as vl_captc_liquida_dia,
    i.nr_cotst,
    i.dt_mes_competencia,
    i._loaded_at
from informe as i
left join dim_fundo as f
    on f.cnpj_fundo_classe = i.cnpj_fundo_classe
    and i.dt_competencia >= f.dt_valido_de
    and i.dt_competencia < f.dt_valido_ate_excl
cross join desconhecido as u
