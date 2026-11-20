# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------

"""CLI/SnapshotAnalyzer semantic contract tests.

These tests compare normalized CLI semantics with SnapshotAnalyzer rather than
raw CLI text. They guard the shared API/core contract from adapter drift.

API-specific shapes are asserted as-is: ``get_template_info()`` returns ``None``
for a missing template, and ``execute_query()`` defaults to ``max_rows=None``.
"""

from __future__ import annotations

import ast
import inspect
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import FocusState, SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core import InvalidDeviceError, QueryExecutionError, TemplateRenderError
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.core.common.error_codes import classify_error
from pt_snap_cli.core.common.errors import QueryCancelledError, QueryTimeoutError
from pt_snap_cli.core.common.json_codec import JSON_SCHEMA_VERSION
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from pt_snap_cli.query.config import QueryParameter, QueryTemplate
from pt_snap_cli.query.registry import QueryRegistry, register_query
from test.test_dataset_focus import make_dataset

runner = CliRunner()

pytestmark = pytest.mark.usefixtures("owned_service_instances")


def test_cancelled_query_has_a_distinct_non_timeout_error_code(tmp_path, monkeypatch):
    error = QueryCancelledError("Frame tree query cancelled by a newer request or reset.")
    assert isinstance(error, QueryExecutionError)
    assert classify_error(error)[0] == "QUERY_CANCELLED"
    root = make_dataset(tmp_path / "cancelled", devices=(0,))

    def cancelled_tree(*args, **kwargs):
        raise error

    monkeypatch.setattr("pt_snap_cli.core.analysis.query_service.frame_tree", cancelled_tree)
    with SnapshotAnalyzer(root) as analyzer:
        with pytest.raises(QueryCancelledError):
            analyzer.execute_query("active_memory_frame_tree_at_event", {"event_id": 1})
    result = runner.invoke(
        app,
        [
            "query",
            str(root),
            "--template-use",
            "active_memory_frame_tree_at_event",
            "--params",
            '{"event_id":1}',
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "QUERY_CANCELLED"


@pytest.mark.parametrize("template", ["event", "block"])
@pytest.mark.parametrize("params", [{"min_size": 2**63}, {"offset": 2**63, "limit": 1}])
def test_dataset_int64_overflow_cli_api_domain_error(tmp_path, template, params):
    if template == "event" and "min_size" in params:
        params = {"min_allocated": params["min_size"]}
    root = make_dataset(tmp_path / "int64-overflow", devices=(0,))
    with SnapshotAnalyzer(root) as analyzer:
        with pytest.raises(QueryExecutionError):
            analyzer.execute_query(template, params)
    result = runner.invoke(
        app,
        ["query", str(root), "--template-use", template, "--params", json.dumps(params), "--json"],
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "QUERY_FAILED"
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("surface", ["service", "api", "report", "cli-query", "cli-report"])
@pytest.mark.parametrize("failure_kind", ["budget", "timeout"])
def test_dataset_budget_error_keeps_message_kind_and_no_partial_result(tmp_path, monkeypatch, surface, failure_kind):
    root = make_dataset(tmp_path / "budget-error", devices=(0,))
    consume = QueryBudget.consume
    failures = []

    def bounded_consume(budget, rows):
        try:
            if failure_kind == "timeout":
                raise QueryTimeoutError(f"Query timed out after {budget.timeout_s} seconds")
            budget.max_work_rows = 1
            consume(budget, rows)
        except QueryExecutionError as exc:
            failures.append(exc)
            raise

    monkeypatch.setattr(QueryBudget, "consume", bounded_consume)
    expected_type = QueryTimeoutError if failure_kind == "timeout" else QueryExecutionError
    if surface in {"service", "api", "report"}:
        with (
            closing(QueryService()) as service,
            SnapshotAnalyzer(root) as analyzer,
            closing(ReportService()) as report,
        ):
            with pytest.raises(expected_type) as caught:
                if surface == "service":
                    service.execute_query("event", db_path=root, timeout_s=30)
                elif surface == "api":
                    analyzer.execute_query("event", timeout_s=30)
                else:
                    report.peak_memory_report(root, timeout_s=30)
        assert len(failures) == 1
        assert type(caught.value) is expected_type
        assert str(caught.value) == str(failures[0])
    else:
        args = (
            ["query", str(root), "--template-use", "event"]
            if surface == "cli-query"
            else ["report", "peak-memory", str(root)]
        ) + ["--timeout", "30"]
        for json_mode in (False, True):
            failures.clear()
            result = runner.invoke(app, args + (["--json"] if json_mode else []))
            assert result.exit_code == 1
            assert len(failures) == 1
            expected_message = str(failures[0])
            if json_mode:
                assert result.stdout == ""
                payload = json.loads(result.stderr)
                assert payload["error"]["code"] == ("QUERY_TIMEOUT" if failure_kind == "timeout" else "QUERY_FAILED")
                assert payload["error"]["message"] == expected_message
                assert "rows" not in payload and "callstack_groups" not in payload
            else:
                prefix = "Error executing query: " if surface == "cli-query" else "Error generating report: "
                assert result.stdout == f"{prefix}{expected_message}\n"
                assert result.stderr == ""


@pytest.mark.parametrize("template", ["event", "active_memory_callstack_at_event"])
def test_stack_summary_cli_api_and_catalog_contract(contract_db: Path, template: str):
    with closing(sqlite3.connect(contract_db)) as conn, conn:
        conn.execute(
            "INSERT INTO trace_entry_0 VALUES (1, 4, 4096, 2048, 0, 2048, 2048, 4096, ?)",
            ("训练.py:42 forward\n" * 1000,),
        )
    params = {"stack_bytes": 17}
    if template == "active_memory_callstack_at_event":
        params["event_id"] = 1
    with SnapshotAnalyzer(db_path=contract_db, device_id=0) as analyzer:
        api_result = analyzer.execute_query(template, params=params)
        cli_result = runner.invoke(
            app,
            [
                "query",
                str(contract_db),
                "--device",
                "0",
                "--template-use",
                template,
                "--params",
                json.dumps(params),
                "--json",
            ],
        )
        assert cli_result.exit_code == 0, cli_result.output
        payload = json.loads(cli_result.output)
        for key in ("rows", "total", "returned", "has_more", "truncated", "total_is_exact"):
            assert payload[key] == api_result[key]
        assert payload["effective_params"]["stack_bytes"] == 17
        assert any(row["stack_truncated"] for row in api_result["rows"])
        info = analyzer.get_template_info(template)
        assert info["parameters"]["stack_bytes"]["default"] == -1
        fields = {field["column"] for field in info["output_schema"]}
        assert {
            "stack_id",
            "stack_kind",
            "stack_event_id",
            "stack_bytes",
            "stack_original_bytes",
            "stack_truncated",
        } <= fields
        catalog = runner.invoke(app, ["capabilities", "--json"])
        assert catalog.exit_code == 0, catalog.output
        entry = next(t for t in json.loads(catalog.output)["templates"] if t["name"] == template)
        assert entry["output_schema"] == info["output_schema"]
        assert entry["parameters"] == info["parameters"]


@pytest.mark.parametrize(
    "template,params",
    [
        ("memory_peak", {}),
        ("allocator_gap", {"start_id": 1, "end_id": 4}),
        ("event", {"min_id": 1, "max_id": 4, "limit": 2, "offset": 1}),
        ("allocation", {"min_id": 1, "max_id": 4, "order_by": "active"}),
        ("callstack_analysis", {"min_count": 1, "limit": 1}),
        ("block", {}),
        ("leak_detection", {}),
    ],
)
def test_dataset_global_cli_api_scope_catalog_and_total_contract(tmp_path, template, params):
    root = make_dataset(tmp_path / "global-contract", devices=(0,))
    with SnapshotAnalyzer(root) as analyzer:
        api = analyzer.execute_query(template, params, exact_total=True)
        cli = runner.invoke(
            app,
            [
                "query",
                str(root),
                "--template-use",
                template,
                "--params",
                json.dumps(params),
                "--exact-total",
                "--json",
            ],
        )
        assert cli.exit_code == 0, cli.output
        payload = json.loads(cli.stdout)
        for key in api:
            assert payload[key] == api[key]
        info = analyzer.get_template_info(template)
        assert info["dataset_support"]["supported"]
        catalog = runner.invoke(app, ["capabilities", "--json"])
        entry = next(c for c in json.loads(catalog.stdout)["templates"] if c["name"] == template)
        assert entry["dataset_support"] == info["dataset_support"]
        assert api["scope"]["boundary_events_included"] is False


def create_contract_db(db_path: Path) -> Path:
    """Create a tiny snapshot database shared by CLI and API contract paths."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE dictionary (
            `table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT
        )
    """)
    for device_id, rows in {
        0: [
            (1, 0x1000, 2048, 2000, 1, 1, -1),
            (2, 0x2000, 512, 500, 0, 2, 3),
        ],
        1: [
            (3, 0x3000, 4096, 4000, 1, 4, None),
        ],
    }.items():
        conn.execute(f"""
            CREATE TABLE trace_entry_{device_id} (
                id INTEGER PRIMARY KEY, action INTEGER, address INTEGER,
                size INTEGER, stream INTEGER, allocated INTEGER,
                active INTEGER, reserved INTEGER, callstack TEXT
            )
        """)
        conn.execute(f"""
            CREATE TABLE block_{device_id} (
                id INTEGER PRIMARY KEY, address INTEGER, size INTEGER,
                requestedSize INTEGER, state INTEGER, allocEventId INTEGER,
                freeEventId INTEGER
            )
        """)
        conn.executemany(
            f"""
            INSERT INTO block_{device_id}
              (id, address, size, requestedSize, state, allocEventId, freeEventId)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def _isolate_contract_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    with patch.object(Path, "home", return_value=tmp_path):
        QueryRegistry.reset()
        yield
        QueryRegistry.reset()


@pytest.fixture
def contract_db(tmp_path: Path) -> Path:
    return create_contract_db(tmp_path / "contract.db")


@pytest.fixture
def analyzer() -> SnapshotAnalyzer:
    return SnapshotAnalyzer()


def _focused_analyzer(db_path: Path, device_id: int | None = None) -> SnapshotAnalyzer:
    return SnapshotAnalyzer(db_path=db_path, device_id=device_id)


def _focus_payload(state: FocusState) -> dict[str, object]:
    return {
        "db_path": state.db_path,
        "device_id": state.device_id,
        "available_devices": state.available_devices,
        "callstack_layout": state.callstack_layout,
        "callstack_layout_error": state.callstack_layout_error,
    }


def _coerce_cli_default(default_text: str) -> object:
    if default_text in {"True", "False"}:
        return default_text == "True"
    try:
        return int(default_text)
    except ValueError:
        try:
            return float(default_text)
        except ValueError:
            return default_text


def _normalize_cli_focus(output: str) -> dict[str, object]:
    focus: dict[str, object] = {}
    for line in output.splitlines():
        if line.startswith("Using project database: "):
            focus["db_path"] = line.removeprefix("Using project database: ")
        elif line.startswith("Focused device: "):
            focus["device_id"] = int(line.removeprefix("Focused device: "))
        elif line.startswith("Available devices: "):
            focus["available_devices"] = [
                int(device.strip()) for device in line.removeprefix("Available devices: ").split(",")
            ]
        elif line.startswith("Callstack layout: "):
            focus["callstack_layout"] = line.removeprefix("Callstack layout: ").split(" ", 1)[0]
        elif line.startswith("Warning: "):
            focus["callstack_layout_error"] = line.removeprefix("Warning: ")
    focus.setdefault("device_id", None)
    focus.setdefault("available_devices", [])
    focus.setdefault("callstack_layout", None)
    focus.setdefault("callstack_layout_error", None)
    return focus


def _normalize_cli_template_list(output: str) -> list[dict[str, str]]:
    templates: list[dict[str, str]] = []
    category: str | None = None
    lines = output.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.endswith(" Queries:"):
            category = line.removesuffix(" Queries:").lower().replace(" ", "_")
        elif line.startswith("  ") and not line.startswith("    "):
            name = line.strip()
            description = lines[index + 1].strip() if index + 1 < len(lines) else ""
            templates.append({"name": name, "description": description, "category": category or ""})
            index += 2
            continue
        index += 1
    return templates


def _normalize_cli_template_info(output: str) -> dict[str, object]:
    info: dict[str, object] = {
        "parameters": {},
        "output_schema": [],
        "semantics_version": None,
        "interpretation_limits": [],
    }
    section: str | None = None
    current_param: str | None = None
    current_column: dict[str, object] | None = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("Template: "):
            info["name"] = stripped.removeprefix("Template: ")
        elif stripped.startswith("Description: "):
            info["description"] = stripped.removeprefix("Description: ")
        elif stripped.startswith("Category: "):
            info["category"] = stripped.removeprefix("Category: ")
        elif stripped.startswith("Devices: "):
            info["devices"] = stripped.removeprefix("Devices: ")
        elif stripped.startswith("Dataset Support: "):
            info["dataset_support"] = json.loads(stripped.removeprefix("Dataset Support: "))
        elif stripped.startswith("Semantics Version: "):
            text = stripped.removeprefix("Semantics Version: ")
            info["semantics_version"] = None if text == "none" else int(text)
        elif stripped == "Parameters:":
            section = "parameters"
            current_column = None
        elif stripped == "Output Schema:":
            section = "output_schema"
            current_column = None
        elif stripped == "Interpretation Limits:":
            section = "template_interpretation_limits"
            current_column = None
        elif stripped == "Example Usage:":
            section = None
            current_column = None
        elif section == "parameters" and line.startswith("  ") and not line.startswith("    "):
            name, metadata = stripped.split(": ", 1)
            param_type = metadata.split(" ", 1)[0]
            required = "(required)" in metadata
            default = None
            if "[default: " in metadata:
                default_text = metadata.split("[default: ", 1)[1].removesuffix("]")
                default = _coerce_cli_default(default_text)
            choices = None
            if "[choices: " in metadata:
                choices_text = metadata.split("[choices: ", 1)[1].split("]", 1)[0]
                choices = [_coerce_cli_default(item) for item in choices_text.split(", ")]
            info["parameters"][name] = {
                "type": param_type,
                "default": default,
                "required": required,
                "description": "",
                "choices": choices,
            }
            current_param = name
        elif section == "parameters" and current_param and line.startswith("    "):
            info["parameters"][current_param]["description"] = stripped
        elif section == "output_schema" and stripped == "Dynamic (depends on query)":
            continue
        elif section == "output_schema" and line.startswith("      - "):
            assert current_column is not None
            limits = current_column.setdefault("interpretation_limits", [])
            assert isinstance(limits, list)
            limits.append(stripped[2:])
        elif section == "output_schema" and line.startswith("    ") and not line.startswith("     "):
            assert current_column is not None
            if stripped.endswith(":") and ": " not in stripped:
                current_column[stripped[:-1]] = []
            else:
                key, value = stripped.split(": ", 1)
                current_column[key] = _coerce_cli_default(value) if key == "sentinel" else value
        elif section == "output_schema" and line.startswith("  ") and not line.startswith("    "):
            column, column_type = stripped.split(": ", 1)
            current_column = {"column": column, "type": column_type}
            schema = info["output_schema"]
            assert isinstance(schema, list)
            schema.append(current_column)
        elif section == "template_interpretation_limits" and stripped.startswith("- "):
            limits = info["interpretation_limits"]
            assert isinstance(limits, list)
            limits.append(stripped[2:])

    return info


def _normalize_cli_query_result(output: str, device_id: int) -> dict[str, object]:
    lines = output.splitlines()
    header = lines[0]
    total = int(header.split("Found ", 1)[1].split(" results", 1)[0])
    returned = int(header.split("showing ", 1)[1].split(":", 1)[0])
    rows = [ast.literal_eval(line.strip()) for line in lines[1:] if line.startswith("  {")]
    return {"total": total, "returned": returned, "device_id": device_id, "rows": rows}


def _assert_query_execution_contract(
    cli_query: dict[str, object],
    api_query: dict[str, object],
    template: str,
    semantics_version: int | None,
) -> None:
    shared = {key: api_query[key] for key in ("total", "returned", "device_id", "rows")}
    assert cli_query == shared
    assert api_query["template"] == template
    assert api_query["semantics_version"] == semantics_version


def _normalize_cli_missing_focus(output: str) -> dict[str, str]:
    return {"kind": "focus_not_configured"}


def test_execute_query_default_max_rows_is_unlimited() -> None:
    """API default remains max_rows=None. Do not restore the removed MCP cap of 100."""
    default = inspect.signature(SnapshotAnalyzer.execute_query).parameters["max_rows"].default
    assert default is None


def test_focus_contract_matches_cli_and_api_semantics(contract_db: Path, analyzer: SnapshotAnalyzer) -> None:
    cli_result = runner.invoke(app, ["focus", str(contract_db), "--device", "1"])
    assert cli_result.exit_code == 0

    cli_focus = _normalize_cli_focus(cli_result.stdout)
    api_focus = _focus_payload(analyzer.set_focus(str(contract_db), device_id=1))

    assert cli_focus == api_focus
    assert cli_focus["callstack_layout"] == "v1"
    assert cli_focus["callstack_layout_error"] is None


def test_invalid_focus_device_contract_matches_cli_and_api_semantics(
    contract_db: Path, analyzer: SnapshotAnalyzer
) -> None:
    cli_result = runner.invoke(app, ["focus", str(contract_db), "--device", "99"])
    assert cli_result.exit_code == 1

    with pytest.raises(InvalidDeviceError) as exc_info:
        analyzer.set_focus(str(contract_db), device_id=99)

    assert str(exc_info.value) in cli_result.stdout


def test_template_list_contract_matches_cli_and_api_semantics(analyzer: SnapshotAnalyzer) -> None:
    cli_result = runner.invoke(app, ["query", "--category", "basic"])
    assert cli_result.exit_code == 0

    assert _normalize_cli_template_list(cli_result.stdout) == analyzer.list_templates("basic")


def test_template_info_contract_matches_cli_and_api_semantics(contract_db: Path) -> None:
    cli_result = runner.invoke(
        app,
        ["query", str(contract_db), "--template-info", "allocation"],
    )
    assert cli_result.exit_code == 0
    assert "Category: basic" in cli_result.stdout
    assert "Devices: all" in cli_result.stdout

    cli_info = _normalize_cli_template_info(cli_result.stdout)
    api_info = _focused_analyzer(contract_db).get_template_info("allocation")

    assert cli_info == api_info
    json.dumps(api_info)
    assert cli_info["semantics_version"] is None
    assert cli_info["interpretation_limits"] == []
    assert cli_info["parameters"]["order_by"]["choices"] == [
        "id",
        "allocated",
        "active",
        "reserved",
    ]
    assert cli_info["parameters"]["order_dir"]["choices"] == ["ASC", "DESC"]


def test_template_semantics_contract_matches_cli_and_api(contract_db: Path) -> None:
    """Issue #141: field units and interpretation limits pass through unchanged."""
    analyzer = _focused_analyzer(contract_db)
    for name in (
        "leak_detection",
        "memory_peak",
        "allocator_gap",
        "active_memory_callstack_at_event",
    ):
        cli_result = runner.invoke(
            app,
            ["query", str(contract_db), "--template-info", name],
        )
        assert cli_result.exit_code == 0, cli_result.stdout
        cli_info = _normalize_cli_template_info(cli_result.stdout)
        api_info = analyzer.get_template_info(name)
        assert cli_info == api_info
        json.dumps(api_info)
        assert api_info["semantics_version"] == (
            2 if name in ("active_memory_callstack_at_event", "memory_peak", "allocator_gap") else 1
        )
        assert api_info["interpretation_limits"]


def test_leak_detection_template_does_not_advertise_device_id(contract_db: Path) -> None:
    """Regression for issue #90: ``device_id`` is resolved from focus / --device,
    not from template parameters, so the template metadata must not expose it.
    """
    cli_result = runner.invoke(
        app,
        ["query", str(contract_db), "--template-info", "leak_detection"],
    )
    assert cli_result.exit_code == 0

    cli_info = _normalize_cli_template_info(cli_result.stdout)
    api_info = _focused_analyzer(contract_db).get_template_info("leak_detection")

    for info in (cli_info, api_info):
        assert info is not None
        assert "parameters" in info
        assert "device_id" not in info["parameters"], (
            "leak_detection must not advertise device_id; use --device / API device_id / focus selection instead."
        )
        assert "min_size" in info["parameters"]


def test_query_execution_contract_matches_cli_and_api_semantics(contract_db: Path) -> None:
    params = {"min_size": 1024}
    device_id = 1
    cli_result = runner.invoke(
        app,
        [
            "query",
            str(contract_db),
            "--template-use",
            "leak_detection",
            "--params",
            json.dumps(params),
            "--device",
            str(device_id),
            "-n",
            "0",
        ],
    )
    assert cli_result.exit_code == 0

    cli_query = _normalize_cli_query_result(cli_result.stdout, device_id=device_id)
    api_query = _focused_analyzer(contract_db).execute_query(
        "leak_detection", params=params, device_id=device_id, max_rows=0
    )

    _assert_query_execution_contract(cli_query, api_query, "leak_detection", 1)


def test_event_query_contract_reads_v1_inline_callstack(contract_db: Path) -> None:
    conn = sqlite3.connect(str(contract_db))
    conn.execute(
        """
        INSERT INTO trace_entry_1
          (id, action, address, size, stream, allocated, active, reserved, callstack)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (1, 4, 0x1000, 2048, 0, 2048, 2048, 4096, "train.py:10"),
    )
    conn.commit()
    conn.close()

    cli_result = runner.invoke(
        app,
        [
            "query",
            str(contract_db),
            "--template-use",
            "event",
            "--params",
            json.dumps({"id": 1}),
            "--device",
            "1",
            "-n",
            "0",
        ],
    )
    assert cli_result.exit_code == 0

    cli_query = _normalize_cli_query_result(cli_result.stdout, device_id=1)
    api_query = _focused_analyzer(contract_db).execute_query("event", params={"id": 1}, device_id=1, max_rows=0)

    _assert_query_execution_contract(cli_query, api_query, "event", None)
    assert api_query["rows"][0]["callstack"] == "train.py:10"


def test_query_parameter_error_contract_matches_cli_and_api_semantics(contract_db: Path) -> None:
    register_query(
        QueryTemplate(
            name="required_query",
            query="SELECT {{ count }}",
            parameters={
                "count": QueryParameter(name="count", type="int", required=True),
            },
        )
    )
    cli_result = runner.invoke(
        app,
        ["query", str(contract_db), "--template-use", "required_query"],
    )
    assert cli_result.exit_code == 1
    analyzer = _focused_analyzer(contract_db)

    with pytest.raises(TemplateRenderError) as exc_info:
        analyzer.execute_query("required_query")

    assert str(exc_info.value) in cli_result.stdout


def test_missing_focus_error_contract_matches_cli_and_api_semantics(
    analyzer: SnapshotAnalyzer,
) -> None:
    cli_result = runner.invoke(app, ["query", "--template-use", "leak_detection"])
    assert cli_result.exit_code == 1

    with pytest.raises(RuntimeError) as exc_info:
        analyzer.execute_query("leak_detection")

    assert _normalize_cli_missing_focus(cli_result.stdout) == {"kind": "focus_not_configured"}
    assert str(exc_info.value) == "No database configured. Call set_focus() first."


def test_unknown_parameter_error_contract_matches_cli_and_api_semantics(contract_db: Path) -> None:
    """Regression for issue #120: both surfaces reject undeclared parameters identically."""
    cli_result = runner.invoke(
        app,
        [
            "query",
            str(contract_db),
            "--template-use",
            "leak_detection",
            "--params",
            '{"min_sze": 1024}',
        ],
    )
    assert cli_result.exit_code == 1

    analyzer = _focused_analyzer(contract_db)
    with pytest.raises(TemplateRenderError) as exc_info:
        analyzer.execute_query("leak_detection", params={"min_sze": 1024})

    assert "Unknown parameter(s) for template 'leak_detection': min_sze" in str(exc_info.value)
    assert str(exc_info.value) in cli_result.stdout


def test_choices_error_contract_matches_cli_and_api_semantics(contract_db: Path) -> None:
    """Regression for issue #120: SQL fragment parameters are bounded on both surfaces."""
    params = {"order_by": "(SELECT 1)", "order_dir": "ASC"}
    cli_result = runner.invoke(
        app,
        ["query", str(contract_db), "--template-use", "allocation", "--params", json.dumps(params)],
    )
    assert cli_result.exit_code == 1

    analyzer = _focused_analyzer(contract_db)
    with pytest.raises(TemplateRenderError) as exc_info:
        analyzer.execute_query("allocation", params=params)

    assert "Parameter 'order_by' must be one of: id, allocated, active, reserved" in str(exc_info.value)
    assert str(exc_info.value) in cli_result.stdout


def test_missing_template_error_contract_matches_cli_and_api_semantics(
    analyzer: SnapshotAnalyzer,
) -> None:
    template_name = "does_not_exist"
    cli_result = runner.invoke(app, ["query", "--template-info", template_name])
    assert cli_result.exit_code == 1
    assert f"Template '{template_name}' not found" in cli_result.stdout
    assert analyzer.get_template_info(template_name) is None


def test_metadata_contract_matches_cli_and_api_semantics(contract_db: Path) -> None:
    cli_result = runner.invoke(app, ["metadata", str(contract_db), "--json"])
    assert cli_result.exit_code == 0

    assert json.loads(cli_result.stdout) == _focused_analyzer(contract_db).get_database_metadata()


def _json_stdout(result) -> dict[str, object]:
    assert result.exit_code == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == JSON_SCHEMA_VERSION
    assert payload["ok"] is True
    return payload


def test_focus_json_contract_matches_api_semantics(contract_db: Path) -> None:
    cli_result = runner.invoke(app, ["focus", str(contract_db), "--device", "1", "--json"])
    payload = _json_stdout(cli_result)
    analyzer = SnapshotAnalyzer()
    api_focus = _focus_payload(analyzer.set_focus(str(contract_db), device_id=1))

    assert payload["db_path"] == api_focus["db_path"]
    assert payload["device_id"] == api_focus["device_id"]
    assert payload["available_devices"] == api_focus["available_devices"]
    assert payload["callstack_layout"] == api_focus["callstack_layout"]
    assert payload["callstack_layout_error"] == api_focus["callstack_layout_error"]


def test_template_list_json_contract_matches_api_semantics(analyzer: SnapshotAnalyzer) -> None:
    cli_result = runner.invoke(app, ["query", "--list", "--category", "basic", "--json"])
    payload = _json_stdout(cli_result)
    assert payload["templates"] == analyzer.list_templates("basic")


def test_template_info_json_contract_matches_api_semantics(contract_db: Path) -> None:
    cli_result = runner.invoke(app, ["query", str(contract_db), "--template-info", "leak_detection", "--json"])
    payload = _json_stdout(cli_result)
    api_info = _focused_analyzer(contract_db).get_template_info("leak_detection")
    assert api_info is not None
    shared = {key: payload[key] for key in api_info}
    assert shared == api_info
    assert payload["template"] == "leak_detection"
    assert payload["semantics_version"] == 1


def test_query_json_contract_matches_api_semantics(contract_db: Path) -> None:
    params = {"min_size": 1024}
    cli_result = runner.invoke(
        app,
        [
            "query",
            str(contract_db),
            "--template-use",
            "leak_detection",
            "--params",
            json.dumps(params),
            "--device",
            "1",
            "-n",
            "0",
            "--json",
        ],
    )
    payload = _json_stdout(cli_result)
    api_query = _focused_analyzer(contract_db).execute_query("leak_detection", params=params, device_id=1, max_rows=0)
    for key in (
        "total",
        "returned",
        "device_id",
        "rows",
        "template",
        "semantics_version",
        "has_more",
        "truncated",
        "total_is_exact",
        "timeout_s",
    ):
        assert payload[key] == api_query[key]
    assert payload["effective_params"]["min_size"] == 1024
    assert payload["has_more"] is False
    assert payload["truncated"] is False
    assert payload["total_is_exact"] is True


@pytest.mark.parametrize("layout", ["v1", "v2"])
def test_missing_callstack_query_json_contract(contract_db: Path, layout: str) -> None:
    name = "active_memory_callstack_at_event"
    with closing(sqlite3.connect(contract_db)) as conn, conn:
        if layout == "v1":
            conn.executemany(
                "INSERT INTO trace_entry_0 (id, callstack) VALUES (?, ?)",
                [(1, ""), (2, None)],
            )
        else:
            conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
            conn.executemany("INSERT INTO callstack VALUES (?, ?)", [(1, ""), (2, None)])
            for device in (0, 1):
                conn.execute(f"ALTER TABLE trace_entry_{device} DROP COLUMN callstack")
                conn.execute(f"ALTER TABLE trace_entry_{device} ADD COLUMN callstackId INTEGER")
            conn.executemany("INSERT INTO trace_entry_0 (id, callstackId) VALUES (?, ?)", [(1, 1), (2, 2)])
    params = {"event_id": 2, "top_n": -1}
    payload = _json_stdout(
        runner.invoke(
            app,
            [
                "query",
                str(contract_db),
                "--template-use",
                name,
                "--params",
                json.dumps(params),
                "--device",
                "0",
                "--json",
            ],
        )
    )
    api_query = _focused_analyzer(contract_db).execute_query(name, params=params, device_id=0)
    assert {key: payload[key] for key in api_query} == api_query
    assert payload["semantics_version"] == 2
    assert payload["returned"] == 1
    row = payload["rows"][0]
    assert row["callstack"] == "[missing callstack]"
    assert row["category"] == "dynamic_live_at_event"
    assert (row["size_bytes"], row["requested_bytes"], row["block_count"]) == (2560, 2500, 2)
    assert row["percent_of_active_blocks"] == 100


def test_json_error_contract_keeps_text_errors_on_stdout(contract_db: Path) -> None:
    text = runner.invoke(app, ["query", str(contract_db), "--template-info", "does_not_exist"])
    assert text.exit_code == 1
    assert "Template 'does_not_exist' not found" in text.stdout

    json_result = runner.invoke(app, ["query", str(contract_db), "--template-info", "does_not_exist", "--json"])
    assert json_result.exit_code == 1
    assert json_result.stdout == ""
    error = json.loads(json_result.stderr)["error"]
    assert error["code"] == "TEMPLATE_NOT_FOUND"
    assert "does_not_exist" in error["message"]


def test_capabilities_contract_matches_cli_and_api_semantics(analyzer: SnapshotAnalyzer) -> None:
    cli_result = runner.invoke(app, ["capabilities", "--json"])
    payload = _json_stdout(cli_result)
    api = analyzer.list_capabilities()
    assert payload["cli_version"] == api["cli_version"]
    assert payload["templates"] == api["templates"]
    assert "skills" not in payload and "skills" not in api
    assert {item["name"] for item in api["templates"]} >= {
        "leak_detection",
        "preexisting_live",
        "freed_block_lifetime",
    }


def test_overview_contract_matches_cli_and_api_semantics(contract_db: Path) -> None:
    cli_result = runner.invoke(app, ["overview", str(contract_db), "--json"])
    payload = _json_stdout(cli_result)
    api = _focused_analyzer(contract_db).get_database_overview()
    assert payload["db_path"] == api["db_path"]
    assert payload["devices"] == api["devices"]
    assert payload["import_metadata"] == api["import_metadata"]
    assert payload["focus_source"] == "explicit"


@pytest.mark.parametrize("name", ["preexisting_live", "active_memory_callstack_at_event"])
def test_capabilities_template_matches_template_info_json(analyzer: SnapshotAnalyzer, name: str) -> None:
    capabilities = _json_stdout(runner.invoke(app, ["capabilities", "--json"]))
    info = _json_stdout(runner.invoke(app, ["query", "--template-info", name, "--json"]))
    entry = next(item for item in capabilities["templates"] if item["name"] == name)
    shared = {key: info[key] for key in entry}
    assert shared == entry
    assert analyzer.get_template_info(name) == entry
    assert next(item for item in analyzer.list_capabilities()["templates"] if item["name"] == name) == entry
    if name == "active_memory_callstack_at_event":
        assert entry["semantics_version"] == 2
        callstack = next(col for col in entry["output_schema"] if col["column"] == "callstack")
        assert "empty strings, NULL text or IDs" in " ".join(callstack["interpretation_limits"])


@pytest.mark.parametrize("use_manifest", [False, True])
def test_dataset_focus_overview_query_contract(tmp_path: Path, use_manifest: bool) -> None:
    root = make_dataset(tmp_path / "dataset")
    path = root / "manifest.json" if use_manifest else root
    with SnapshotAnalyzer() as analyzer:
        state = analyzer.set_focus(str(path), 2)
        focus = _json_stdout(runner.invoke(app, ["focus", str(path), "--device", "2", "--json"]))
        assert {key: focus[key] for key in _focus_payload(state)} == _focus_payload(state)
        overview = _json_stdout(runner.invoke(app, ["overview", str(path), "--json"]))
        api_overview = analyzer.get_database_overview()
        assert {key: overview[key] for key in api_overview} == api_overview
        metadata_result = runner.invoke(app, ["metadata", str(path), "--json"])
        assert metadata_result.exit_code == 0, metadata_result.output
        assert json.loads(metadata_result.stdout) == analyzer.get_database_metadata()
        for params, selector in [
            ({"id": 4}, []),
            ({}, ["--slice", "1"]),
            ({"min_id": 2, "max_id": 3}, []),
        ]:
            cli = _json_stdout(
                runner.invoke(
                    app,
                    [
                        "query",
                        str(path),
                        "--device",
                        "2",
                        "--template-use",
                        "event",
                        "--params",
                        json.dumps(params),
                        "--json",
                        *selector,
                    ],
                )
            )
            api = analyzer.execute_query("event", params, device_id=2, slice_index=1 if selector else None)
            assert {key: cli[key] for key in api} == api
            assert cli["scope"]["boundary_events_included"] is False
        error = runner.invoke(app, ["query", str(path), "--template-use", "event", "--params", '{"id": -1}', "--json"])
        assert error.exit_code == 1
        assert json.loads(error.stderr)["error"]["code"] == "INVALID_PARAMETER"
        global_peak = runner.invoke(app, ["query", str(path), "--template-use", "memory_peak", "--json"])
        assert global_peak.exit_code == 0, global_peak.output
        peak_payload = json.loads(global_peak.stdout)
        assert peak_payload["scope"]["slice_indices"] == [0, 1, 2]
        assert peak_payload["rows"][0]["peak_active"] == 8  # never synthetic 999
        manifest = root / "manifest.json"
        data = json.loads(manifest.read_text())
        data["status"] = "building"
        manifest.write_text(json.dumps(data))
        error = runner.invoke(app, ["focus", str(path), "--json"])
        assert error.exit_code == 1
        assert json.loads(error.stderr)["error"]["code"] == "DATABASE_SCHEMA_INVALID"
        with pytest.raises(ValueError, match="complete"):
            analyzer.set_focus(str(path))


def test_compatible_import_focus_metadata_query_contract(tmp_path: Path, monkeypatch) -> None:
    from test.core.test_msinsight_export import options as compatible_options

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    request = compatible_options(tmp_path, multiple=True)
    imported = _json_stdout(
        runner.invoke(
            app,
            [
                "import",
                str(request.snapshot_file),
                "--format",
                "msinsight",
                "--events-per-slice",
                "2",
                "--json",
            ],
        )
    )
    assert imported["format"] == "compatibility-v1"
    path = imported["dataset_path"]
    focused = _json_stdout(runner.invoke(app, ["focus", path, "--device", "1", "--json"]))
    with SnapshotAnalyzer(path, device_id=1) as analyzer:
        state = analyzer.get_focus()
        assert state.available_devices == focused["available_devices"] == [0, 1]
        assert state.callstack_layout == focused["callstack_layout"] == "v1"
        metadata_result = runner.invoke(app, ["metadata", path, "--json"])
        assert metadata_result.exit_code == 0, metadata_result.output
        metadata = json.loads(metadata_result.output)
        assert metadata == analyzer.get_database_metadata()
        assert metadata["status"] == "available"
        assert metadata["metadata"]["import_format_version"] == 1
        overview_result = runner.invoke(app, ["overview", path, "--json"])
        assert overview_result.exit_code == 0, overview_result.output
        overview = json.loads(overview_result.output)
        api_overview = analyzer.get_database_overview()
        assert {key: overview[key] for key in api_overview} == api_overview
        for params, selector in [
            ({"id": 3}, []),
            ({}, ["--slice", "1"]),
            ({"min_id": 2, "max_id": 3}, []),
        ]:
            cli = _json_stdout(
                runner.invoke(
                    app,
                    [
                        "query",
                        path,
                        "--device",
                        "1",
                        "--template-use",
                        "event",
                        "--params",
                        json.dumps(params),
                        "--json",
                        *selector,
                    ],
                )
            )
            api = analyzer.execute_query("event", params, slice_index=1 if selector else None)
            assert {key: cli[key] for key in api} == api
            assert cli["scope"]["boundary_events_included"] is False
        assert not hasattr(analyzer, "import_snapshot")


@pytest.mark.parametrize("template", ["event", "active_blocks_at_event", "active_memory_callstack_at_event"])
@pytest.mark.parametrize("frames", [False, True])
def test_dataset_point_event_sources_cli_api_report_contract(tmp_path: Path, template: str, frames: bool) -> None:
    from pt_snap_cli.core.analysis.report_service import ReportService
    from test.core.test_dataset_attribution import add_frames, case

    root = case(tmp_path)
    if frames:
        add_frames(root)
    params = {"id": 0, "stack_bytes": 0} if template == "event" else {"event_id": 8}
    if template == "active_memory_callstack_at_event":
        params.update({"top_n": 1, "stack_bytes": 0})
    cli = _json_stdout(
        runner.invoke(
            app,
            [
                "query",
                str(root),
                "--device",
                "2",
                "--template-use",
                template,
                "--params",
                json.dumps(params),
                "-n",
                "1",
                "--exact-total",
                "--json",
            ],
        )
    )
    with SnapshotAnalyzer(root, device_id=2) as analyzer:
        api = analyzer.execute_query(template, params, max_rows=1, exact_total=True)
        assert {key: cli[key] for key in api} == api
        assert cli["scope"]["source_coverage"]["range_complete"]
        if template != "event":
            assert cli["truncated"] and cli["scope"]["source_coverage"]["allocation_source_complete"]
        if template == "active_memory_callstack_at_event":
            report = ReportService()
            try:
                shared = report.event_attribution(8, root, 2, limit=1, stack_bytes=0)
                assert shared.rows[0] == api["rows"][0]
                assert shared.scope == api["scope"]
            finally:
                report.close()


def test_overview_error_contract_maps_four_domain_failures(tmp_path: Path) -> None:
    missing = runner.invoke(app, ["overview", str(tmp_path / "missing.db"), "--json"])
    missing_error = json.loads(missing.stderr)["error"]
    assert missing.exit_code == 1
    assert missing_error["code"] == "DATABASE_NOT_FOUND"
    with pytest.raises(FileNotFoundError):
        SnapshotAnalyzer().get_database_overview(str(tmp_path / "missing.db"))

    bad_db = tmp_path / "no-dictionary.db"
    conn = sqlite3.connect(str(bad_db))
    conn.execute("CREATE TABLE other_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    schema = runner.invoke(app, ["overview", str(bad_db), "--json"])
    schema_error = json.loads(schema.stderr)["error"]
    assert schema.exit_code == 1
    assert schema_error["code"] == "DATABASE_SCHEMA_INVALID"
    with pytest.raises(ValueError):
        SnapshotAnalyzer().get_database_overview(str(bad_db))

    focus_dir = tmp_path / ".pt-snap"
    focus_dir.mkdir()
    (focus_dir / "focus.json").write_text("not-json", encoding="utf-8")
    invalid = runner.invoke(app, ["overview", "--json"])
    invalid_error = json.loads(invalid.stderr)["error"]
    assert invalid.exit_code == 1
    assert invalid_error["code"] == "FOCUS_FILE_INVALID"
    with pytest.raises(ValueError):
        SnapshotAnalyzer().get_database_overview()

    (focus_dir / "focus.json").unlink()
    unconfigured = runner.invoke(app, ["overview", "--json"])
    unconfigured_error = json.loads(unconfigured.stderr)["error"]
    assert unconfigured.exit_code == 1
    assert unconfigured_error["code"] == "FOCUS_NOT_CONFIGURED"
    with pytest.raises(RuntimeError, match="No database configured"):
        SnapshotAnalyzer().get_database_overview()


def test_explicit_dataset_limits_and_failures_match_cli_api(tmp_path):
    from pt_snap_cli.api import QueryLimits

    root = make_dataset(tmp_path / "limits-contract", devices=(0,))
    limits = QueryLimits(100, 123456, 0)
    with SnapshotAnalyzer(root) as analyzer:
        api = analyzer.execute_query("event", query_limits=limits)
        with pytest.raises(QueryExecutionError, match="max_work_rows=1") as error:
            analyzer.execute_query("event", query_limits=QueryLimits(1))
    cli = runner.invoke(
        app,
        [
            "query",
            str(root),
            "--template-use",
            "event",
            "--max-work-rows",
            "100",
            "--max-work-bytes",
            "123456",
            "--max-scratch-db-bytes",
            "0",
            "--json",
        ],
    )
    assert cli.exit_code == 0, cli.output
    payload = json.loads(cli.stdout)
    assert payload["scope"] == api["scope"]
    assert payload["rows"] == api["rows"]
    failed = runner.invoke(
        app,
        [
            "query",
            str(root),
            "--template-use",
            "event",
            "--max-work-rows",
            "1",
            "--json",
        ],
    )
    assert failed.exit_code == 1 and failed.stdout == ""
    assert json.loads(failed.stderr)["error"]["message"] == str(error.value)


@pytest.mark.parametrize("layout", ("v1", "v2"))
@pytest.mark.parametrize("source", ("dataset", "standalone"))
def test_zero_rank_completeness_cli_api_contract(tmp_path, layout, source):
    from test.core.test_dataset_zero_rank import zero_rank_pair

    dataset, single = zero_rank_pair(tmp_path, layout, "mixed")
    path = dataset if source == "dataset" else single
    params = {"event_id": 1, "top_n": 0, "include_static": False}
    with SnapshotAnalyzer(path) as analyzer:
        for exact in (False, True):
            api = analyzer.execute_query("active_memory_callstack_at_event", params, exact_total=exact)
            cli = _json_stdout(
                runner.invoke(
                    app,
                    [
                        "query",
                        str(path),
                        "--template-use",
                        "active_memory_callstack_at_event",
                        "--params",
                        json.dumps(params),
                        "--json",
                        *(["--exact-total"] if exact else []),
                    ],
                )
            )
            assert {key: cli[key] for key in api} == api
            assert api["rows"] == [] and api["has_more"] and api["truncated"]
            assert api["total_is_exact"] is exact
            assert api["total"] == int(exact)
