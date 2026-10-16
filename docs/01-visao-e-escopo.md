# 01 - Visão e escopo

**Problema:** transformar dados brutos em um modelo analítico confiável, testado e consumível por aplicações.

**Objetivo:** modelar um data warehouse dimensional com dbt sobre os dados de fundos, com testes de qualidade e documentação, e disponibilizá-lo por uma API REST.

**Fonte de dados:** gold ou silver do P1 (`aws-fundos-pipeline`); se o P1 não estiver pronto, script de carga direta dos dados abertos da CVM.

| Dentro do escopo | Fora do escopo |
|---|---|
| Modelagem dimensional, testes dbt, snapshots, documentação, API read-only, testes de contrato, container | Front-end, autenticação de usuários final, deploy em produção |

## Métricas de sucesso (meta)
- `dbt build` sem falhas
- 100% dos modelos de mart documentados e testados
- p95 < 300 ms nos endpoints de série temporal em carga local
- OpenAPI publicada

## Stakeholders (papéis simulados)
| Papel | Interesse principal |
|---|---|
| Recrutador técnico / gestor | Evidência clara de stack, qualidade e autonomia, em 5 minutos de leitura |
| Engenheiro(a) revisor(a) | Código testado, organizado, reprodutível, com decisões justificadas |
| Analista consumidor(a) | Dados confiáveis, documentados e fáceis de consultar |
| Thales (dev e operador) | Custo baixo, execução reprodutível, manutenção simples |
