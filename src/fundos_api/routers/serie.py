"""`GET /v1/fundos/{cnpj}/serie` (RF-08): daily series of one fund/class over a period.

Grain (default): one point per day at class level. Subclass rows of `fct_informe_diario` are
rolled up into their class, as in `fct_captacao_mensal` (ADR 006: a CNPJ never reports at class
level and per subclass on the same day): amounts, flows and `nr_cotst` are summed; `vl_quota`
is kept only when the day has a single row, since share values of different subclasses cannot
be added, and `id_subclasse` is null. With `por_subclasse=true` the grain is the fact's: one
point per subclass per day, ordered by (date, subclass), each with its own `vl_quota` and
`id_subclasse` (null for a class that reports without subclasses).

Period: `inicio` and `fim` are optional. `fim` defaults to the latest reported day of the CNPJ
(or `inicio`, if later) and `inicio` to 12 months before `fim`. The range is inclusive, ordered
by date ascending and limited to `MAX_PERIODO_DIAS` days; `inicio > fim` or a longer range gives
422. An unknown CNPJ gives 404; a known CNPJ without points in the period gives 200 with an
empty list. Every value reaches DuckDB as a bound parameter.
"""

from calendar import monthrange
from datetime import date, timedelta
from typing import Annotated, Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError

from fundos_api.config import Settings
from fundos_api.db import get_connection, get_settings_from_app
from fundos_api.params import CnpjPath
from fundos_api.schemas import ErrorResponse, PontoSerie, SerieFundo

# About five years of calendar days (including leap days): bounds the scan of one request.
MAX_PERIODO_DIAS = 1830
DEFAULT_PERIODO_MESES = 12

router = APIRouter(tags=["fundos"])

_SERIE_SQL = """
select
    sk_data,
    sum(vl_total)                                           as vl_total,
    case when count(*) = 1 then any_value(vl_quota) end     as vl_quota,
    sum(vl_patrim_liq)                                      as vl_patrim_liq,
    sum(vl_captc_dia)                                       as vl_captc_dia,
    sum(vl_resg_dia)                                        as vl_resg_dia,
    sum(vl_captc_liquida_dia)                               as vl_captc_liquida_dia,
    cast(sum(nr_cotst) as integer)                          as nr_cotst
from {schema}.fct_informe_diario
where cnpj_fundo_classe = ? and sk_data between ? and ?
group by sk_data
order by sk_data
"""

_SERIE_SUBCLASSE_SQL = """
select
    sk_data, id_subclasse, vl_total, vl_quota, vl_patrim_liq, vl_captc_dia, vl_resg_dia,
    vl_captc_liquida_dia, nr_cotst
from {schema}.fct_informe_diario
where cnpj_fundo_classe = ? and sk_data between ? and ?
order by sk_data, id_subclasse nulls first
"""


def _invalid(field: str, msg: str, value: Any) -> RequestValidationError:
    return RequestValidationError(
        [{"type": "value_error", "loc": ("query", field), "msg": msg, "input": str(value)}]
    )


def _check_period(inicio: date, fim: date) -> None:
    if inicio > fim:
        raise _invalid("inicio", "inicio must not be after fim", inicio)
    if (fim - inicio).days + 1 > MAX_PERIODO_DIAS:
        raise _invalid("fim", f"period must not exceed {MAX_PERIODO_DIAS} days", fim)


def months_before(day: date, months: int) -> date:
    """`day` shifted back by `months`, clamped to the last day of a shorter month."""
    year, month0 = divmod(day.year * 12 + day.month - 1 - months, 12)
    month = month0 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def default_inicio(fim: date) -> date:
    """First day of the default 12-month window ending on `fim` (inclusive)."""
    return months_before(fim, DEFAULT_PERIODO_MESES) + timedelta(days=1)


def _rows(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [d[0] for d in cursor.description or []]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


@router.get(
    "/fundos/{cnpj}/serie",
    response_model=SerieFundo,
    responses={404: {"model": ErrorResponse, "description": "CNPJ not found"}},
)
def serie_fundo(
    cnpj: CnpjPath,
    con: Annotated[duckdb.DuckDBPyConnection, Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    inicio: Annotated[
        date | None,
        Query(description="First day (inclusive). Default: 12 months before `fim`."),
    ] = None,
    fim: Annotated[
        date | None,
        Query(description="Last day (inclusive). Default: latest reported day of the CNPJ."),
    ] = None,
    por_subclasse: Annotated[
        bool,
        Query(
            description="`true`: one point per subclass per day, each with its own `vl_quota` "
            "and `id_subclasse`. Default: class-level points (amounts summed, `vl_quota` null "
            "on days with more than one subclass)."
        ),
    ] = False,
) -> SerieFundo:
    """Daily series (share value, net assets, flows) of a fund/class, ordered by date."""
    if inicio is not None and fim is not None:
        _check_period(inicio, fim)
    schema = settings.marts_schema
    known = con.execute(
        f"select 1 from {schema}.dim_fundo "
        "where cnpj_fundo_classe = ? and tp_registro <> 'DESCONHECIDO' limit 1",
        [cnpj],
    ).fetchone()
    if known is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CNPJ not found")
    if fim is None:
        row = con.execute(
            f"select max(sk_data) from {schema}.fct_informe_diario where cnpj_fundo_classe = ?",
            [cnpj],
        ).fetchone()
        latest = row[0] if row and isinstance(row[0], date) else date.today()
        fim = latest if inicio is None else max(latest, inicio)
    if inicio is None:
        inicio = default_inicio(fim)
    _check_period(inicio, fim)
    sql = _SERIE_SUBCLASSE_SQL if por_subclasse else _SERIE_SQL
    cursor = con.execute(sql.format(schema=schema), [cnpj, inicio, fim])
    items = [PontoSerie(**row) for row in _rows(cursor)]
    return SerieFundo(cnpj_fundo_classe=cnpj, inicio=inicio, fim=fim, items=items)
