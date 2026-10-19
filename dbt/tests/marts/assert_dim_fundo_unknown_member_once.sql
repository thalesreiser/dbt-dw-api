-- RF-03 (3.2): dim_fundo has exactly one unknown member, current, with the documented key.
-- Returns a row (fails) unless there is exactly one such member and no other DESCONHECIDO row.

with membros as (

    select
        count(*) filter (
            where tp_registro = 'DESCONHECIDO'
        ) as nr_desconhecido,
        count(*) filter (
            where tp_registro = 'DESCONHECIDO'
              and cnpj_fundo_classe = '00000000000000'
              and fl_versao_atual
              and sk_fundo = {{ dbt_utils.generate_surrogate_key(["'00000000000000'", "cast('1900-01-01' as date)"]) }}
        ) as nr_membro_valido
    from {{ ref('dim_fundo') }}

)

select *
from membros
where nr_desconhecido <> 1 or nr_membro_valido <> 1
