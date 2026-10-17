-- RF-02: fund class registry after CVM Resolution 175 (registro_classe.csv), renamed, typed and
-- standardized. Grain: one row per class registry id (id_registro_classe).
--
-- A handful of ids appear twice in the source: one exact duplicate and a few rows that differ
-- only in the custodian or the controller (guarded by the singular test
-- assert_cadastro_classes_constant_per_id). One row is kept deterministically: the lowest
-- custodian CNPJ, then the lowest controller CNPJ (nulls last).
-- Decision: docs/adr/006-staging-grain-and-deduplication.md.

with source as (

    select * from {{ source('cvm', 'cadastro_classes') }}

),

renamed as (

    select
        {{ clean_text('ID_Registro_Classe') }}                          as id_registro_classe,
        {{ clean_text('ID_Registro_Fundo') }}                           as id_registro_fundo,
        {{ clean_cnpj('CNPJ_Classe') }}                                 as cnpj_classe,
        {{ clean_text('Codigo_CVM') }}                                  as cd_cvm,
        {{ clean_name('Denominacao_Social') }}                          as nm_denominacao_social,
        {{ clean_code('Tipo_Classe') }}                                 as tp_classe,
        {{ clean_code('Situacao') }}                                    as sit_classe,
        {{ to_date('Data_Registro') }}                                  as dt_registro,
        {{ to_date('Data_Constituicao') }}                              as dt_constituicao,
        {{ to_date('Data_Inicio') }}                                    as dt_inicio,
        {{ to_date('Data_Inicio_Situacao') }}                           as dt_inicio_situacao,
        {{ clean_code('Classificacao') }}                               as tp_classificacao,
        {{ clean_code('Classificacao_Anbima') }}                        as tp_classificacao_anbima,
        {{ clean_name('Indicador_Desempenho') }}                        as nm_indicador_desempenho,
        {{ clean_code('Forma_Condominio') }}                            as tp_condominio,
        {{ clean_code('Publico_Alvo') }}                                as tp_publico_alvo,
        {{ to_flag('Classe_Cotas') }}                                   as fl_classe_cotas,
        {{ to_flag('Exclusivo') }}                                      as fl_exclusivo,
        {{ to_flag('Tributacao_Longo_Prazo') }}                         as fl_tributacao_longo_prazo,
        {{ to_flag('Entidade_Investimento') }}                          as fl_entidade_investimento,
        {{ to_flag('Permitido_Aplicacao_CemPorCento_Exterior') }}       as fl_aplicacao_100_exterior,
        {{ to_flag('Classe_ESG') }}                                     as fl_classe_esg,
        {{ to_decimal('Patrimonio_Liquido') }}                          as vl_patrim_liq,
        {{ to_date('Data_Patrimonio_Liquido') }}                        as dt_patrim_liq,
        {{ clean_cpf_cnpj('CNPJ_Auditor') }}                            as cpf_cnpj_auditor,
        {{ clean_name('Auditor') }}                                     as nm_auditor,
        {{ clean_cnpj('CNPJ_Custodiante') }}                            as cnpj_custodiante,
        {{ clean_name('Custodiante') }}                                 as nm_custodiante,
        {{ clean_cnpj('CNPJ_Controlador') }}                            as cnpj_controlador,
        {{ clean_name('Controlador') }}                                 as nm_controlador,
        _source,
        _source_file,
        _loaded_at
    from source

)

select * from renamed
qualify row_number() over (
    partition by id_registro_classe
    order by cnpj_custodiante asc nulls last, cnpj_controlador asc nulls last,
        nm_custodiante asc nulls last, nm_controlador asc nulls last
) = 1
