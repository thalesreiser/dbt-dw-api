"""RF-06 (4.2): the documentation coverage check fails on an undocumented mart column."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_docs_coverage.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_docs_coverage", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve the module by name
    spec.loader.exec_module(module)
    return module


def _write(target: Path, mart_column_description: str, extra_column: bool = True) -> None:
    uid = "model.fundos_dw.dim_data"
    manifest: dict[str, Any] = {
        "nodes": {
            uid: {
                "resource_type": "model",
                "package_name": "fundos_dw",
                "name": "dim_data",
                "fqn": ["fundos_dw", "marts", "dim_data"],
                "description": "Calendar dimension.",
                "columns": {"sk_data": {"description": mart_column_description}},
            }
        },
        "sources": {},
        "exposures": {},
    }
    # The catalog has a column the yml does not declare: it must count as undocumented too.
    columns = {"SK_DATA": {}, "nr_ano": {}} if extra_column else {"SK_DATA": {}}
    catalog = {"nodes": {uid: {"columns": columns}}, "sources": {}}
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (target / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")


@pytest.mark.parametrize(
    ("require", "expected"), [("marts", 1), ("staging", 0)], ids=["required", "not-required"]
)
def test_undocumented_catalog_column(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], require: str, expected: int
) -> None:
    _write(tmp_path, "The calendar date.")
    assert _load().main(["--target", str(tmp_path), "--require", require]) == expected
    assert "dim_data.nr_ano" in capsys.readouterr().out


@pytest.mark.parametrize(("description", "expected"), [("The calendar date.", 0), ("  ", 1)])
def test_blank_description_fails(tmp_path: Path, description: str, expected: int) -> None:
    _write(tmp_path, description, extra_column=False)
    assert _load().main(["--target", str(tmp_path), "--require", "marts"]) == expected
