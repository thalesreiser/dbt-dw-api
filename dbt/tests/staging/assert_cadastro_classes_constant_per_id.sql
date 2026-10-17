-- RF-02 / ADR 006: stg_cvm__cadastro_classes keeps one row per ID_Registro_Classe. Repeated ids
-- were observed to differ only in the custodian and controller columns; returns the ids whose
-- other attributes differ, which would make the deterministic pick lose class-level data.

select ID_Registro_Classe
from {{ source('cvm', 'cadastro_classes') }}
group by ID_Registro_Classe
having count(distinct (
    ID_Registro_Fundo, CNPJ_Classe, Codigo_CVM, Data_Registro, Data_Constituicao, Data_Inicio,
    Tipo_Classe, Denominacao_Social, Situacao, Data_Inicio_Situacao, Classificacao,
    Indicador_Desempenho, Classe_Cotas, Classificacao_Anbima, Tributacao_Longo_Prazo,
    Entidade_Investimento, Permitido_Aplicacao_CemPorCento_Exterior, Classe_ESG,
    Forma_Condominio, Exclusivo, Publico_Alvo, Patrimonio_Liquido, Data_Patrimonio_Liquido,
    CNPJ_Auditor, Auditor
)) > 1
