# Usage policy: dbt-dw-api

**Author:** Thales Reiser Pedreira · [GitHub](https://github.com/thalesreiser) · [LinkedIn](https://www.linkedin.com/in/thalesreiserpedreira)

## Code license

The code is released under the [MIT license](LICENSE). In short:

| ✅ You may | 📌 As long as | ⚠️ Keep in mind |
|---|---|---|
| Use, copy, modify and distribute the code | You keep the `Copyright (c) 2026 Thales Reiser Pedreira` notice and the license text in every copy or substantial portion | The software is provided without warranty of any kind |
| Use it in personal or commercial projects | You give credit to the author | The author is not liable for damages or costs arising from its use |

The [`LICENSE`](LICENSE) text is the legally binding one; this page is only a summary.

## Purpose of the project

This is a portfolio project, built to demonstrate data engineering skills through a documented requirements engineering process. It is not a product and was not designed for production use.

## Data

The MIT license applies to the **code**, not to the data it processes.

- The repository **contains no raw data**. Data is downloaded from the official public sources at run time, and only small samples for tests are versioned.
- The data belongs to its sources and follows their terms of use.
- Whoever runs the project is responsible for using the data in accordance with Brazil's data protection law (**LGPD, Law 13,709/2018**) and the terms of the sources.
- **Fund data (CVM):** daily reports and the registry of investment funds, public data about legal entities. The results are not investment advice.
- **Attribution:** Source: Comissão de Valores Mobiliários (CVM) — Portal Dados Abertos (dados.cvm.gov.br), licensed under the Open Database License (ODbL). This repository does not redistribute CVM data (it contains only code, a national holiday calendar seed and synthetic test fixtures). Results derived from it remain subject to the ODbL attribution and share-alike terms if published as a database. The MIT license covers the code only.

## API usage

- The API is **read-only** and designed to run locally. It must **not** be exposed to the internet without a security review.
- Access requires an API key defined in your `.env`. Never publish that key.
- Respect the configured rate limit. Load tests must only target your own local instance.

## Security

- No secret, key or credential may be committed. Create your own `.env` (ignored by Git) from `.env.example`.
- The pre-commit hooks run **gitleaks** to detect secrets before every commit.
- If you find a vulnerability, **do not open a public issue**: report it privately through GitHub private vulnerability reporting, as described in [`SECURITY.md`](SECURITY.md).

## Contributions

Issues and suggestions are welcome. Contributions submitted to this repository are licensed under the same MIT license.
