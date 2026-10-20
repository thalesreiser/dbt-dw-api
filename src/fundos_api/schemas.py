"""Pydantic v2 response models (RNF-03).

Field names follow the dbt marts (`dbt/models/marts/_marts.yml`). LGPD: the models carry fund
and class data only. They never include a CPF or the name of a natural person: the manager
columns of `dim_fundo` (`cpf_cnpj_gestor`, `nm_gestor`), which may identify an individual,
are not exposed, and neither is any shareholder data (only the aggregate count `nr_cotst`).
`tests/test_schemas.py` guards this rule.

Number format: values are `Decimal` internally (exact, as stored in DuckDB) and JSON numbers
on the wire. Monetary amounts (`Valor`) are rounded to 2 decimal places (`1500.25`); the share
value `vl_quota` (`Quota`, a unit price with up to 12 decimals) is not rounded and keeps the
precision of a JSON number (an IEEE 754 double, 15-17 significant digits). Counts are integers.
"""

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

T = TypeVar("T")

_CENTAVOS = Decimal("0.01")


def _valor_json(value: Decimal) -> float:
    return float(value.quantize(_CENTAVOS, rounding=ROUND_HALF_EVEN))


# Monetary amount: JSON number rounded to 2 decimal places.
Valor = Annotated[
    Decimal,
    PlainSerializer(_valor_json, return_type=float, when_used="json"),
    Field(description="Amount in BRL, JSON number rounded to 2 decimal places."),
]
# Share value (unit price, up to 12 decimals): JSON number, not rounded.
Quota = Annotated[
    Decimal,
    PlainSerializer(float, return_type=float, when_used="json"),
    Field(description="Share value, JSON number not rounded (up to 12 decimal places)."),
]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HealthResponse(_Model):
    """Liveness and warehouse status. Never exposes file paths."""

    status: Literal["ok", "unavailable"]
    database: Literal["reachable", "unreachable"]
    latest_month: date | None = Field(
        default=None,
        description="Latest reference month loaded (`max(dt_mes_competencia)` of the daily fact).",
    )


class ErrorResponse(_Model):
    """Error body for 4xx/5xx responses raised by the API (validation errors use FastAPI's)."""

    detail: str


class FundoResumo(_Model):
    """Fund/class summary from the current version of `dim_fundo` (RF-07)."""

    cnpj_fundo_classe: str = Field(pattern=r"^\d{14}$")
    tp_registro: Literal["CLASSE", "FUNDO", "DESCONHECIDO"]
    cnpj_fundo: str | None = None
    nm_denominacao_social: str
    nm_denominacao_social_fundo: str | None = None
    tp_fundo: str | None = None
    tp_classe: str | None = None
    sit_fundo_classe: str
    tp_classificacao: str | None = None
    tp_classificacao_anbima: str | None = None
    tp_condominio: str | None = None
    tp_publico_alvo: str | None = None
    fl_exclusivo: bool | None = None
    cnpj_administrador: str | None = None
    nm_administrador: str | None = None
    dt_registro: date | None = None
    fl_informa_recente: bool = Field(
        description="The CNPJ has a daily report in the latest reference month loaded "
        "(e.g. a `CANCELADO` fund that still reports)."
    )


class PontoSerie(_Model):
    """One day of the series of a fund/class from `fct_informe_diario` (RF-08)."""

    sk_data: date
    id_subclasse: str | None = None
    vl_quota: Quota | None = None
    vl_patrim_liq: Valor | None = None
    vl_total: Valor | None = None
    vl_captc_dia: Valor | None = None
    vl_resg_dia: Valor | None = None
    vl_captc_liquida_dia: Valor
    nr_cotst: int | None = None


class CaptacaoMensal(_Model):
    """Monthly net inflows of a fund/class from `fct_captacao_mensal` (RF-09)."""

    cnpj_fundo_classe: str = Field(pattern=r"^\d{14}$")
    nm_denominacao_social: str | None = None
    sk_mes: date
    vl_captc_mes: Valor
    vl_resg_mes: Valor
    vl_captc_liquida_mes: Valor
    vl_patrim_liq_fim_mes: Valor | None = None
    nr_cotst_fim_mes: int | None = None
    nr_dias_informados: int


class Page(_Model, Generic[T]):
    """Paginated envelope (limit/offset)."""

    items: list[T]
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    total: int = Field(ge=0, description="Total number of matching rows.")


class SerieFundo(_Model):
    """Daily series of one fund/class over a period (RF-08), ordered by `sk_data` ascending.

    Default: class-level points (subclass rows rolled up into their class, `id_subclasse`
    null). With `por_subclasse=true`: one point per subclass per day, ordered by date and
    subclass, each with its own `vl_quota` and `id_subclasse`.
    """

    cnpj_fundo_classe: str = Field(pattern=r"^\d{14}$")
    inicio: date = Field(description="First day of the period (inclusive).")
    fim: date = Field(description="Last day of the period (inclusive).")
    items: list[PontoSerie]


class RankingCaptacaoItem(CaptacaoMensal):
    """One position of the monthly net inflows ranking (RF-09)."""

    posicao: int = Field(ge=1, description="Position in the ranking, starting at 1.")


class RankingCaptacao(_Model):
    """Top N funds/classes of a month by net inflows (RF-09, RN-01)."""

    sk_mes: date = Field(description="Reference month (first day).")
    ordem: Literal["desc", "asc"]
    top: int = Field(ge=1)
    items: list[RankingCaptacaoItem]
