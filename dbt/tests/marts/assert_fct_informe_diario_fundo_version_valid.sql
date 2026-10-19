-- RF-03 (3.3): sk_fundo of each daily row is the dim_fundo version of the same CNPJ that is
-- valid on the report date ([dt_valido_de, dt_valido_ate)), or the unknown member only when no
-- such version exists. Holds unchanged when dim_fundo keeps several versions per CNPJ (3.4).

with fato as (

    select f.cnpj_fundo_classe, f.sk_data, f.sk_fundo, d.cnpj_fundo_classe as cnpj_dim,
           d.tp_registro, d.dt_valido_de, d.dt_valido_ate
    from {{ ref('fct_informe_diario') }} as f
    inner join {{ ref('dim_fundo') }} as d
        on d.sk_fundo = f.sk_fundo

)

select *
from fato
where (
        tp_registro <> 'DESCONHECIDO'
        and (
            cnpj_dim <> cnpj_fundo_classe
            or sk_data < dt_valido_de
            or sk_data >= coalesce(dt_valido_ate, cast('9999-12-31' as date))
        )
    )
   or (
        tp_registro = 'DESCONHECIDO'
        and exists (
            select 1 from {{ ref('dim_fundo') }} as v
            where v.cnpj_fundo_classe = fato.cnpj_fundo_classe
              and fato.sk_data >= v.dt_valido_de
              and (v.dt_valido_ate is null or fato.sk_data < v.dt_valido_ate)
        )
    )
