-- RF-03 (3.2): fund/class dimension. Grain: one row per reporting CNPJ (cnpj_fundo_classe) and
-- version (SCD2), plus the unknown member. Design: docs/dimensional-model.md.
--
-- RF-04 (3.4): SCD type 2, built from the snapshot snp_cvm__fundo_classe.
-- * dt_valido_de = date of dbt_valid_from, except the first version of each CNPJ, which starts
--   at 1900-01-01 (no registry history before the first snapshot), so facts older than the
--   first snapshot still resolve and sk_fundo of the first version is the one of task 3.2.
-- * dt_valido_ate = date of dbt_valid_to (exclusive), null for the current version. Validity
--   is the half-open interval [dt_valido_de, dt_valido_ate).
-- * Several versions opened on the same day collapse into the last one of that day, so
--   (cnpj_fundo_classe, dt_valido_de) and sk_fundo stay unique.
--
-- fl_informa_recente: the CNPJ has at least one daily report in the latest reference month
-- loaded. Computed from stg_cvm__informe_diario (the same rows fct_informe_diario holds), since
-- the fact depends on this dimension; same value on every version of a CNPJ, false for the
-- unknown member.

with registro_snapshot as (

    select * from {{ ref('snp_cvm__fundo_classe') }}

),

-- Last version of each CNPJ per day; its dbt_valid_to is the start of the next kept version.
versoes_do_dia as (

    select *
    from registro_snapshot
    qualify row_number() over (
        partition by cnpj_fundo_classe, cast(dbt_valid_from as date)
        order by dbt_valid_from desc
    ) = 1

),

versoes as (

    select
        * exclude (dbt_scd_id, dbt_updated_at, dbt_valid_from, dbt_valid_to),
        case
            when row_number() over (
                partition by cnpj_fundo_classe order by dbt_valid_from
            ) = 1 then cast('1900-01-01' as date)
            else cast(dbt_valid_from as date)
        end                                 as dt_valido_de,
        cast(dbt_valid_to as date)          as dt_valido_ate,
        dbt_valid_to is null                as fl_versao_atual
    from versoes_do_dia

),

-- Facts whose CNPJ does not resolve point here, so they never have orphan keys.
desconhecido as (

    select
        '00000000000000'                    as cnpj_fundo_classe,
        'DESCONHECIDO'                      as tp_registro,
        cast(null as varchar)               as id_registro_classe,
        cast(null as varchar)               as id_registro_fundo,
        cast(null as varchar)               as cnpj_fundo,
        'DESCONHECIDO'                      as nm_denominacao_social,
        'DESCONHECIDO'                      as nm_denominacao_social_fundo,
        cast(null as varchar)               as tp_fundo,
        cast(null as varchar)               as tp_classe,
        'DESCONHECIDO'                      as sit_fundo_classe,
        cast(null as varchar)               as sit_fundo,
        cast(null as varchar)               as tp_classificacao,
        cast(null as varchar)               as tp_classificacao_anbima,
        cast(null as varchar)               as tp_condominio,
        cast(null as varchar)               as tp_publico_alvo,
        cast(null as boolean)               as fl_exclusivo,
        cast(null as varchar)               as cnpj_administrador,
        cast(null as varchar)               as nm_administrador,
        cast(null as varchar)               as cpf_cnpj_gestor,
        cast(null as varchar)               as nm_gestor,
        cast(null as date)                  as dt_registro,
        cast('1900-01-01' as date)          as dt_valido_de,
        cast(null as date)                  as dt_valido_ate,
        true                                as fl_versao_atual

),

mes_recente as (

    select max(dt_mes_competencia) as dt_mes_competencia
    from {{ ref('stg_cvm__informe_diario') }}

),

cnpjs_recentes as (

    select distinct i.cnpj_fundo_classe
    from {{ ref('stg_cvm__informe_diario') }} as i
    inner join mes_recente as m
        on i.dt_mes_competencia = m.dt_mes_competencia
    where i.cnpj_fundo_classe is not null

),

unioned as (

    select * from versoes
    union all by name
    select * from desconhecido

)

select
    {{ dbt_utils.generate_surrogate_key(['u.cnpj_fundo_classe', 'u.dt_valido_de']) }} as sk_fundo,
    u.cnpj_fundo_classe,
    tp_registro,
    id_registro_classe,
    id_registro_fundo,
    cnpj_fundo,
    nm_denominacao_social,
    nm_denominacao_social_fundo,
    tp_fundo,
    tp_classe,
    sit_fundo_classe,
    sit_fundo,
    tp_classificacao,
    tp_classificacao_anbima,
    tp_condominio,
    tp_publico_alvo,
    fl_exclusivo,
    cnpj_administrador,
    nm_administrador,
    cpf_cnpj_gestor,
    nm_gestor,
    dt_registro,
    u.tp_registro <> 'DESCONHECIDO'
        and r.cnpj_fundo_classe is not null as fl_informa_recente,
    dt_valido_de,
    dt_valido_ate,
    fl_versao_atual
from unioned as u
left join cnpjs_recentes as r
    on u.cnpj_fundo_classe = r.cnpj_fundo_classe
