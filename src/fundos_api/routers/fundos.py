"""`GET /v1/fundos`: current funds/classes with filters and pagination (RF-07).

Reads the current version of `dim_fundo` (`fl_versao_atual`) and never the unknown member.
Ordering is deterministic (`cnpj_fundo_classe`) and every filter is a bound parameter.
Registry status is shown as published by CVM: a cancelled fund that still reports is listed
with `sit_fundo_classe = 'CANCELADO'`; `fl_informa_recente` (filter `informa_recente`) tells
whether the CNPJ has a daily report in the latest month loaded.
"""

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError

from fundos_api.db import get_connection, get_settings_from_app
from fundos_api.params import PageParams, pagination
from fundos_api.schemas import FundoResumo, Page

router = APIRouter(tags=["fundos"])

# Registry statuses published by CVM (`sit_fundo_classe`), without the unknown member.
SITUACOES = frozenset(
    {
        "CANCELADO",
        "EM ANALISE",
        "EM FUNCIONAMENTO NORMAL",
        "EM LIQUIDACAO",
        "EM SITUACAO ESPECIAL",
        "FASE PRE-OPERACIONAL",
        "INCORPORACAO",
    }
)
TEXT_FILTER_PATTERN = r"^[A-Za-z0-9 ()\-]+$"

_COLUMNS = ", ".join(FundoResumo.model_fields)


def _situacao(
    situacao: Annotated[
        str | None,
        Query(
            max_length=40,
            # Declared as an enum so the OpenAPI contract matches what is accepted (RF-11);
            # lower case and surrounding spaces are tolerated as well.
            json_schema_extra={"enum": sorted(SITUACOES)},
            description="Registry status (`sit_fundo_classe`), case-insensitive: "
            + ", ".join(sorted(SITUACOES))
            + ".",
        ),
    ] = None,
) -> str | None:
    if situacao is None:
        return None
    value = situacao.strip().upper()
    if value not in SITUACOES:
        raise RequestValidationError(
            [
                {
                    "type": "enum",
                    "loc": ("query", "situacao"),
                    "msg": "Input should be one of: " + ", ".join(sorted(SITUACOES)),
                    "input": situacao,
                    "ctx": {"expected": sorted(SITUACOES)},
                }
            ]
        )
    return value


@router.get("/fundos", response_model=Page[FundoResumo])
def list_fundos(
    request: Request,
    con: Annotated[duckdb.DuckDBPyConnection, Depends(get_connection)],
    page: Annotated[PageParams, Depends(pagination)],
    situacao: Annotated[str | None, Depends(_situacao)],
    tp_fundo: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=20,
            pattern=TEXT_FILTER_PATTERN,
            description="Fund type, exact and case-insensitive (e.g. `FIF`, `FIDC`, `FI`).",
        ),
    ] = None,
    tp_classe: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=60,
            pattern=TEXT_FILTER_PATTERN,
            description="Class type, exact and case-insensitive "
            "(e.g. `CLASSES DE COTAS DE FUNDOS FIF`); fund-only rows have none.",
        ),
    ] = None,
    nome: Annotated[
        str | None,
        Query(
            min_length=3,
            max_length=100,
            description="Substring of the legal name (`nm_denominacao_social`), "
            "case-insensitive.",
        ),
    ] = None,
    informa_recente: Annotated[
        bool | None,
        Query(
            description="Filter by `fl_informa_recente`: the CNPJ has a daily report in the "
            "latest month loaded (e.g. `situacao=CANCELADO&informa_recente=true`).",
        ),
    ] = None,
) -> Page[FundoResumo]:
    """Current funds/classes, filtered and paginated with `limit`/`offset`, by CNPJ."""
    schema = get_settings_from_app(request).marts_schema
    where = ["fl_versao_atual", "tp_registro <> 'DESCONHECIDO'"]
    params: list[object] = []
    if situacao is not None:
        where.append("sit_fundo_classe = ?")
        params.append(situacao)
    if tp_fundo is not None:
        where.append("upper(tp_fundo) = upper(?)")
        params.append(tp_fundo)
    if tp_classe is not None:
        where.append("upper(tp_classe) = upper(?)")
        params.append(tp_classe)
    if nome is not None:
        where.append("contains(lower(nm_denominacao_social), lower(?))")
        params.append(nome)
    if informa_recente is not None:
        where.append("fl_informa_recente = ?")
        params.append(informa_recente)
    base = f"from {schema}.dim_fundo where " + " and ".join(where)

    count_row = con.execute(f"select count(*) {base}", params).fetchone()
    total = int(count_row[0]) if count_row else 0
    cursor = con.execute(
        f"select {_COLUMNS} {base} order by cnpj_fundo_classe limit ? offset ?",
        [*params, page.limit, page.offset],
    )
    columns = [d[0] for d in cursor.description]
    items = [
        FundoResumo.model_validate(dict(zip(columns, row, strict=True)))
        for row in cursor.fetchall()
    ]
    return Page[FundoResumo](items=items, limit=page.limit, offset=page.offset, total=total)
