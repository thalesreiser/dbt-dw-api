"""Validated request inputs shared by the `/v1` endpoints (RNF-03).

Invalid input is rejected with 422 before any query runs. Unknown query parameters are
ignored (FastAPI default), so pagination combines freely with the filters of each endpoint.
"""

import re
from datetime import date
from typing import Annotated

from fastapi import Depends, Path, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, BeforeValidator, ConfigDict

from fundos_api.config import HARD_MAX_PAGE_SIZE, Settings
from fundos_api.db import get_settings_from_app

CNPJ_PATTERN = r"^\d{14}$"
MAX_OFFSET = 1_000_000

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _require_iso_date(value: object) -> object:
    # Pydantic's lax mode would also take `0` or `1700000000` as a Unix timestamp; the
    # contract (`format: date`) only allows `YYYY-MM-DD` (found by Schemathesis, RF-11).
    if isinstance(value, str) and not _ISO_DATE.fullmatch(value):
        raise ValueError("Input should be a valid date in the format YYYY-MM-DD")
    return value


# A calendar day in a query string: strictly `YYYY-MM-DD`, as documented (`format: date`).
IsoDate = Annotated[date, BeforeValidator(_require_iso_date)]

# A fund/class CNPJ in a path: exactly 14 digits, no punctuation.
CnpjPath = Annotated[
    str,
    Path(
        pattern=CNPJ_PATTERN,
        description="CNPJ with 14 digits, no punctuation.",
        # Synthetic CNPJ (valid check digits, no real fund); present in the test warehouse,
        # so the contract tests (RF-11) also exercise the 200 path.
        openapi_examples={"classe": {"summary": "Fund class", "value": "11222333000181"}},
    ),
]


class PageParams(BaseModel):
    """Resolved pagination: `limit` defaulted and capped by the settings."""

    model_config = ConfigDict(frozen=True)

    limit: int
    offset: int


def pagination(
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    limit: Annotated[
        int | None,
        Query(
            ge=1,
            le=HARD_MAX_PAGE_SIZE,
            description="Page size; default `DEFAULT_PAGE_SIZE`, at most `MAX_PAGE_SIZE`.",
        ),
    ] = None,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET, description="Number of rows to skip.")] = 0,
) -> PageParams:
    """FastAPI dependency: validated pagination within `max_page_size`.

    Plain query parameters (not a query model), so it combines with any endpoint filters.
    Unknown query parameters are ignored, as everywhere in the API; invalid `limit`/`offset`
    values give 422.
    """
    size = settings.default_page_size if limit is None else limit
    if size > settings.max_page_size:
        raise RequestValidationError(
            [
                {
                    "type": "less_than_equal",
                    "loc": ("query", "limit"),
                    "msg": f"Input should be less than or equal to {settings.max_page_size}",
                    "input": size,
                    "ctx": {"le": settings.max_page_size},
                }
            ]
        )
    return PageParams(limit=size, offset=offset)
