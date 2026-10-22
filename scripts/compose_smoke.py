"""RNF-04 (task 7.2): call the README examples against the API started by `make up`.

Checks status codes and JSON bodies, and prints each response with CNPJs and names masked (shape
and aggregates only, never a real row identifier in the CI log). Standard library only, so it
runs on the CI host without installing the project.

Usage:
    API_KEY=... python scripts/compose_smoke.py [--base-url http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

SITUACAO = "em%20funcionamento%20normal"


def mask(value: Any) -> Any:
    """Copy of a JSON value with CNPJs and names replaced and lists cut to two items."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key.startswith("cnpj") and isinstance(item, str):
                out[key] = "<cnpj>"
            elif key.startswith("nm_") and isinstance(item, str):
                out[key] = "<name>"
            else:
                out[key] = mask(item)
        return out
    if isinstance(value, list):
        return [mask(item) for item in value[:2]]
    return value


def get(base_url: str, path: str, api_key: str | None) -> tuple[int, Any]:
    """GET `path`; return the status code and the decoded JSON body."""
    request = urllib.request.Request(base_url + path)
    if api_key is not None:
        request.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    return status, json.loads(body)


def check(base_url: str, path: str, api_key: str | None, expected: int) -> Any:
    """Call `path`, print the masked response and fail unless the status is `expected`."""
    status, body = get(base_url, path, api_key)
    shown = path.replace(SITUACAO, "...") if "cnpj" not in path else path
    print(f"GET {shown} -> {status}")
    print(json.dumps(mask(body), ensure_ascii=False, indent=1))
    if status != expected:
        raise SystemExit(f"expected {expected}, got {status} for {path}")
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    api_key = os.environ.get("API_KEY", "")
    if not api_key:
        parser.error("set API_KEY")
    base = args.base_url.rstrip("/")

    health = check(base, "/health", None, 200)
    assert health["status"] == "ok", health

    fundos = check(base, f"/v1/fundos?situacao={SITUACAO}&limit=2", api_key, 200)
    assert fundos["total"] > 0 and 0 < len(fundos["items"]) <= 2, "empty fund list"
    assert all(i["sit_fundo_classe"] == "EM FUNCIONAMENTO NORMAL" for i in fundos["items"])

    ranking = check(base, "/v1/rankings/captacao?top=3", api_key, 200)
    assert len(ranking["items"]) == 3, "ranking must have 3 items"
    assert isinstance(ranking["items"][0]["vl_captc_liquida_mes"], int | float)

    cnpj = ranking["items"][0]["cnpj_fundo_classe"]
    serie = check(base, f"/v1/fundos/{cnpj}/serie", api_key, 200)
    assert serie["items"], "empty series for the ranking leader"
    assert check(base, "/v1/fundos/00000000000000/serie", api_key, 404)["detail"]

    assert check(base, "/v1/fundos?limit=2", None, 401)["detail"] == "missing X-API-Key header"
    assert check(base, "/v1/fundos?limit=2", "wrong-key", 401)["detail"] == "invalid API key"
    print("compose smoke: all README examples passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
