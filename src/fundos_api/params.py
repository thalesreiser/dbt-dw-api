"""Validated request inputs shared by the `/v1` endpoints (RNF-03).

Invalid input is rejected with 422 before any query runs. The endpoints that use these
dependencies arrive with tasks 5.2-5.4.
"""

from typing import Annotated

from fastapi import Depends, Path, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from fundos_api.config import HARD_MAX_PAGE_SIZE, Settings
from fundos_api.db import get_settings_from_app

CNPJ_PATTERN = r"^\d{14}$"
MAX_OFFSET = 1_000_000

# A fund/class CNPJ in a path: exactly 14 digits, no punctuation.
CnpjPath = Annotated[
    str,
    Path(pattern=CNPJ_PATTERN, description="CNPJ with 14 digits, no punctuation."),
]


class PageQuery(BaseModel):
    """Query parameters `limit` and `offset`."""

    model_config = ConfigDict(extra="forbid")

    limit: int | None = Field(default=None, ge=1, le=HARD_MAX_PAGE_SIZE)
    offset: int = Field(default=0, ge=0, le=MAX_OFFSET)


class PageParams(BaseModel):
    """Resolved pagination: `limit` defaulted and capped by the settings."""

    model_config = ConfigDict(frozen=True)

    limit: int
    offset: int


def pagination(
    query: Annotated[PageQuery, Query()],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> PageParams:
    """FastAPI dependency: validated pagination within `max_page_size`."""
    limit = settings.default_page_size if query.limit is None else query.limit
    if limit > settings.max_page_size:
        raise RequestValidationError(
            [
                {
                    "type": "less_than_equal",
                    "loc": ("query", "limit"),
                    "msg": f"Input should be less than or equal to {settings.max_page_size}",
                    "input": limit,
                    "ctx": {"le": settings.max_page_size},
                }
            ]
        )
    return PageParams(limit=limit, offset=query.offset)
