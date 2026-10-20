"""Pydantic v2 response models (RNF-03).

Field names follow the dbt marts (`dbt/models/marts/_marts.yml`). LGPD: the models carry fund
and class data only. They never include a CPF or the name of a natural person: the manager
columns of `dim_fundo` (`cpf_cnpj_gestor`, `nm_gestor`), which may identify an individual,
are not exposed, and neither is any shareholder data (only the aggregate count `nr_cotst`).
`tests/test_schemas.py` guards this rule.

Amounts are `Decimal` (exact, as stored in DuckDB) and are serialized as JSON strings.
"""

from datetime import date
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


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


class PontoSerie(_Model):
    """One day of the series of a fund/class from `fct_informe_diario` (RF-08)."""

    sk_data: date
    id_subclasse: str | None = None
    vl_quota: Decimal | None = None
    vl_patrim_liq: Decimal | None = None
    vl_total: Decimal | None = None
    vl_captc_dia: Decimal | None = None
    vl_resg_dia: Decimal | None = None
    vl_captc_liquida_dia: Decimal
    nr_cotst: int | None = None


class CaptacaoMensal(_Model):
    """Monthly net inflows of a fund/class from `fct_captacao_mensal` (RF-09)."""

    cnpj_fundo_classe: str = Field(pattern=r"^\d{14}$")
    nm_denominacao_social: str | None = None
    sk_mes: date
    vl_captc_mes: Decimal
    vl_resg_mes: Decimal
    vl_captc_liquida_mes: Decimal
    vl_patrim_liq_fim_mes: Decimal | None = None
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

    Class-level points: subclass rows are rolled up into their class, so `id_subclasse` is null.
    """

    cnpj_fundo_classe: str = Field(pattern=r"^\d{14}$")
    inicio: date = Field(description="First day of the period (inclusive).")
    fim: date = Field(description="Last day of the period (inclusive).")
    items: list[PontoSerie]
