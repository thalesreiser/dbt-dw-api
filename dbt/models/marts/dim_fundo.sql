-- RF-03 (3.2): fund/class dimension. Grain: one row per reporting CNPJ (cnpj_fundo_classe) and
-- version, plus the unknown member. Design: docs/dimensional-model.md.
--
-- Until the SCD2 snapshot of task 3.4 there is a single (current) version per CNPJ. It already
-- follows the history rules of the design: the first version starts at 1900-01-01, so sk_fundo
-- = hash(cnpj_fundo_classe, dt_valido_de) stays the same when the snapshot takes over.

with unificado as (

    select * from {{ ref('int_fundo_classe__unificado') }}

),

versoes as (

    select
        *,
        cast('1900-01-01' as date)          as dt_valido_de,
        cast(null as date)                  as dt_valido_ate,
        true                                as fl_versao_atual
    from unificado

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

unioned as (

    select * from versoes
    union all by name
    select * from desconhecido

)

select
    {{ dbt_utils.generate_surrogate_key(['cnpj_fundo_classe', 'dt_valido_de']) }} as sk_fundo,
    cnpj_fundo_classe,
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
    dt_valido_de,
    dt_valido_ate,
    fl_versao_atual
from unioned
