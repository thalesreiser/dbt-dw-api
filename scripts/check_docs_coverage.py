"""RF-06: documentation coverage of the dbt project (task 4.2).

Reads `dbt/target/manifest.json` and `dbt/target/catalog.json` (written by `dbt docs generate`)
and lists every model, snapshot, seed, source table and exposure without a description, and
every column without one. The columns come from the catalog (what the warehouse really has)
plus the ones declared in yml, so a column that exists but is not documented is reported too.

Exits with status 1 when a resource of a required layer, or one of its columns, has no
description. Default required layers: marts, intermediate, snapshot, seed, staging, exposure;
the raw sources are reported but not required (they keep the original CVM layout, documented
in docs/data-source.md).

Usage: python scripts/check_docs_coverage.py [--target dbt/target] [--require marts,...]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT = "fundos_dw"
DEFAULT_REQUIRED = "marts,intermediate,snapshot,seed,staging,exposure"
LAYERS = ("source", "staging", "intermediate", "snapshot", "seed", "marts", "exposure")


@dataclass
class Resource:
    layer: str
    name: str
    described: bool
    columns: dict[str, bool] = field(default_factory=dict)  # column -> has a description


def _layer(node: dict[str, Any]) -> str:
    resource_type = str(node["resource_type"])
    if resource_type == "model":
        fqn = node.get("fqn", [])
        return str(fqn[1]) if len(fqn) > 2 else "model"
    return resource_type


def _has_text(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def collect(manifest: dict[str, Any], catalog: dict[str, Any]) -> list[Resource]:
    resources: list[Resource] = []
    groups = (
        ("nodes", manifest["nodes"], catalog["nodes"]),
        ("sources", manifest["sources"], catalog["sources"]),
    )
    for kind, manifest_nodes, catalog_nodes in groups:
        for unique_id, node in manifest_nodes.items():
            if node.get("package_name") != PROJECT:
                continue
            if kind == "nodes" and node["resource_type"] not in ("model", "snapshot", "seed"):
                continue
            columns = {
                name.lower(): _has_text(col.get("description"))
                for name, col in node.get("columns", {}).items()
            }
            for name in catalog_nodes.get(unique_id, {}).get("columns", {}):
                columns.setdefault(name.lower(), False)
            name = node["name"] if kind == "nodes" else f"{node['source_name']}.{node['name']}"
            resources.append(
                Resource(_layer(node), name, _has_text(node.get("description")), columns)
            )
    for node in manifest.get("exposures", {}).values():
        if node.get("package_name") == PROJECT:
            resources.append(Resource("exposure", node["name"], _has_text(node.get("description"))))
    return resources


def report(resources: list[Resource], required: set[str]) -> int:
    by_layer: dict[str, list[Resource]] = defaultdict(list)
    for resource in resources:
        by_layer[resource.layer].append(resource)

    failures = 0
    print(f"{'layer':<13} {'resources':>15} {'columns':>15}  required")
    for layer in sorted(by_layer, key=lambda x: LAYERS.index(x) if x in LAYERS else 99):
        items = by_layer[layer]
        n_res = len(items)
        ok_res = sum(r.described for r in items)
        n_col = sum(len(r.columns) for r in items)
        ok_col = sum(sum(r.columns.values()) for r in items)
        is_required = layer in required
        print(
            f"{layer:<13} {ok_res:>7}/{n_res:<7} {ok_col:>7}/{n_col:<7}  "
            f"{'yes' if is_required else 'no'}"
        )
        if is_required:
            failures += (n_res - ok_res) + (n_col - ok_col)

    missing = [
        (r.layer, r.name, col)
        for r in resources
        for col in ([None] if not r.described else [])
        + [c for c, ok in r.columns.items() if not ok]
    ]
    if missing:
        print("\nWithout a description:")
        for layer, name, col in missing:
            flag = "ERROR" if layer in required else "info "
            print(f"  {flag} {layer:<13} {name}{'' if col is None else '.' + col}")
    print(f"\n{failures} undocumented item(s) in required layers ({', '.join(sorted(required))}).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--target", type=Path, default=Path("dbt/target"))
    parser.add_argument("--require", default=DEFAULT_REQUIRED, help="comma-separated layers")
    args = parser.parse_args(argv)
    manifest = json.loads((args.target / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((args.target / "catalog.json").read_text(encoding="utf-8"))
    required = {x.strip() for x in str(args.require).split(",") if x.strip()}
    return report(collect(manifest, catalog), required)


if __name__ == "__main__":
    sys.exit(main())
