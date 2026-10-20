"""RNF-01 load test helpers (task 6.2).

`sample`: write N CNPJs sampled from the current versions of `dim_fundo` (with a daily report
in the latest month) to a file outside the repository, for `loadtest/locustfile.py`.

`report`: turn the locust `<prefix>_stats.csv` into aggregates per endpoint (requests, RPS,
error rate, p50/p95/p99) as JSON and Markdown, and check the RNF-01 target (p95 of the series
below 300 ms). Only aggregates are written: no CNPJ, no row of the warehouse.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

import duckdb

SERIE_NAME = "/v1/fundos/[cnpj]/serie"
TARGET_P95_MS = 300.0


def sample_cnpjs(db_path: Path, schema: str, n: int, seed: float) -> list[str]:
    """N distinct CNPJs of current `dim_fundo` versions that report in the latest month."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        con.execute("select setseed(?)", [seed])
        rows = con.execute(
            f"select cnpj_fundo_classe from {schema}.dim_fundo "
            "where fl_versao_atual and fl_informa_recente and tp_registro <> 'DESCONHECIDO' "
            "order by random() limit ?",
            [n],
        ).fetchall()
    return [str(r[0]) for r in rows]


def _num(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def summarize(stats_csv: Path) -> dict[str, Any]:
    """Per-endpoint aggregates from a locust stats CSV (milliseconds, requests per second)."""
    endpoints: list[dict[str, Any]] = []
    with stats_csv.open(newline="") as fh:
        for row in csv.DictReader(fh):
            count = int(_num(row["Request Count"]))
            failures = int(_num(row["Failure Count"]))
            endpoints.append(
                {
                    "name": row["Name"],
                    "requests": count,
                    "failures": failures,
                    "error_rate": round(failures / count, 4) if count else 0.0,
                    "rps": round(_num(row["Requests/s"]), 2),
                    "p50_ms": _num(row["50%"]),
                    "p95_ms": _num(row["95%"]),
                    "p99_ms": _num(row["99%"]),
                    "max_ms": _num(row["Max Response Time"]),
                }
            )
    serie = next((e for e in endpoints if e["name"] == SERIE_NAME), None)
    return {
        "target": {"endpoint": SERIE_NAME, "p95_ms_below": TARGET_P95_MS},
        "met": bool(serie and serie["requests"] and serie["p95_ms"] < TARGET_P95_MS),
        "endpoints": endpoints,
    }


def to_markdown(summary: dict[str, Any], context: str) -> str:
    lines = [
        "## RNF-01 load test",
        "",
        context,
        "",
        "| Endpoint | Requests | RPS | Error rate | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for e in summary["endpoints"]:
        lines.append(
            f"| `{e['name']}` | {e['requests']} | {e['rps']} | {e['error_rate']:.2%} "
            f"| {e['p50_ms']:.0f} | {e['p95_ms']:.0f} | {e['p99_ms']:.0f} | {e['max_ms']:.0f} |"
        )
    verdict = "met" if summary["met"] else "NOT met"
    lines += ["", f"Target p95 < {TARGET_P95_MS:.0f} ms on `{SERIE_NAME}`: **{verdict}**.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample", help="sample CNPJs from dim_fundo into a file")
    s.add_argument("--db", type=Path, default=Path(os.environ.get("DUCKDB_PATH", "")))
    s.add_argument("--schema", default="marts")
    s.add_argument("-n", type=int, default=500)
    s.add_argument("--seed", type=float, default=0.42)
    s.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("report", help="aggregate a locust stats CSV")
    r.add_argument("--stats", type=Path, required=True, help="locust <prefix>_stats.csv")
    r.add_argument("--json", type=Path, required=True)
    r.add_argument("--markdown", type=Path, required=True)
    r.add_argument("--context", default="", help="environment line for the Markdown report")
    r.add_argument("--fail-on-miss", action="store_true", help="exit 1 if the target is missed")
    args = parser.parse_args(argv)

    if args.command == "sample":
        cnpjs = sample_cnpjs(args.db, args.schema, args.n, args.seed)
        if not cnpjs:
            print("no CNPJ sampled", file=sys.stderr)
            return 1
        args.out.write_text("\n".join(cnpjs) + "\n")
        print(f"sampled {len(cnpjs)} CNPJs")
        return 0

    summary = summarize(args.stats)
    args.json.write_text(json.dumps(summary, indent=2) + "\n")
    markdown = to_markdown(summary, args.context)
    args.markdown.write_text(markdown)
    print(markdown)
    return 1 if args.fail_on_miss and not summary["met"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
