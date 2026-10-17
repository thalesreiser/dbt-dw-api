-- RF-02: fund registry after CVM Resolution 175 (registro_fundo.csv), renamed, typed and
-- standardized. Grain: one row per fund registry id (id_registro_fundo).
--
-- The source has one row per fund AND manager (gestor), plus a few exact duplicates. Every
-- fund-level attribute is identical across those rows (guarded by the singular test
-- assert_cadastro_fundos_constant_per_id), so the dedup only has to pick the manager columns:
-- the first manager by CPF/CNPJ (nulls last), then by name, is kept, and nr_gestor counts the
-- distinct managers of the fund. Decision: docs/adr/006-staging-grain-and-deduplication.md.

with source as (

    select * from {{ source('cvm', 'cadastro_fundos') }}

),

renamed as (

    select
        {{ clean_text('ID_Registro_Fundo') }}               as id_registro_fundo,
        {{ clean_cnpj('CNPJ_Fundo') }}                      as cnpj_fundo,
        {{ clean_text('Codigo_CVM') }}                      as cd_cvm,
        {{ clean_name('Denominacao_Social') }}              as nm_denominacao_social,
        {{ clean_code('Tipo_Fundo') }}                      as tp_fundo,
        {{ clean_code('Situacao') }}                        as sit_fundo,
        {{ to_date('Data_Registro') }}                      as dt_registro,
        {{ to_date('Data_Constituicao') }}                  as dt_constituicao,
        {{ to_date('Data_Cancelamento') }}                  as dt_cancelamento,
        {{ to_date('Data_Inicio_Situacao') }}               as dt_inicio_situacao,
        {{ to_date('Data_Adaptacao_RCVM175') }}             as dt_adaptacao_rcvm175,
        {{ to_date('Data_Inicio_Exercicio_Social') }}       as dt_inicio_exercicio_social,
        {{ to_date('Data_Fim_Exercicio_Social') }}          as dt_fim_exercicio_social,
        {{ to_decimal('Patrimonio_Liquido') }}              as vl_patrim_liq,
        {{ to_date('Data_Patrimonio_Liquido') }}            as dt_patrim_liq,
        {{ clean_name('Diretor') }}                         as nm_diretor,
        {{ clean_cnpj('CNPJ_Administrador') }}              as cnpj_administrador,
        {{ clean_name('Administrador') }}                   as nm_administrador,
        {{ clean_code('Tipo_Pessoa_Gestor') }}              as tp_pessoa_gestor,
        {{ clean_cpf_cnpj('CPF_CNPJ_Gestor') }}             as cpf_cnpj_gestor,
        {{ clean_name('Gestor') }}                          as nm_gestor,
        -- distinct managers of the fund (0 when the registry lists none)
        cast(count(distinct {{ clean_cpf_cnpj('CPF_CNPJ_Gestor') }})
            over (partition by ID_Registro_Fundo) as integer) as nr_gestor,
        _source,
        _source_file,
        _loaded_at
    from source

)

select * from renamed
qualify row_number() over (
    partition by id_registro_fundo
    order by cpf_cnpj_gestor asc nulls last, nm_gestor asc nulls last, tp_pessoa_gestor asc nulls last
) = 1
