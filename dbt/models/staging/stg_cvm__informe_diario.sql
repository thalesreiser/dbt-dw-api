-- RF-02: daily report of funds and classes, renamed, typed and standardized.
-- Grain: one row per class/subclass per day (cnpj_fundo_classe, id_subclasse, dt_competencia);
-- id_subclasse is null when the report is at class (or fund) level.

with source as (

    select * from {{ source('cvm', 'informe_diario') }}

)

select
    {{ clean_cnpj('CNPJ_FUNDO_CLASSE') }}             as cnpj_fundo_classe,
    {{ clean_text('ID_SUBCLASSE') }}                  as id_subclasse,
    {{ to_date('DT_COMPTC') }}                        as dt_competencia,
    {{ clean_code('TP_FUNDO_CLASSE') }}               as tp_fundo_classe,
    {{ to_decimal('VL_TOTAL') }}                      as vl_total,
    {{ to_decimal('VL_QUOTA', 27, 12) }}              as vl_quota,
    {{ to_decimal('VL_PATRIM_LIQ') }}                 as vl_patrim_liq,
    {{ to_decimal('CAPTC_DIA') }}                     as vl_captc_dia,
    {{ to_decimal('RESG_DIA') }}                      as vl_resg_dia,
    {{ to_integer('NR_COTST') }}                      as nr_cotst,
    cast(competencia || '-01' as date)                as dt_mes_competencia,
    _source,
    _source_file,
    _loaded_at

from source
