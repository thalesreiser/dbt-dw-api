"""`GET /v1/rankings/captacao`: top N funds/classes of a month by net inflows (RF-09, RN-01)."""

from datetime import date
from typing import Annotated, Literal

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, status

from fundos_api.config import Settings
from fundos_api.db import get_connection, get_settings_from_app
from fundos_api.schemas import ErrorResponse, RankingCaptacao, RankingCaptacaoItem

router = APIRouter(tags=["rankings"])

# Years 1000-9999: `0000-01` is not a valid date (it gave a 500 before task 6.1).
MONTH_PATTERN = r"^[1-9]\d{3}-(0[1-9]|1[0-2])$"
MAX_TOP = 100

# Fixed SQL fragments chosen from a whitelist; user input never reaches the SQL text.
_ORDER_BY = {
    "desc": "f.vl_captc_liquida_mes desc, f.cnpj_fundo_classe asc",
    "asc": "f.vl_captc_liquida_mes asc, f.cnpj_fundo_classe asc",
}

_COLUMNS = [*RankingCaptacaoItem.model_fields]


def _parse_month(value: str) -> date:
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def _latest_month(con: duckdb.DuckDBPyConnection, schema: str) -> date | None:
    row = con.execute(f"select max(sk_mes) from {schema}.fct_captacao_mensal").fetchone()
    value = row[0] if row else None
    return value if isinstance(value, date) else None


@router.get(
    "/rankings/captacao",
    response_model=RankingCaptacao,
    responses={404: {"model": ErrorResponse, "description": "No data for the month"}},
)
def ranking_captacao(
    con: Annotated[duckdb.DuckDBPyConnection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    mes: Annotated[
        str | None,
        Query(
            pattern=MONTH_PATTERN,
            description="Reference month `YYYY-MM`; defaults to the latest month loaded.",
        ),
    ] = None,
    top: Annotated[int, Query(ge=1, le=MAX_TOP, description="Number of positions.")] = 10,
    ordem: Annotated[
        Literal["desc", "asc"],
        Query(description="`desc`: largest net inflows first; `asc`: largest net outflows."),
    ] = "desc",
) -> RankingCaptacao:
    """Top N funds/classes of the month by net inflows (inflows - redemptions, RN-01).

    Ties are broken by CNPJ (ascending), so the order is deterministic. The name comes from
    the current version of `dim_fundo`. A month without data gives 404.
    """
    schema = settings.marts_schema
    if mes is None:
        month = _latest_month(con, schema)
        if month is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no monthly data available")
    else:
        month = _parse_month(mes)

    select_cols = ", ".join(
        "d.nm_denominacao_social" if c == "nm_denominacao_social" else f"f.{c}"
        for c in _COLUMNS
        if c != "posicao"
    )
    sql = f"""
        select row_number() over (order by {_ORDER_BY[ordem]}) as posicao, {select_cols}
        from {schema}.fct_captacao_mensal f
        left join {schema}.dim_fundo d
            on d.cnpj_fundo_classe = f.cnpj_fundo_classe and d.fl_versao_atual
        where f.sk_mes = ?
        order by posicao
        limit ?
    """
    cursor = con.execute(sql, [month, top])
    names = [d[0] for d in cursor.description]
    items = [
        RankingCaptacaoItem.model_validate(dict(zip(names, r, strict=True)))
        for r in cursor.fetchall()
    ]
    if not items:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no data for month {month.strftime('%Y-%m')}"
        )
    return RankingCaptacao(sk_mes=month, ordem=ordem, top=top, items=items)
