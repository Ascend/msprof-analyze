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

"""JSON-mode CLI contract tests for issue #138."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from click import unstyle
from typer.testing import CliRunner

from pt_snap_cli.cli import app
from pt_snap_cli.config import ENV_DB_PATH
from pt_snap_cli.core.common.json_codec import JSON_SCHEMA_VERSION
from pt_snap_cli.query.config import QueryTemplate
from pt_snap_cli.query.registry import QueryRegistry, register_query

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures" / "snapshots"


def create_sample_db(db_path: Path) -> Path:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY, action TEXT, device_id INTEGER, size INTEGER, timestamp REAL
        )
        """)
    conn.execute("INSERT INTO trace_entry_0 (action, device_id, size, timestamp) VALUES ('malloc', 0, 1024, 1.0)")
    conn.commit()
    conn.close()
    return db_path


def create_contract_db(db_path: Path) -> Path:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    for device_id, rows in {
        0: [
            (1, 0x1000, 2048, 2000, 1, 1, -1),
            (2, 0x2000, 512, 500, 0, 2, 3),
        ],
        1: [(3, 0x3000, 4096, 4000, 1, 4, None)],
    }.items():
        conn.execute(f"""
            CREATE TABLE block_{device_id} (
                id INTEGER PRIMARY KEY, address INTEGER, size INTEGER,
                requestedSize INTEGER, state INTEGER, allocEventId INTEGER, freeEventId INTEGER
            )
            """)
        conn.execute(f"""
            CREATE TABLE trace_entry_{device_id} (
                id INTEGER PRIMARY KEY, action INTEGER, address INTEGER, size INTEGER,
                stream INTEGER, allocated INTEGER, active INTEGER, reserved INTEGER, callstack TEXT
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


def create_peak_report_db(db_path: Path) -> Path:
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY, action INTEGER, address INTEGER, size INTEGER,
            stream INTEGER, allocated INTEGER, active INTEGER, reserved INTEGER, callstackId INTEGER
        )
        """)
    conn.execute("CREATE TABLE callstack (id INTEGER PRIMARY KEY, callstack TEXT)")
    conn.execute("""
        CREATE TABLE block_0 (
            id INTEGER PRIMARY KEY, address INTEGER, size INTEGER, requestedSize INTEGER,
            state INTEGER, allocEventId INTEGER, freeEventId INTEGER
        )
        """)
    conn.executemany(
        "INSERT INTO callstack (id, callstack) VALUES (?, ?)",
        [(0, "train.py:10"), (1, "block.py:20"), (2, "free.py:30"), (3, "after.py:40")],
    )
    conn.executemany(
        """
        INSERT INTO trace_entry_0
          (id, action, address, size, stream, allocated, active, reserved, callstackId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 2, 0x1000, 1024, 0, 1024, 1024, 4096, 0),
            (2, 2, 0x2000, 2048, 0, 3072, 3072, 4096, 1),
            (3, 3, 0x2000, 2048, 0, 1024, 1024, 8192, 2),
            (4, 2, 0x4000, 4096, 0, 5120, 5120, 8192, 3),
        ],
    )
    conn.executemany(
        """
        INSERT INTO block_0
          (id, address, size, requestedSize, state, allocEventId, freeEventId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (-10, 0xA000, 8192, 8000, 1, -1, -1),
            (1, 0x1000, 1024, 1000, 1, 1, -1),
            (2, 0x2000, 2048, 2000, 0, 2, 3),
            (4, 0x4000, 4096, 4000, 1, 4, -1),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def _isolate_cli_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    with patch.object(Path, "home", return_value=tmp_path):
        QueryRegistry.reset()
        yield
        QueryRegistry.reset()


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    return create_sample_db(tmp_path / "sample.db")


@pytest.fixture
def contract_style_db(tmp_path: Path) -> Path:
    return create_contract_db(tmp_path / "contract.db")


@pytest.fixture
def report_db(tmp_path: Path) -> Path:
    return create_peak_report_db(tmp_path / "report.db")


def _assert_clean_json_success(result) -> dict[str, object]:
    assert result.exit_code == 0, result.stderr or result.stdout
    assert result.stdout
    assert "\x1b" not in result.stdout
    assert "Agents: prefer --json" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == JSON_SCHEMA_VERSION
    assert payload["ok"] is True
    return payload


def _assert_json_error(result, code: str) -> dict[str, object]:
    assert result.exit_code == 1
    assert unstyle(result.stdout) == ""
    assert "\x1b" not in result.stderr
    payload = json.loads(result.stderr)
    assert payload["schema_version"] == JSON_SCHEMA_VERSION
    assert payload["ok"] is False
    error = payload["error"]
    assert error["code"] == code
    assert error["message"]
    assert "hint" in error
    return payload


def test_focus_read_set_device_global_and_session_json(tmp_path: Path, sample_db: Path) -> None:
    empty = runner.invoke(app, ["focus", "--json"])
    empty_payload = _assert_clean_json_success(empty)
    assert empty_payload["configured"] is False
    assert empty_payload["action"] == "read"
    assert empty_payload["db_path"] is None

    set_project = runner.invoke(app, ["focus", str(sample_db), "--device", "0", "--json"])
    project_payload = _assert_clean_json_success(set_project)
    assert project_payload["action"] == "set_project"
    assert project_payload["db_path"] == str(sample_db.resolve())
    assert project_payload["device_id"] == 0
    assert project_payload["focus_source"] == "project"
    assert project_payload["available_devices"] == [0]

    read_back = runner.invoke(app, ["focus", "--json"])
    read_payload = _assert_clean_json_success(read_back)
    assert read_payload["configured"] is True
    assert read_payload["device_id"] == 0

    set_device = runner.invoke(app, ["focus", "--device", "0", "--json"])
    device_payload = _assert_clean_json_success(set_device)
    assert device_payload["action"] == "set_device"
    assert device_payload["device_id"] == 0

    set_global = runner.invoke(app, ["focus", str(sample_db), "--global", "--json"])
    global_payload = _assert_clean_json_success(set_global)
    assert global_payload["action"] == "set_global"
    assert global_payload["focus_source"] == "global"

    session = runner.invoke(app, ["focus", str(sample_db), "--session", "--json"])
    session_payload = _assert_clean_json_success(session)
    assert session_payload["action"] == "validate_session"
    assert session_payload["session_applied"] is False
    assert "export" not in session.stdout.splitlines()[0]
    env = session_payload["env"]
    assert env["name"] == ENV_DB_PATH
    assert env["value"] == str(sample_db.resolve())
    assert env["export"].startswith(f"export {ENV_DB_PATH}=")
    assert f"export {ENV_DB_PATH}=" not in session.stdout.split("{", 1)[0]

    session_read = runner.invoke(app, ["focus", "--session", "--json"])
    session_read_payload = _assert_clean_json_success(session_read)
    assert session_read_payload["action"] == "read"
    assert session_read_payload["configured"] is True

    global_read = runner.invoke(app, ["focus", "--global", "--json"])
    global_read_payload = _assert_clean_json_success(global_read)
    assert global_read_payload["action"] == "read"


def test_focus_json_errors_use_stderr(tmp_path: Path, sample_db: Path) -> None:
    missing = runner.invoke(app, ["focus", str(tmp_path / "missing.db"), "--json"])
    _assert_json_error(missing, "DATABASE_NOT_FOUND")

    conflict = runner.invoke(app, ["focus", str(sample_db), "--session", "--global", "--json"])
    _assert_json_error(conflict, "INVALID_PARAMETER")

    device_conflict = runner.invoke(app, ["focus", str(sample_db), "--session", "--device", "0", "--json"])
    _assert_json_error(device_conflict, "INVALID_PARAMETER")

    focus_dir = tmp_path / ".pt-snap"
    focus_dir.mkdir()
    (focus_dir / "focus.json").write_text("not-json", encoding="utf-8")
    invalid = runner.invoke(app, ["focus", "--json"])
    _assert_json_error(invalid, "FOCUS_FILE_INVALID")


def test_config_json_show_path_and_clear(tmp_path: Path, sample_db: Path) -> None:
    empty = runner.invoke(app, ["config", "--json"])
    empty_payload = _assert_clean_json_success(empty)
    assert empty_payload["action"] == "show"
    assert empty_payload["config"] == {}

    runner.invoke(app, ["focus", str(sample_db), "--global"])
    shown = runner.invoke(app, ["config", "--json"])
    shown_payload = _assert_clean_json_success(shown)
    assert shown_payload["config"]["db_path"] == str(sample_db.resolve())

    path = runner.invoke(app, ["config", "--path", "--json"])
    path_payload = _assert_clean_json_success(path)
    assert path_payload["action"] == "path"
    assert path_payload["path"].endswith("config.json")

    cleared = runner.invoke(app, ["config", "--clear", "--json"])
    cleared_payload = _assert_clean_json_success(cleared)
    assert cleared_payload["action"] == "clear"
    assert cleared_payload["cleared"] is True
    assert json.loads(Path(cleared_payload["path"]).read_text()) == {}


def test_query_list_info_execute_empty_and_limit_json(sample_db: Path, contract_style_db: Path) -> None:
    listed = runner.invoke(app, ["query", "--list", "--json"])
    listed_payload = _assert_clean_json_success(listed)
    names = {item["name"] for item in listed_payload["templates"]}
    assert "leak_detection" in names
    assert listed_payload["category"] is None

    basic = runner.invoke(app, ["query", "--list", "--category", "basic", "--json"])
    basic_payload = _assert_clean_json_success(basic)
    assert basic_payload["category"] == "basic"
    assert {item["category"] for item in basic_payload["templates"]} == {"basic"}

    info = runner.invoke(app, ["query", "--template-info", "leak_detection", "--json"])
    info_payload = _assert_clean_json_success(info)
    assert info_payload["template"] == "leak_detection"
    assert info_payload["name"] == "leak_detection"
    assert info_payload["semantics_version"] == 1
    assert info_payload["interpretation_limits"]
    assert "min_size" in info_payload["parameters"]
    assert "device_id" not in info_payload["parameters"]
    columns = {column["column"]: column for column in info_payload["output_schema"]}
    assert columns["size"]["units"] == "bytes"
    assert columns["address"]["units"] == "address"

    register_query(QueryTemplate(name="empty_rows", query="SELECT 1 AS x WHERE 0"))
    empty = runner.invoke(
        app,
        ["query", str(sample_db), "--template-use", "empty_rows", "--json"],
    )
    empty_payload = _assert_clean_json_success(empty)
    assert empty_payload["total"] == 0
    assert empty_payload["returned"] == 0
    assert empty_payload["rows"] == []
    assert empty_payload["template"] == "empty_rows"
    assert empty_payload["db_path"] == str(sample_db.resolve())

    limited = runner.invoke(
        app,
        [
            "query",
            str(contract_style_db),
            "--template-use",
            "leak_detection",
            "--params",
            '{"min_size": 0}',
            "--device",
            "0",
            "-n",
            "1",
            "--json",
        ],
    )
    limited_payload = _assert_clean_json_success(limited)
    assert limited_payload["returned"] == 1
    assert limited_payload["total"] == 1
    # Device 0 has a single leak candidate, so -n 1 is a complete page.
    assert limited_payload["has_more"] is False
    assert limited_payload["truncated"] is False
    assert limited_payload["total_is_exact"] is True
    assert limited_payload["timeout_s"] is None
    assert limited_payload["effective_params"]["min_size"] == 0
    assert limited_payload["effective_params"]["limit"] == 1
    assert limited_payload["device_id"] == 0


def test_query_json_error_paths(tmp_path: Path, sample_db: Path) -> None:
    missing_template = runner.invoke(app, ["query", "--template-info", "does_not_exist", "--json"])
    _assert_json_error(missing_template, "TEMPLATE_NOT_FOUND")

    no_focus = runner.invoke(app, ["query", "--template-use", "leak_detection", "--json"])
    _assert_json_error(no_focus, "FOCUS_NOT_CONFIGURED")

    missing_db = runner.invoke(
        app,
        ["query", str(tmp_path / "missing.db"), "--template-use", "leak_detection", "--json"],
    )
    _assert_json_error(missing_db, "DATABASE_NOT_FOUND")

    bad_params = runner.invoke(
        app,
        [
            "query",
            str(sample_db),
            "--template-use",
            "leak_detection",
            "--params",
            '{"min_sze": 1}',
            "--json",
        ],
    )
    _assert_json_error(bad_params, "INVALID_PARAMETER")

    bad_device = runner.invoke(
        app,
        [
            "query",
            str(sample_db),
            "--template-use",
            "leak_detection",
            "--device",
            "99",
            "--json",
        ],
    )
    _assert_json_error(bad_device, "DEVICE_NOT_FOUND")


def test_query_json_error_for_database_without_devices(tmp_path: Path) -> None:
    database = tmp_path / "no-devices.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    connection.commit()
    connection.close()

    result = runner.invoke(
        app,
        ["query", str(database), "--template-use", "leak_detection", "--json"],
    )

    _assert_json_error(result, "DEVICE_NOT_FOUND")


def test_import_json_fresh_and_reuse(tmp_path: Path) -> None:
    snapshot = tmp_path / "sample.pkl"
    shutil.copy(FIXTURES / "snapshot_with_empty_cache.pkl", snapshot)

    first = runner.invoke(app, ["import", str(snapshot), "--no-focus", "--json"])
    first_payload = _assert_clean_json_success(first)
    assert first_payload["reused"] is False
    assert first_payload["db_path"].endswith("sample.pkl.db")
    assert first_payload["focus_state"] is None
    assert first_payload["metadata"]["source_name"] == "sample.pkl"

    second = runner.invoke(app, ["import", str(snapshot), "--no-focus", "--json"])
    second_payload = _assert_clean_json_success(second)
    assert second_payload["reused"] is True
    assert second_payload["cache_miss_reason"] is None
    assert second_payload["db_path"] == first_payload["db_path"]

    focused = runner.invoke(app, ["import", str(snapshot), "--json"])
    focused_payload = _assert_clean_json_success(focused)
    assert focused_payload["reused"] is True
    assert focused_payload["focus_state"] is not None
    assert focused_payload["focus_source"] == "project"
    assert focused_payload["focus_state"]["focus_source"] == "project"
    assert focused_payload["focus_state"]["db_path"] == focused_payload["db_path"]


def test_import_json_error_for_missing_snapshot(tmp_path: Path) -> None:
    missing = runner.invoke(app, ["import", str(tmp_path / "missing.pkl"), "--no-focus", "--json"])
    _assert_json_error(missing, "SNAPSHOT_INVALID")


def test_effective_params_limit_matches_trailing_sql_not_inner_top_n() -> None:
    from pt_snap_cli.cli import _effective_query_params
    from pt_snap_cli.query.config import QueryTemplate
    from pt_snap_cli.query.executor import _TRAILING_LIMIT_RE, QueryExecutor
    from pt_snap_cli.query.registry import get_query

    template = get_query("active_memory_callstack_at_event")
    assert template is not None
    body = template.query_variants["v1"]
    clone = QueryTemplate(
        name=template.name,
        query=body,
        parameters=template.parameters,
    )
    executor = QueryExecutor.__new__(QueryExecutor)
    executor._env = QueryExecutor(context=None)._env
    executor._compiled_cache = {}
    sql = executor.render(clone, {"event_id": 1}, device_id=0, max_rows=50)
    match = _TRAILING_LIMIT_RE.search(sql)
    assert match is not None
    trailing = int(match.group("limit"))
    assert trailing == 50

    wide = _effective_query_params(
        "active_memory_callstack_at_event",
        {"event_id": 1},
        max_rows=50,
    )
    assert wide["top_n"] == 20
    assert wide["limit"] == trailing

    tight = _effective_query_params(
        "active_memory_callstack_at_event",
        {"event_id": 1},
        max_rows=5,
    )
    assert tight["top_n"] == 20
    assert tight["limit"] == 5


def test_argv_requests_json_is_flag_not_option_value() -> None:
    from pt_snap_cli.cli import _argv_requests_json

    assert _argv_requests_json(["query", "-n", "abc", "--json"]) is True
    assert _argv_requests_json(["query", "--json"]) is True
    assert _argv_requests_json(["query", "--list", "--json"]) is True
    assert _argv_requests_json(["query", "--params", "--json"]) is False
    assert _argv_requests_json(["query", "--", "--json"]) is False
    assert _argv_requests_json(["query", "-n", "abc"]) is False
    assert _argv_requests_json(["query", "--template-use=missing", "--json"]) is True
    assert _argv_requests_json(["query", "-n", "-1", "--json"]) is True
    assert _argv_requests_json(["query", "--exact-total", "--json"]) is True


def test_safe_call_json_usage_error_uses_stderr_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from unittest.mock import patch

    from pt_snap_cli.cli import _safe_call

    with patch("sys.argv", ["pt-snap", "query", "-n", "abc", "--json"]):
        code = _safe_call()
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["schema_version"] == JSON_SCHEMA_VERSION
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_PARAMETER"
    # Parser versions use either "int" or "integer" in this diagnostic.
    assert "-n" in payload["error"]["message"]
    assert any(word in payload["error"]["message"] for word in ("int", "integer"))
    assert "hint" in payload["error"]


def test_safe_call_json_abort_uses_stderr_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from unittest.mock import patch

    from typer.exceptions import Abort

    from pt_snap_cli.cli import _safe_call

    with (
        patch("sys.argv", ["pt-snap", "focus", "--json"]),
        patch("pt_snap_cli.cli.app", side_effect=Abort()),
    ):
        code = _safe_call()
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["schema_version"] == JSON_SCHEMA_VERSION
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ERROR"
    assert payload["error"]["message"] == "Aborted!"
    assert "hint" in payload["error"]


def test_safe_call_json_sigint_uses_returned_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from unittest.mock import patch

    from pt_snap_cli.cli import _safe_call

    with (
        patch("sys.argv", ["pt-snap", "focus", "--json"]),
        patch("pt_snap_cli.cli.app", return_value=130),
    ):
        code = _safe_call()
    captured = capsys.readouterr()
    assert code == 130
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ERROR"
    assert payload["error"]["message"] == "Aborted!"


def test_safe_call_json_domain_error_returns_nonzero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from unittest.mock import patch

    from pt_snap_cli.cli import _safe_call

    with patch("sys.argv", ["pt-snap", "query", "--template-info", "does_not_exist", "--json"]):
        code = _safe_call()
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["schema_version"] == JSON_SCHEMA_VERSION
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TEMPLATE_NOT_FOUND"


def test_safe_call_text_domain_error_returns_nonzero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from unittest.mock import patch

    from pt_snap_cli.cli import _safe_call

    with patch("sys.argv", ["pt-snap", "query", "--template-info", "does_not_exist"]):
        code = _safe_call()
    captured = capsys.readouterr()
    assert code == 1
    assert "not found" in captured.out.lower()
    assert captured.err == ""


def test_split_json_is_independent_of_format(tmp_path: Path) -> None:
    source = FIXTURES / "snapshot_expandable.pkl"
    pickle_out = tmp_path / "pickle-split"
    json_out = tmp_path / "json-split"

    listed = runner.invoke(
        app,
        [
            "split",
            str(source),
            "--device",
            "0",
            "--slices",
            "1",
            "--output",
            str(pickle_out),
            "--json",
        ],
    )
    pickle_payload = _assert_clean_json_success(listed)
    assert pickle_payload["format"] == "pickle"
    assert pickle_payload["devices"] == [0]
    assert len(pickle_payload["files"]) == 1
    assert pickle_payload["files"][0].endswith(".pkl")
    assert pickle_out.exists()

    formatted = runner.invoke(
        app,
        [
            "split",
            str(source),
            "--device",
            "0",
            "--slices",
            "1",
            "--format",
            "json",
            "--output",
            str(json_out),
            "--json",
        ],
    )
    format_payload = _assert_clean_json_success(formatted)
    assert format_payload["format"] == "json"
    assert format_payload["files"][0].endswith(".json")
    assert json_out.exists()


def test_split_json_error_keeps_stdout_empty(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "split",
            str(tmp_path / "missing.pkl"),
            "--slices",
            "1",
            "--output",
            str(tmp_path / "out"),
            "--json",
        ],
    )
    _assert_json_error(result, "SPLIT_FAILED")


def test_metadata_and_report_json_success_fields_stay_compatible(tmp_path: Path, report_db: Path) -> None:
    snapshot = tmp_path / "sample.pkl"
    shutil.copy(FIXTURES / "snapshot_with_empty_cache.pkl", snapshot)
    runner.invoke(app, ["import", str(snapshot), "--no-focus"])

    metadata = runner.invoke(app, ["metadata", str(tmp_path / "sample.pkl.db"), "--json"])
    assert metadata.exit_code == 0
    payload = json.loads(metadata.stdout)
    assert payload["status"] == "available"
    assert "schema_version" not in payload
    assert "ok" not in payload

    report = runner.invoke(app, ["report", "peak-memory", str(report_db), "--json"])
    assert report.exit_code == 0
    report_payload = json.loads(report.stdout)
    assert report_payload["metric"] == "active"
    assert "device_id" in report_payload
    assert "callstack_groups" in report_payload

    missing = runner.invoke(app, ["metadata", "--json"])
    _assert_json_error(missing, "FOCUS_NOT_CONFIGURED")

    missing_report = runner.invoke(app, ["report", "peak-memory", "--json"])
    _assert_json_error(missing_report, "FOCUS_NOT_CONFIGURED")


def test_text_mode_errors_still_use_stdout(tmp_path: Path) -> None:
    result = runner.invoke(app, ["query", "--template-info", "does_not_exist"])
    assert result.exit_code == 1
    assert "Error: Template 'does_not_exist' not found" in result.stdout
    assert result.stderr == "" or "TEMPLATE_NOT_FOUND" not in result.stderr


def test_capabilities_json_uses_success_envelope() -> None:
    result = runner.invoke(app, ["capabilities", "--json"])
    payload = _assert_clean_json_success(result)
    assert "cli_version" in payload
    names = {item["name"] for item in payload["templates"]}
    assert {"leak_detection", "preexisting_live", "freed_block_lifetime"} <= names
    leak = next(item for item in payload["templates"] if item["name"] == "leak_detection")
    assert leak["semantics_version"] == 1
    assert "min_size" in leak["parameters"]
    assert "skills" not in payload


def test_overview_json_uses_success_envelope(sample_db: Path) -> None:
    result = runner.invoke(app, ["overview", str(sample_db), "--json"])
    payload = _assert_clean_json_success(result)
    assert payload["db_path"] == str(sample_db.resolve())
    assert payload["focus_source"] == "explicit"
    assert payload["devices"] == [{"device_id": 0, "first_event_id": 1, "last_event_id": 1}]
    assert payload["import_metadata"]["status"] == "unavailable"


def test_overview_json_error_uses_stderr_envelope() -> None:
    result = runner.invoke(app, ["overview", "--json"])
    _assert_json_error(result, "FOCUS_NOT_CONFIGURED")


def test_overview_json_missing_database_uses_envelope(tmp_path: Path) -> None:
    result = runner.invoke(app, ["overview", str(tmp_path / "missing.db"), "--json"])
    _assert_json_error(result, "DATABASE_NOT_FOUND")


def test_overview_json_invalid_schema_uses_envelope(tmp_path: Path) -> None:
    db_path = tmp_path / "no-dictionary.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE other_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["overview", str(db_path), "--json"])
    _assert_json_error(result, "DATABASE_SCHEMA_INVALID")


def test_overview_json_missing_id_column_uses_envelope(tmp_path: Path) -> None:
    db_path = tmp_path / "no-id.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
    conn.execute("CREATE TABLE trace_entry_0 (action INTEGER)")
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["overview", str(db_path), "--json"])
    _assert_json_error(result, "DATABASE_SCHEMA_INVALID")


def test_overview_json_invalid_focus_file_uses_envelope(tmp_path: Path) -> None:
    focus_dir = tmp_path / ".pt-snap"
    focus_dir.mkdir()
    (focus_dir / "focus.json").write_text("not-json", encoding="utf-8")
    result = runner.invoke(app, ["overview", "--json"])
    _assert_json_error(result, "FOCUS_FILE_INVALID")
