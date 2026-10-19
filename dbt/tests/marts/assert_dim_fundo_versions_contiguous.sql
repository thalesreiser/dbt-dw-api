-- RF-04 (3.4): the versions of each CNPJ in dim_fundo cover [1900-01-01, open end) without
-- overlaps or gaps: the first starts at 1900-01-01, each one starts where the previous one ends
-- (half-open intervals) and only the last one is open. Returns the offending versions.

with versoes as (

    select
        cnpj_fundo_classe,
        dt_valido_de,
        dt_valido_ate,
        lag(dt_valido_ate) over (
            partition by cnpj_fundo_classe order by dt_valido_de
        ) as dt_valido_ate_anterior,
        row_number() over (
            partition by cnpj_fundo_classe order by dt_valido_de
        ) as nr_versao,
        count(*) over (partition by cnpj_fundo_classe) as nr_versoes
    from {{ ref('dim_fundo') }}

)

select *
from versoes
where (nr_versao = 1 and dt_valido_de <> cast('1900-01-01' as date))
   or (nr_versao > 1 and dt_valido_ate_anterior is distinct from dt_valido_de)
   or ((nr_versao = nr_versoes) <> (dt_valido_ate is null))
