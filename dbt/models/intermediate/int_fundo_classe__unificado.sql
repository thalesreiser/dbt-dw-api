-- RF-03 (3.2): fund and class registries unified at the grain of the daily report key.
-- Grain: one row per reporting CNPJ (cnpj_fundo_classe). Design: docs/dimensional-model.md.
--
-- * CLASSE rows: one per class CNPJ, with the attributes of the class and of its parent fund.
-- * FUNDO rows: one per fund CNPJ that is not a class CNPJ and whose CNPJ has no class in the
--   registry (funds not adapted to Resolution 175); class columns are null. The CNPJ of a
--   multi-class fund is not a row of its own: it is reached through cnpj_fundo on its classes.
-- * One registry entry per CNPJ: when a CNPJ has several registry ids, keep the non-cancelled
--   one, then the latest dt_registro, then the highest registry id.
-- Registry status is kept as-is: a CANCELADO fund that still reports keeps its status.
-- RF-04 (3.4): a view (not ephemeral) because the snapshot snp_cvm__fundo_classe selects from it.

{{ config(materialized='view', schema='intermediate') }}

with classes as (

    select * from {{ ref('stg_cvm__cadastro_classes') }}

),

fundos as (

    select * from {{ ref('stg_cvm__cadastro_fundos') }}

),

classe_rows as (

    select
        c.cnpj_classe                       as cnpj_fundo_classe,
        'CLASSE'                            as tp_registro,
        c.id_registro_classe,
        c.id_registro_fundo,
        f.cnpj_fundo,
        c.nm_denominacao_social,
        f.nm_denominacao_social             as nm_denominacao_social_fundo,
        f.tp_fundo,
        c.tp_classe,
        c.sit_classe                        as sit_fundo_classe,
        f.sit_fundo,
        c.tp_classificacao,
        c.tp_classificacao_anbima,
        c.tp_condominio,
        c.tp_publico_alvo,
        c.fl_exclusivo,
        f.cnpj_administrador,
        f.nm_administrador,
        f.cpf_cnpj_gestor,
        f.nm_gestor,
        c.dt_registro
    from classes as c
    inner join fundos as f
        on f.id_registro_fundo = c.id_registro_fundo
    qualify row_number() over (
        partition by c.cnpj_classe
        order by (c.sit_classe = 'CANCELADO') asc, c.dt_registro desc nulls last,
            try_cast(c.id_registro_classe as bigint) desc nulls last, c.id_registro_classe desc
    ) = 1

),

-- CNPJs already covered by a class: class CNPJs and the CNPJs of funds that have classes.
cnpjs_com_classe as (

    select cnpj_classe as cnpj from classes
    union
    select f.cnpj_fundo
    from fundos as f
    inner join classes as c
        on c.id_registro_fundo = f.id_registro_fundo

),

fundo_rows as (

    select
        f.cnpj_fundo                        as cnpj_fundo_classe,
        'FUNDO'                             as tp_registro,
        cast(null as varchar)               as id_registro_classe,
        f.id_registro_fundo,
        f.cnpj_fundo,
        f.nm_denominacao_social,
        f.nm_denominacao_social             as nm_denominacao_social_fundo,
        f.tp_fundo,
        cast(null as varchar)               as tp_classe,
        f.sit_fundo                         as sit_fundo_classe,
        f.sit_fundo,
        cast(null as varchar)               as tp_classificacao,
        cast(null as varchar)               as tp_classificacao_anbima,
        cast(null as varchar)               as tp_condominio,
        cast(null as varchar)               as tp_publico_alvo,
        cast(null as boolean)               as fl_exclusivo,
        f.cnpj_administrador,
        f.nm_administrador,
        f.cpf_cnpj_gestor,
        f.nm_gestor,
        f.dt_registro
    from fundos as f
    where not exists (select 1 from cnpjs_com_classe as x where x.cnpj = f.cnpj_fundo)
    qualify row_number() over (
        partition by f.cnpj_fundo
        order by (f.sit_fundo = 'CANCELADO') asc, f.dt_registro desc nulls last,
            try_cast(f.id_registro_fundo as bigint) desc nulls last, f.id_registro_fundo desc
    ) = 1

)

select * from classe_rows
union all
select * from fundo_rows
