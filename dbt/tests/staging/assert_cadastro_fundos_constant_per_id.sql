-- RF-02 / ADR 006: stg_cvm__cadastro_fundos keeps one row per ID_Registro_Fundo and only has to
-- choose among the manager (gestor) columns. This holds only if every fund-level attribute is
-- identical across the source rows of the same id; returns the ids where it is not.

select ID_Registro_Fundo
from {{ source('cvm', 'cadastro_fundos') }}
group by ID_Registro_Fundo
having count(distinct (
    CNPJ_Fundo, Codigo_CVM, Data_Registro, Data_Constituicao, Tipo_Fundo, Denominacao_Social,
    Data_Cancelamento, Situacao, Data_Inicio_Situacao, Data_Adaptacao_RCVM175,
    Data_Inicio_Exercicio_Social, Data_Fim_Exercicio_Social, Patrimonio_Liquido,
    Data_Patrimonio_Liquido, Diretor, CNPJ_Administrador, Administrador
)) > 1
