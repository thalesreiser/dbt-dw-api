-- RF-02 / ADR 005: every CNPJ in the daily report must resolve to the registry, either as a
-- class CNPJ or (funds not adapted to Resolution 175) as a fund CNPJ. 100% matched for 2026-09.
-- Warn only: the registry is today's snapshot, not an as-of copy for older reference months.
{{ config(severity='warn') }}

select distinct i.cnpj_fundo_classe
from {{ ref('stg_cvm__informe_diario') }} as i
where not exists (
        select 1 from {{ ref('stg_cvm__cadastro_classes') }} as c
        where c.cnpj_classe = i.cnpj_fundo_classe
    )
  and not exists (
        select 1 from {{ ref('stg_cvm__cadastro_fundos') }} as f
        where f.cnpj_fundo = i.cnpj_fundo_classe
    )
