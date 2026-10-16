# 02 - Análise e priorização (MoSCoW)

## Requisitos funcionais
| ID | Requisito | Prior. | Critério de aceite | Verificação |
|---|---|---|---|---|
| RF-01 | Carregar dados de origem (Parquet do P1, ou carga direta) no warehouse | M | Então as tabelas de origem estão disponíveis como `sources` no dbt | `dbt source freshness` e contagem |
| RF-02 | Camada staging: renomear, tipar e padronizar colunas | M | Então cada fonte tem um modelo `stg_` com colunas padronizadas | Testes dbt |
| RF-03 | Modelo dimensional: `dim_fundo`, `dim_data`, `fct_informe_diario`, `fct_captacao_mensal` | M | Então fatos referenciam dimensões sem órfãos | Teste `relationships` |
| RF-04 | Histórico de mudanças cadastrais com snapshot (SCD tipo 2) | S | Dada mudança no cadastro, então ambas as versões existem com vigência | `dbt snapshot` e consulta |
| RF-05 | Testes de qualidade: unique, not_null, accepted_values, relationships e regras de negócio | M | Então falha um teste ao inserir dado inválido proposital | `dbt test` |
| RF-06 | Documentação e linhagem geradas pelo dbt | M | Então `dbt docs generate` mostra descrição e lineage de todos os marts | Revisão |
| RF-07 | API `GET /v1/fundos` com filtros e paginação | M | Dado filtro por situação, então retorna só fundos correspondentes, paginados | pytest + httpx |
| RF-08 | API `GET /v1/fundos/{cnpj}/serie` com período | M | Então retorna a série ordenada, ou 404 se o CNPJ não existe | pytest |
| RF-09 | API `GET /v1/rankings/captacao` por mês | S | Então retorna o top N do mês | pytest |
| RF-10 | Autenticação por API key e limite de requisições | S | Sem chave, então 401; excesso, então 429 | pytest |
| RF-11 | Testes de contrato contra a especificação OpenAPI | S | Então nenhum endpoint viola o contrato | Schemathesis |

## Requisitos não funcionais, regras e restrições
| ID | Tipo | Descrição |
|---|---|---|
| RNF-01 | Desempenho | p95 < 300 ms nas consultas de série (meta) |
| RNF-02 | Confiabilidade | `dbt build` falha o CI se qualquer teste falhar |
| RNF-03 | Segurança | API somente leitura; chave fora do repositório; validação de entrada com Pydantic |
| RNF-04 | Portabilidade | Execução via Docker Compose; adaptador do warehouse trocável (DuckDB local, Athena opcional) |
| RNF-05 | Manutenibilidade | Modelos em camadas staging → intermediate → marts, convenção de nomes documentada |
| RN-01 | Regra | Captação líquida = captações − resgates no período |
| RN-02 | Regra | Valores monetários em BRL, datas em UTC-3 só na apresentação |
| RST-01 | Restrição | Sem custo recorrente: warehouse local com DuckDB |

## Riscos
| ID | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| R-01 | Escopo crescer e o projeto não terminar | Alta | Alto | MoSCoW rígido; "Could" só após todos os "Must" |
| R-03 | Falta de tempo | Alta | Alto | Entrega incremental: cada épico gera algo publicável |
| R-P3-01 | Dependência do P1 atrasar | — | — | Script de carga direta (RF-01) |
| R-P3-02 | Modelagem dimensional mal definida gerar retrabalho | — | — | Fechar granularidade e diagrama no Épico 3.1 antes de codar |
