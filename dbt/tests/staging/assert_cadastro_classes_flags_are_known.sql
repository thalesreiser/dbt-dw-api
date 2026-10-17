-- RF-05 (2.3): the fl_ columns of stg_cvm__cadastro_classes are built by to_flag, which maps
-- S/N to true/false and anything else to null. Returns the raw flag values outside S, N, N/A
-- and blank, which to_flag would otherwise turn into null silently.

with flags as (

    select 'Classe_Cotas' as flag, Classe_Cotas as value from {{ source('cvm', 'cadastro_classes') }}
    union all
    select 'Exclusivo', Exclusivo from {{ source('cvm', 'cadastro_classes') }}
    union all
    select 'Tributacao_Longo_Prazo', Tributacao_Longo_Prazo from {{ source('cvm', 'cadastro_classes') }}
    union all
    select 'Entidade_Investimento', Entidade_Investimento from {{ source('cvm', 'cadastro_classes') }}
    union all
    select 'Permitido_Aplicacao_CemPorCento_Exterior', Permitido_Aplicacao_CemPorCento_Exterior
    from {{ source('cvm', 'cadastro_classes') }}
    union all
    select 'Classe_ESG', Classe_ESG from {{ source('cvm', 'cadastro_classes') }}

)

select flag, value, count(*) as row_count
from flags
where coalesce(upper(trim(value)), '') not in ('S', 'N', 'N/A', '')
group by flag, value
