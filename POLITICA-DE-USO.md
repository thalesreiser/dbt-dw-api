# Política de uso: dbt-dw-api

**Autor:** Thales Reiser Pedreira · [GitHub](https://github.com/thalesreiser) · [LinkedIn](https://www.linkedin.com/in/thalesreiserpedreira)

## Licença do código

O código está sob a [licença MIT](LICENSE). Em resumo:

| ✅ Você pode | 📌 Desde que | ⚠️ Saiba que |
|---|---|---|
| Usar, copiar, modificar e distribuir o código | Mantenha o aviso `Copyright (c) 2026 Thales Reiser Pedreira` e o texto da licença em qualquer cópia ou trecho substancial | O software é fornecido sem garantia de qualquer tipo |
| Usar em projetos pessoais ou comerciais | Dê crédito ao autor | O autor não responde por danos nem por custos decorrentes do uso |

O texto do [`LICENSE`](LICENSE) é o que tem valor jurídico; esta página é só um resumo.

## Finalidade do projeto

Este é um projeto de portfólio, criado para demonstrar competências de engenharia de dados com um processo de engenharia de requisitos documentado. Ele não é um produto e não foi pensado para uso em produção.

## Dados

A licença MIT vale para o **código**, não para os dados que ele processa.

- O repositório **não contém dados brutos**. Os dados são baixados das fontes públicas oficiais em tempo de execução, e apenas pequenas amostras para testes são versionadas.
- Os dados pertencem às respectivas fontes e seguem os termos de uso delas.
- Quem executa o projeto é responsável por usar os dados de acordo com a **LGPD (Lei nº 13.709/2018)** e com os termos das fontes.
- **Dados de fundos (CVM):** informe diário e cadastro de fundos de investimento, dados públicos sobre pessoas jurídicas. Os resultados não são recomendação de investimento.

## Uso da API

- A API é **somente leitura** e foi feita para rodar localmente. Ela **não** deve ser exposta na internet sem uma revisão de segurança.
- O acesso exige uma API key definida no seu `.env`. Nunca publique essa chave.
- Respeite o limite de requisições configurado. Testes de carga devem ser feitos apenas contra a sua própria instância local.

## Segurança

- Nenhum segredo, chave ou credencial deve ser versionado. Crie o seu `.env` (ignorado pelo Git) a partir do `.env.example`.
- O pre-commit roda o **gitleaks** para detectar segredos antes de cada commit.
- Se encontrar uma vulnerabilidade, **não abra issue pública**: fale direto com o autor pelo GitHub ou pelo LinkedIn.

## Contribuições

Issues e sugestões são bem-vindas. Contribuições enviadas a este repositório ficam sob a mesma licença MIT.
