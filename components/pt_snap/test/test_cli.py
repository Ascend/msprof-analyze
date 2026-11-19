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

"""Tests for CLI."""

import json
import shlex
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from click import unstyle
from typer.testing import CliRunner

from pt_snap_cli.cli import app
from pt_snap_cli.query.config import QueryTemplate
from pt_snap_cli.query.registry import QueryRegistry, register_query

runner = CliRunner()


def create_sample_db(db_path: Path, size: int = 1024) -> Path:
    """Create a sample SQLite database for testing."""
    conn = sqlite3.connect(str(db_path))

    # Create dictionary table
    conn.execute("""
        CREATE TABLE dictionary (
            `table` TEXT,
            `column` TEXT,
            `key` TEXT,
            `value` TEXT
        )
    """)

    # Create trace_entry_0 table
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY,
            action TEXT,
            device_id INTEGER,
            size INTEGER,
            timestamp REAL
        )
    """)

    # Create blocks_0 table
    conn.execute("""
        CREATE TABLE blocks_0 (
            id INTEGER PRIMARY KEY,
            device_id INTEGER,
            address INTEGER,
            size INTEGER,
            start_time REAL,
            end_time REAL
        )
    """)

    # Insert sample data
    conn.execute(
        """
        INSERT INTO trace_entry_0 (action, device_id, size, timestamp)
        VALUES ('malloc', 0, ?, 1.0)
    """,
        (size,),
    )

    conn.execute(
        """
        INSERT INTO blocks_0 (device_id, address, size, start_time, end_time)
        VALUES (0, 1000, ?, 1.0, 2.0)
    """,
        (size,),
    )

    conn.commit()
    conn.close()
    return db_path


def create_peak_report_db(db_path: Path) -> Path:
    """Create a memory snapshot database for peak report CLI tests."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE dictionary (
            `table` TEXT,
            `column` TEXT,
            `key` TEXT,
            `value` TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE trace_entry_0 (
            id INTEGER PRIMARY KEY,
            action INTEGER,
            address INTEGER,
            size INTEGER,
            stream INTEGER,
            allocated INTEGER,
            active INTEGER,
            reserved INTEGER,
            callstackId INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE callstack (
            id INTEGER PRIMARY KEY,
            callstack TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE block_0 (
            id INTEGER PRIMARY KEY,
            address INTEGER,
            size INTEGER,
            requestedSize INTEGER,
            state INTEGER,
            allocEventId INTEGER,
            freeEventId INTEGER
        )
    """)
    conn.executemany(
        "INSERT INTO callstack (id, callstack) VALUES (?, ?)",
        [
            (0, "train.py:10"),
            (1, "block.py:20"),
            (2, "free.py:30"),
            (3, "after.py:40"),
        ],
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


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    """Create a sample SQLite database for testing."""
    return create_sample_db(tmp_path / "sample.db")


@pytest.fixture
def config_with_db(tmp_path: Path, sample_db: Path) -> None:
    """Set up config with sample database."""
    config_dir = tmp_path / ".config" / "pt-snap-cli"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"db_path": str(sample_db)}))


@pytest.fixture(autouse=True)
def mock_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Mock Path.home to use tmp_path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    with patch.object(Path, "home", return_value=tmp_path):
        yield


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset query registry before each test."""
    QueryRegistry.reset()
    yield
    QueryRegistry.reset()


class TestCLI:
    """Test CLI commands."""

    def test_version_flag(self) -> None:
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "msprof-analyze pt-snap version" in result.stdout

    def test_help_flag(self) -> None:
        """Test --help flag."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "PyTorch Memory Snapshot Analysis Tool" in result.stdout
        assert "capabilities" in result.stdout
        assert "overview" in result.stdout
        assert "skill" not in result.stdout.lower()

    def test_short_help_flag(self) -> None:
        """Test -h flag."""
        result = runner.invoke(app, ["-h"])
        assert result.exit_code == 0
        assert "PyTorch Memory Snapshot Analysis Tool" in result.stdout

    def test_subcommand_short_help_flag(self) -> None:
        """Test -h flag for subcommands."""
        result = runner.invoke(app, ["query", "-h"])
        assert result.exit_code == 0
        assert "Execute queries on the memory snapshot database" in result.stdout

    def test_split_help_contract(self) -> None:
        result = runner.invoke(app, ["split", "--help"])
        assert result.exit_code == 0
        output = unstyle(result.stdout)
        normalized_help = " ".join(output.split())
        assert "SNAPSHOT_PATH" in output
        assert "SNAPSHOT_FILE" not in output
        assert "--format {pickle,json}" in normalized_help
        assert "[default: pickle]" in output
        for option in ("--device", "--slices", "--max-entries", "--output"):
            assert option in output

    def test_split_output_is_required(self) -> None:
        result = runner.invoke(app, ["split", "snapshot.pkl", "--slices", "1"])
        assert result.exit_code != 0
        assert "--output" in unstyle(result.stderr)

    def test_split_error_uses_domain_presentation_without_traceback(self, tmp_path: Path) -> None:
        source = tmp_path / "missing.pkl"
        result = runner.invoke(
            app,
            ["split", str(source), "--slices", "2", "--output", str(tmp_path / "out")],
        )
        assert result.exit_code == 1
        assert f"Split path failed for '{source}'" in result.stdout
        assert "Traceback" not in result.stdout

    def test_split_format_metavar_does_not_bypass_domain_validation(self, tmp_path: Path) -> None:
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_expandable.pkl"
        result = runner.invoke(
            app,
            [
                "split",
                str(source),
                "--slices",
                "1",
                "--format",
                "yaml",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 1
        assert f"Split argument failed for '{source}'" in result.stdout
        assert "format must be exactly 'pickle' or 'json'" in result.stdout

    def test_split_does_not_read_or_write_focus(self, tmp_path: Path) -> None:
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_expandable.pkl"
        with patch("pt_snap_cli.cli._focus_service", side_effect=AssertionError("focus read")):
            result = runner.invoke(
                app,
                [
                    "split",
                    str(source),
                    "--device",
                    "0",
                    "--slices",
                    "1",
                    "--output",
                    str(tmp_path / "out"),
                ],
            )
        assert result.exit_code == 0
        assert "Files: 1" in result.stdout

    def test_split_cli_all_devices_max_entries_json(self, tmp_path: Path) -> None:
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_with_multi_devices.pkl"
        output = tmp_path / "json-split"

        result = runner.invoke(
            app,
            [
                "split",
                str(source),
                "--max-entries",
                "5000",
                "--format",
                "json",
                "--output",
                str(output),
            ],
        )

        assert result.exit_code == 0
        assert "Devices: 0, 1" in result.stdout
        assert len(list(output.glob("*.json"))) == 4

    def test_focus_database_not_found(self, tmp_path: Path) -> None:
        """Test 'focus' command with non-existent database."""
        non_existent = tmp_path / "not_found.db"
        result = runner.invoke(app, ["focus", str(non_existent)])
        assert result.exit_code == 1
        assert "Error" in result.stdout


class TestQueryCommandErrors:
    """Test query command error scenarios."""

    def test_query_template_info_not_found(self, sample_db: Path) -> None:
        """Test 'query --template-info' with non-existent template."""
        result = runner.invoke(app, ["query", str(sample_db), "--template-info", "nonexistent"])
        assert result.exit_code == 1
        assert "Error: Template 'nonexistent' not found" in result.stdout

    def test_query_without_template_use(self, sample_db: Path) -> None:
        """Test 'query' command without --template-use raises error."""
        result = runner.invoke(app, ["query", str(sample_db)])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower()
        assert "--template-use" in result.stdout

    def test_query_database_not_found(self, tmp_path: Path) -> None:
        """Test 'query' command with non-existent database."""
        non_existent = tmp_path / "not_found.db"
        result = runner.invoke(app, ["query", str(non_existent), "--template-use", "test"])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower()

    def test_query_with_config(self, tmp_path: Path, sample_db: Path) -> None:
        """Test 'query' command falls back to legacy global config."""
        config_dir = tmp_path / ".config" / "pt-snap-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"db_path": str(sample_db)}))

        register_query(QueryTemplate(name="test_query", description="Test", query="SELECT 1"))

        result = runner.invoke(app, ["query", "--template-use", "test_query"])
        assert result.exit_code == 0
        assert "No results found" in result.stdout or "Found" in result.stdout

    def test_query_configured_db_not_found(self, tmp_path: Path) -> None:
        """Test 'query' command when configured database doesn't exist."""
        config_dir = tmp_path / ".config" / "pt-snap-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"db_path": "/nonexistent/path.db"}))

        register_query(QueryTemplate(name="test", description="Test", query="SELECT 1"))

        result = runner.invoke(app, ["query", "--template-use", "test"])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower()
        assert "database" in result.stdout.lower()


class TestFocusCommandErrors:
    """Test focus command error scenarios."""

    def test_focus_database_invalid(self, tmp_path: Path) -> None:
        """Test 'focus' command with invalid database."""
        invalid_db = tmp_path / "invalid.db"
        invalid_db.write_text("not a database")

        result = runner.invoke(app, ["focus", str(invalid_db)])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower()

    def test_focus_database_exception_handling(self, tmp_path: Path) -> None:
        """Test 'focus' command exception handling."""
        bad_file = tmp_path / "bad.db"
        bad_file.write_text("corrupted content")

        result = runner.invoke(app, ["focus", str(bad_file)])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower()


class TestQueryTemplateInfo:
    """Test query --template-info command in detail."""

    def test_template_info_with_complex_parameters(self, sample_db: Path) -> None:
        """Test template info with various parameter types."""
        from pt_snap_cli.query.config import QueryParameter

        template = QueryTemplate(
            name="complex_template",
            description="Template with complex parameters",
            query="SELECT * FROM blocks",
            parameters={
                "int_param": QueryParameter(
                    name="int_param",
                    type="int",
                    default=42,
                    required=False,
                    description="Integer parameter",
                ),
                "float_param": QueryParameter(
                    name="float_param",
                    type="float",
                    default=3.14,
                    required=False,
                    description="Float parameter",
                ),
                "str_param": QueryParameter(
                    name="str_param",
                    type="str",
                    default="default_value",
                    required=False,
                    description="String parameter",
                ),
                "bool_param": QueryParameter(
                    name="bool_param",
                    type="bool",
                    default=True,
                    required=False,
                    description="Boolean parameter",
                ),
                "required_param": QueryParameter(
                    name="required_param",
                    type="int",
                    default=None,
                    required=True,
                    description="Required parameter",
                ),
            },
        )
        register_query(template)

        result = runner.invoke(app, ["query", str(sample_db), "--template-info", "complex_template"])
        assert result.exit_code == 0
        assert "Template: complex_template" in result.stdout
        assert "int_param" in result.stdout
        assert "float_param" in result.stdout
        assert "str_param" in result.stdout
        assert "bool_param" in result.stdout
        assert "required_param" in result.stdout
        assert "(required)" in result.stdout
        assert "(optional)" in result.stdout
        assert "[default:" in result.stdout

    def test_template_info_shows_choices(self, sample_db: Path) -> None:
        from pt_snap_cli.query.config import QueryParameter

        register_query(
            QueryTemplate(
                name="ordered",
                query="SELECT 1 ORDER BY {{ order_by }} {{ order_dir }}",
                parameters={
                    "order_by": QueryParameter(name="order_by", type="str", default="id", choices=["id", "size"]),
                    "order_dir": QueryParameter(name="order_dir", type="str", default="ASC", choices=["ASC", "DESC"]),
                    "limit": QueryParameter(name="limit", type="int", default=-1),
                },
            )
        )

        result = runner.invoke(app, ["query", str(sample_db), "--template-info", "ordered"])

        assert result.exit_code == 0
        output = unstyle(result.stdout)
        assert "  order_by: str (optional) [choices: id, size] [default: id]" in output
        assert "  order_dir: str (optional) [choices: ASC, DESC] [default: ASC]" in output
        assert "  limit: int (optional) [default: -1]" in output

    def test_template_info_example_uses_first_choice_when_str_has_no_default(self, sample_db: Path) -> None:
        from pt_snap_cli.query.config import QueryParameter

        register_query(
            QueryTemplate(
                name="choice_example",
                query="SELECT 1 ORDER BY {{ order_by }}",
                parameters={
                    "order_by": QueryParameter(name="order_by", type="str", choices=["id", "size"]),
                },
            )
        )

        result = runner.invoke(app, ["query", str(sample_db), "--template-info", "choice_example"])

        assert result.exit_code == 0
        output = unstyle(result.stdout)
        assert '"order_by": "id"' in output
        assert '"order_by": "example"' not in output

    def test_template_info_without_parameters(self, sample_db: Path) -> None:
        """Test template info with no parameters."""
        template = QueryTemplate(
            name="no_param_template",
            description="Template without parameters",
            query="SELECT COUNT(*) FROM blocks",
        )
        register_query(template)

        result = runner.invoke(app, ["query", str(sample_db), "--template-info", "no_param_template"])
        assert result.exit_code == 0
        assert "Parameters:" in result.stdout
        assert "None" in result.stdout

    def test_template_info_without_output_schema(self, sample_db: Path) -> None:
        """Test template info without output schema."""
        template = QueryTemplate(
            name="no_schema_template",
            description="Template without output schema",
            query="SELECT * FROM blocks",
        )
        register_query(template)

        result = runner.invoke(app, ["query", str(sample_db), "--template-info", "no_schema_template"])
        assert result.exit_code == 0
        assert "Output Schema:" in result.stdout
        assert "Dynamic" in result.stdout
        assert "Semantics Version: none" in result.stdout

    def test_template_info_shows_packaged_semantics(self, sample_db: Path) -> None:
        result = runner.invoke(app, ["query", str(sample_db), "--template-info", "leak_detection"])
        output = unstyle(result.stdout)
        assert result.exit_code == 0
        assert "Semantics Version: 1" in output
        assert "units: event_id" in output
        assert "sentinel: -1" in output
        assert "Interpretation Limits:" in output
        assert "not a confirmed leak" in output

    def test_focus_database_success(self, sample_db: Path) -> None:
        """Test 'focus' command writes project focus by default."""
        result = runner.invoke(app, ["focus", str(sample_db)])
        assert result.exit_code == 0
        assert "Using project database" in result.stdout
        assert "Focus file" in result.stdout
        assert "Available devices" in result.stdout
        focus_file = Path.cwd() / ".pt-snap" / "focus.json"
        assert json.loads(focus_file.read_text())["db_path"] == str(sample_db.resolve())

    def test_focus_database_reports_v1_callstack_layout(self, tmp_path: Path) -> None:
        db_path = tmp_path / "v1.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT)")
        conn.commit()
        conn.close()

        result = runner.invoke(app, ["focus", str(db_path)])
        assert result.exit_code == 0
        assert "Callstack layout: v1 (inline text)" in result.stdout
        focus_data = json.loads((Path.cwd() / ".pt-snap" / "focus.json").read_text())
        assert "callstack_layout" not in focus_data

    def test_focus_database_warns_on_conflicting_callstack_layout(self, tmp_path: Path) -> None:
        db_path = tmp_path / "conflict.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT, callstackId INTEGER)")
        conn.commit()
        conn.close()

        result = runner.invoke(app, ["focus", str(db_path)])
        assert result.exit_code == 0
        assert "Warning:" in result.stdout
        assert "both callstack and callstackId" in result.stdout
        focus_data = json.loads((Path.cwd() / ".pt-snap" / "focus.json").read_text())
        assert focus_data["db_path"] == str(db_path.resolve())
        assert "callstack_layout" not in focus_data

    def test_focus_device_only_reports_callstack_layout(self, tmp_path: Path) -> None:
        db_path = tmp_path / "v1.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT)")
        conn.commit()
        conn.close()
        focus_dir = Path.cwd() / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(db_path)}))

        result = runner.invoke(app, ["focus", "--device", "0"])
        assert result.exit_code == 0
        assert "Focused device" in result.stdout
        assert "Callstack layout: v1 (inline text)" in result.stdout

    def test_focus_database_with_device(self, sample_db: Path) -> None:
        """Test 'focus --device' sets both database and device."""
        result = runner.invoke(app, ["focus", str(sample_db), "--device", "0"])
        assert result.exit_code == 0
        assert "Focused device: 0" in result.stdout

        focus_file = Path.cwd() / ".pt-snap" / "focus.json"
        data = json.loads(focus_file.read_text())
        assert data["db_path"] == str(sample_db.resolve())
        assert data["device_id"] == 0

    def test_focus_database_global(self, tmp_path: Path, sample_db: Path) -> None:
        """Test 'focus --global' preserves legacy global config behavior."""
        result = runner.invoke(app, ["focus", str(sample_db), "--global"])
        assert result.exit_code == 0
        assert "Using global database" in result.stdout
        config_file = tmp_path / ".config" / "pt-snap-cli" / "config.json"
        assert json.loads(config_file.read_text())["db_path"] == str(sample_db.resolve())
        assert not (Path.cwd() / ".pt-snap" / "focus.json").exists()

    def test_focus_database_session(self, sample_db: Path) -> None:
        """Test 'focus --session' prints export without writing focus files."""
        result = runner.invoke(app, ["focus", str(sample_db), "--session"])
        assert result.exit_code == 0
        assert shlex.split(result.stdout.strip()) == [
            "export",
            f"PT_SNAP_DB_PATH={sample_db.resolve()}",
        ]
        assert not (Path.cwd() / ".pt-snap" / "focus.json").exists()

    def test_focus_database_session_and_global_conflict(self, sample_db: Path) -> None:
        """Test mutually exclusive focus scopes."""
        result = runner.invoke(app, ["focus", str(sample_db), "--session", "--global"])
        assert result.exit_code == 1
        assert "cannot be used together" in result.stdout

    def test_focus_database_session_rejects_device(self, sample_db: Path) -> None:
        result = runner.invoke(
            app,
            ["focus", str(sample_db), "--session", "--device", "0"],
        )

        assert result.exit_code == 1
        assert "session focus exports only a database path" in result.stdout

    def test_focus_show_current(self, tmp_path: Path, sample_db: Path) -> None:
        """Test 'focus' command without arguments shows effective focus."""
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        focus_file = focus_dir / "focus.json"
        focus_file.write_text(json.dumps({"db_path": str(sample_db)}))

        result = runner.invoke(app, ["focus"])
        assert result.exit_code == 0
        assert "Current database (project)" in result.stdout
        assert str(sample_db) in result.stdout

    def test_focus_show_current_with_device(self, tmp_path: Path, sample_db: Path) -> None:
        """Test 'focus' without arguments shows db and device."""
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        focus_file = focus_dir / "focus.json"
        focus_file.write_text(json.dumps({"db_path": str(sample_db), "device_id": 1}))

        result = runner.invoke(app, ["focus"])
        assert result.exit_code == 0
        assert "Focused device: 1" in result.stdout

    def test_focus_no_database_set(self, tmp_path: Path) -> None:
        """Test 'focus' command when no focus is configured."""
        config_dir = tmp_path / ".config" / "pt-snap-cli"
        config_dir.mkdir(parents=True)

        result = runner.invoke(app, ["focus"])
        assert result.exit_code == 0
        assert "No current focus set" in result.stdout

    def test_focus_database_not_exist_warning(self, tmp_path: Path) -> None:
        """Test 'focus' command shows warning when effective focus doesn't exist."""
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        focus_file = focus_dir / "focus.json"
        focus_file.write_text(json.dumps({"db_path": "/nonexistent/path.db"}))

        result = runner.invoke(app, ["focus"])
        assert result.exit_code == 0
        assert "Current database" in result.stdout
        assert "Warning" in result.stdout

    def test_focus_device_only_update(self, tmp_path: Path, sample_db: Path) -> None:
        """Test 'focus --device' without db_path updates device only."""
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(sample_db)}))

        result = runner.invoke(app, ["focus", "--device", "0"])
        assert result.exit_code == 0
        assert "Focused device" in result.stdout

        data = json.loads((focus_dir / "focus.json").read_text())
        assert data["device_id"] == 0
        assert data["db_path"] == str(sample_db)

    def test_focus_device_only_no_db_set(self, tmp_path: Path) -> None:
        """Test 'focus --device' without a database set fails."""
        result = runner.invoke(app, ["focus", "--device", "0"])
        assert result.exit_code == 1
        assert "No database set" in result.stdout

    def test_focus_device_invalid(self, sample_db: Path) -> None:
        """Test 'focus --device' with invalid device ID."""
        result = runner.invoke(app, ["focus", str(sample_db), "--device", "99"])
        assert result.exit_code == 1
        assert "Device 99 not found" in result.stdout

    def test_focus_device_only_invalid(self, tmp_path: Path, sample_db: Path) -> None:
        """Test 'focus --device' with invalid device when db already set."""
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(sample_db)}))

        result = runner.invoke(app, ["focus", "--device", "99"])
        assert result.exit_code == 1
        assert "Device 99 not found" in result.stdout

    def test_config_show(self, tmp_path: Path, sample_db: Path) -> None:
        """Test 'config' command shows configuration."""
        config_dir = tmp_path / ".config" / "pt-snap-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"db_path": str(sample_db)}))

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "Current configuration" in result.stdout
        assert "db_path" in result.stdout

    def test_config_clear(self, tmp_path: Path) -> None:
        """Test 'config --clear' command clears configuration."""
        config_dir = tmp_path / ".config" / "pt-snap-cli"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"db_path": "/some/path.db"}))

        result = runner.invoke(app, ["config", "--clear"])
        assert result.exit_code == 0
        assert "Configuration cleared" in result.stdout

        config_data = json.loads(config_file.read_text())
        assert config_data == {}

    def test_config_no_config(self, tmp_path: Path) -> None:
        """Test 'config' command when no config exists."""
        config_dir = tmp_path / ".config" / "pt-snap-cli"
        config_dir.mkdir(parents=True)

        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "No configuration set" in result.stdout

    def test_config_path(self, tmp_path: Path) -> None:
        """Test 'config --path' command shows config file path."""
        result = runner.invoke(app, ["config", "--path"])
        assert result.exit_code == 0
        assert "Config file" in result.stdout
        assert "pt-snap-cli" in result.stdout


class TestQueryCommand:
    """Test query command."""

    def test_query_list_templates(self, sample_db: Path) -> None:
        """Test 'query --list' command lists templates grouped by category."""
        register_query(QueryTemplate(name="test_template", description="Test query", query="SELECT 1"))

        result = runner.invoke(app, ["query", str(sample_db), "--list"])
        assert result.exit_code == 0
        assert "Basic Queries:" in result.stdout
        assert "test_template" in result.stdout

    def test_query_list_no_templates(self, sample_db: Path) -> None:
        """Test 'query --list' shows default packaged templates."""
        result = runner.invoke(app, ["query", str(sample_db), "--list"])
        assert result.exit_code == 0
        # Default packaged templates should be listed
        assert "Basic Queries:" in result.stdout
        assert "block" in result.stdout
        assert "Statistical Queries:" in result.stdout
        assert "Business Queries:" in result.stdout

    def test_query_template_info(self, sample_db: Path) -> None:
        """Test 'query --template-info' command."""
        from pt_snap_cli.query.config import QueryParameter

        template = QueryTemplate(
            name="info_template",
            description="Template for testing",
            query="SELECT * FROM blocks",
            parameters={
                "device_id": QueryParameter(
                    name="device_id", type="int", default=0, required=False, description="Device ID"
                )
            },
            output_schema=[{"column": "id", "type": "int"}, {"column": "size", "type": "int"}],
        )
        register_query(template)

        result = runner.invoke(app, ["query", str(sample_db), "--template-info", "info_template"])
        assert result.exit_code == 0
        assert "Template: info_template" in result.stdout
        assert "Description" in result.stdout
        assert "Parameters:" in result.stdout

    def test_query_no_database_configured(self, tmp_path: Path) -> None:
        """Test 'query' command without database configuration."""
        result = runner.invoke(app, ["query"])
        assert result.exit_code == 1
        # The error should mention either database or template-use
        assert "error" in result.stdout.lower()

    def test_query_uses_project_focus(self, sample_db: Path) -> None:
        """Test 'query' command uses project focus."""
        focus_dir = Path.cwd() / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(sample_db)}))
        register_query(QueryTemplate(name="size_query", description="Test", query="SELECT size FROM trace_entry_0"))

        result = runner.invoke(app, ["query", "--template-use", "size_query"])

        assert result.exit_code == 0
        assert "'size': 1024" in result.stdout

    def test_query_env_overrides_project_focus(
        self,
        tmp_path: Path,
        sample_db: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test PT_SNAP_DB_PATH overrides project focus."""
        env_db = create_sample_db(tmp_path / "env.db", size=2048)
        focus_dir = Path.cwd() / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(sample_db)}))
        monkeypatch.setenv("PT_SNAP_DB_PATH", str(env_db))
        register_query(QueryTemplate(name="size_query", description="Test", query="SELECT size FROM trace_entry_0"))

        result = runner.invoke(app, ["query", "--template-use", "size_query"])

        assert result.exit_code == 0
        assert "'size': 2048" in result.stdout

    def test_query_explicit_path_overrides_env_and_project(
        self,
        tmp_path: Path,
        sample_db: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test explicit db path has highest priority."""
        env_db = create_sample_db(tmp_path / "env.db", size=2048)
        explicit_db = create_sample_db(tmp_path / "explicit.db", size=4096)
        focus_dir = Path.cwd() / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(sample_db)}))
        monkeypatch.setenv("PT_SNAP_DB_PATH", str(env_db))
        register_query(QueryTemplate(name="size_query", description="Test", query="SELECT size FROM trace_entry_0"))

        result = runner.invoke(app, ["query", str(explicit_db), "--template-use", "size_query"])

        assert result.exit_code == 0
        assert "'size': 4096" in result.stdout

    def test_query_with_device(self, sample_db: Path) -> None:
        """Test 'query' command with --device option."""
        template = QueryTemplate(
            name="device_query",
            description="Query with device",
            query="SELECT * FROM blocks_0 WHERE device_id = ?",
            devices=[0],
        )
        register_query(template)

        result = runner.invoke(app, ["query", str(sample_db), "--template-use", "device_query", "--device", "0"])
        assert result.exit_code in [0, 1]

    def test_query_uses_focused_device_zero(self, sample_db: Path) -> None:
        """Test query respects focused device 0."""
        focus_dir = Path.cwd() / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"db_path": str(sample_db), "device_id": 0}))
        register_query(
            QueryTemplate(
                name="size_query_device_zero",
                description="Test",
                query="SELECT size FROM trace_entry_0",
            )
        )

        result = runner.invoke(app, ["query", "--template-use", "size_query_device_zero"])

        assert result.exit_code == 0
        assert "'size': 1024" in result.stdout

    def test_query_max_rows_zero_is_unlimited(self, sample_db: Path) -> None:
        """Test -n 0 shows all rows."""
        register_query(
            QueryTemplate(
                name="two_rows",
                description="Test",
                query="SELECT 1 AS value UNION ALL SELECT 2 AS value",
            )
        )

        result = runner.invoke(
            app,
            ["query", str(sample_db), "--template-use", "two_rows", "-n", "0"],
        )

        assert result.exit_code == 0
        assert "Found 2 results, showing 2:" in result.stdout

    def test_query_with_params(self, sample_db: Path) -> None:
        """Test 'query' command with --params option."""
        template = QueryTemplate(
            name="param_query",
            description="Query with params",
            query="SELECT * FROM trace_entry_0 WHERE device_id = ?",
            devices=[0],
        )
        register_query(template)

        result = runner.invoke(
            app,
            [
                "query",
                str(sample_db),
                "--template-use",
                "param_query",
                "--params",
                '{"device_id": 0}',
            ],
        )
        assert result.exit_code in [0, 1]

    def test_query_invalid_json_params(self, sample_db: Path) -> None:
        """Test 'query' command with invalid JSON params."""
        register_query(QueryTemplate(name="test", description="Test", query="SELECT 1"))

        result = runner.invoke(app, ["query", str(sample_db), "--template-use", "test", "--params", "invalid json"])
        assert result.exit_code == 1
        assert "Error" in result.stdout

    def test_query_non_object_json_params(self, sample_db: Path) -> None:
        register_query(QueryTemplate(name="test", description="Test", query="SELECT 1"))

        result = runner.invoke(
            app,
            ["query", str(sample_db), "--template-use", "test", "--params", "[]"],
        )

        assert result.exit_code == 1
        assert "Error executing query: Query parameters must be a JSON object" in result.stdout

    def test_query_invalid_parameter_type_is_controlled(self, sample_db: Path) -> None:
        from pt_snap_cli.query.config import QueryParameter

        register_query(
            QueryTemplate(
                name="typed_query",
                query="SELECT {{ count }}",
                parameters={
                    "count": QueryParameter(name="count", type="int", required=True),
                },
            )
        )

        result = runner.invoke(
            app,
            [
                "query",
                str(sample_db),
                "--template-use",
                "typed_query",
                "--params",
                '{"count": "invalid"}',
            ],
        )

        assert result.exit_code == 1
        assert "Error executing query" in result.stdout
        assert "cannot be converted to int" in result.stdout

    def test_query_unknown_parameter_is_rejected(self, sample_db: Path) -> None:
        """Regression for issue #120: a misspelled filter must not be silently dropped."""
        from pt_snap_cli.query.config import QueryParameter

        register_query(
            QueryTemplate(
                name="filtered",
                query="SELECT * FROM trace_entry_0 WHERE size >= {{ min_size }}",
                parameters={"min_size": QueryParameter(name="min_size", type="int", default=0)},
            )
        )

        result = runner.invoke(
            app,
            ["query", str(sample_db), "--template-use", "filtered", "--params", '{"min_sze": 1}'],
        )

        assert result.exit_code == 1
        assert "Error executing query" in result.stdout
        assert "Unknown parameter(s) for template 'filtered': min_sze (accepted: min_size)" in (result.stdout)

    def test_query_sql_fragment_parameter_outside_choices_is_rejected(self, sample_db: Path) -> None:
        """Regression for issue #120: ORDER BY inputs are bounded before rendering."""
        from pt_snap_cli.query.config import QueryParameter

        register_query(
            QueryTemplate(
                name="ordered",
                query="SELECT * FROM trace_entry_0 ORDER BY {{ order_by }} {{ order_dir }}",
                parameters={
                    "order_by": QueryParameter(name="order_by", type="str", default="id", choices=["id", "size"]),
                    "order_dir": QueryParameter(name="order_dir", type="str", default="ASC", choices=["ASC", "DESC"]),
                },
            )
        )

        injected = runner.invoke(
            app,
            [
                "query",
                str(sample_db),
                "--template-use",
                "ordered",
                "--params",
                '{"order_by": "(SELECT name FROM sqlite_master LIMIT 1)"}',
            ],
        )
        assert injected.exit_code == 1
        assert "Parameter 'order_by' must be one of: id, size" in injected.stdout
        assert "syntax error" not in injected.stdout

        bad_direction = runner.invoke(
            app,
            [
                "query",
                str(sample_db),
                "--template-use",
                "ordered",
                "--params",
                '{"order_dir": "UP"}',
            ],
        )
        assert bad_direction.exit_code == 1
        assert "Parameter 'order_dir' must be one of: ASC, DESC (got 'UP')" in bad_direction.stdout

        accepted = runner.invoke(
            app,
            [
                "query",
                str(sample_db),
                "--template-use",
                "ordered",
                "--params",
                '{"order_by": "size", "order_dir": "desc"}',
            ],
        )
        assert accepted.exit_code == 0
        assert "Found 1 results" in accepted.stdout

    def test_query_list_by_category(self, sample_db: Path) -> None:
        """Test 'query --list --category basic' filters by category."""
        register_query(QueryTemplate(name="basic_q", description="Basic", query="SELECT 1", category="basic"))
        register_query(
            QueryTemplate(name="stat_q", description="Stats", query="SELECT COUNT(*)", category="statistical")
        )

        result = runner.invoke(app, ["query", str(sample_db), "--list", "--category", "basic"])
        assert result.exit_code == 0
        assert "Basic Queries:" in result.stdout
        assert "basic_q" in result.stdout
        assert "Statistical Queries:" not in result.stdout
        assert "stat_q" not in result.stdout

    def test_query_list_invalid_category(self, sample_db: Path) -> None:
        """Test 'query --list --category invalid' returns error."""
        register_query(QueryTemplate(name="test", description="Test", query="SELECT 1", category="basic"))

        result = runner.invoke(app, ["query", str(sample_db), "--list", "--category", "invalid"])
        assert result.exit_code != 0
        assert "Invalid category" in result.stdout


class TestSafeCall:
    """Test _safe_call wrapper for console script entry point."""

    def test_safe_call_runs_app(self, sample_db: Path) -> None:
        """Test that _safe_call successfully runs the CLI app."""
        from unittest.mock import patch

        from pt_snap_cli.cli import _safe_call

        with patch("sys.argv", ["pt-snap", "--version"]):
            assert _safe_call() == 0

    def test_safe_call_catches_comp_keyerror(self) -> None:
        """Test _safe_call catches KeyError from broken shell completion."""
        from unittest.mock import patch

        from pt_snap_cli.cli import _safe_call

        with patch("pt_snap_cli.cli.app", side_effect=KeyError("COMP_WORDS")):
            exit_code = _safe_call()
            assert exit_code == 1

    def test_safe_call_reraises_unrelated_keyerror(self) -> None:
        """Test _safe_call re-raises KeyError not related to shell completion."""
        from unittest.mock import patch

        from pt_snap_cli.cli import _safe_call

        with patch("pt_snap_cli.cli.app", side_effect=KeyError("some_other_key")):
            with pytest.raises(KeyError, match="some_other_key"):
                _safe_call()

    def test_safe_call_abort_writes_aborted(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Non-standalone Abort must keep Click's Aborted! line on stderr."""
        from unittest.mock import patch

        from typer.exceptions import Abort

        from pt_snap_cli.cli import _safe_call

        with (
            patch("sys.argv", ["pt-snap", "focus"]),
            patch("pt_snap_cli.cli.app", side_effect=Abort()),
        ):
            assert _safe_call() == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.strip() == "Aborted!"


class TestImportCommand:
    """Test import command."""

    def test_import_success_writes_focus(self, tmp_path: Path) -> None:
        """Test import writes a database and project focus by default."""
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_with_empty_cache.pkl"
        snapshot = tmp_path / "sample.pkl"
        shutil.copy(source, snapshot)

        result = runner.invoke(app, ["import", str(snapshot)], catch_exceptions=False)

        assert result.exit_code == 0
        assert "Imported:" in result.stdout
        assert "Cache miss: database_missing" in result.stdout
        assert (tmp_path / ".pt-snap" / "focus.json").exists()

    def test_import_missing_tool_message(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test import reports built-in backend packaging guidance when unavailable."""
        from pt_snap_cli.core.common.errors import ImportToolMissingError

        snapshot = tmp_path / "sample.pkl"
        snapshot.write_bytes(b"not a real snapshot")

        def raise_missing_tool(*args: object, **kwargs: object) -> object:
            raise ImportToolMissingError(
                "Snapshot import backend is unavailable. Reinstall msprof-analyze; the package may be incomplete."
            )

        monkeypatch.setattr(
            "pt_snap_cli.core.importing.import_service.ImportService.import_snapshot",
            raise_missing_tool,
        )

        result = runner.invoke(app, ["import", str(snapshot)])

        assert result.exit_code != 0
        assert "snapshot import backend" in result.output.lower()
        assert "reinstall msprof-analyze" in result.output.lower()

    def test_import_invalid_path(self) -> None:
        """Test import rejects missing snapshot paths."""
        result = runner.invoke(app, ["import", "/no/such/file.pkl"])

        assert result.exit_code != 0
        assert "exist" in result.output.lower()

    def test_import_invalid_suffix(self, tmp_path: Path) -> None:
        """Test import rejects non-pkl snapshot paths."""
        snapshot = tmp_path / "sample.txt"
        # Content is irrelevant: the .txt suffix is rejected before the
        # backend ever opens the file.
        snapshot.write_text("not a snapshot")

        result = runner.invoke(app, ["import", str(snapshot)])

        assert result.exit_code != 0
        assert "suffix" in result.output.lower() or ".pkl" in result.output.lower()

    def test_import_no_focus(self, tmp_path: Path) -> None:
        """Test import --no-focus creates a database without writing project focus."""
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_with_empty_cache.pkl"
        snapshot = tmp_path / "sample.pkl"
        shutil.copy(source, snapshot)

        result = runner.invoke(app, ["import", str(snapshot), "--no-focus"], catch_exceptions=False)

        assert result.exit_code == 0
        assert not (tmp_path / ".pt-snap").exists()
        assert (tmp_path / "sample.pkl.db").exists()

    def test_import_reuses_matching_database(self, tmp_path: Path) -> None:
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_with_empty_cache.pkl"
        snapshot = tmp_path / "sample.pkl"
        shutil.copy(source, snapshot)

        first = runner.invoke(app, ["import", str(snapshot), "--no-focus"])
        second = runner.invoke(app, ["import", str(snapshot), "--no-focus"])

        assert first.exit_code == 0
        assert second.exit_code == 0
        assert "Imported:" in first.stdout
        assert "Reused:" in second.stdout
        assert "Cache miss:" not in second.stdout

    def test_import_force_rebuilds_matching_database(self, tmp_path: Path) -> None:
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_with_empty_cache.pkl"
        snapshot = tmp_path / "sample.pkl"
        shutil.copy(source, snapshot)
        runner.invoke(app, ["import", str(snapshot), "--no-focus"])

        result = runner.invoke(app, ["import", str(snapshot), "--no-focus", "--force"])

        assert result.exit_code == 0
        assert "Imported:" in result.stdout
        assert "Cache miss: forced" in result.stdout

    def test_metadata_json_reports_generated_database(self, tmp_path: Path) -> None:
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_with_empty_cache.pkl"
        snapshot = tmp_path / "sample.pkl"
        shutil.copy(source, snapshot)
        runner.invoke(app, ["import", str(snapshot), "--no-focus"])

        result = runner.invoke(app, ["metadata", str(tmp_path / "sample.pkl.db"), "--json"])
        payload = json.loads(result.stdout)

        assert result.exit_code == 0
        assert payload["status"] == "available"
        assert payload["metadata"]["source_name"] == "sample.pkl"
        assert "source_path" not in payload["metadata"]

    def test_metadata_uses_current_focus(self, tmp_path: Path) -> None:
        source = Path(__file__).parent / "fixtures" / "snapshots" / "snapshot_with_empty_cache.pkl"
        snapshot = tmp_path / "sample.pkl"
        shutil.copy(source, snapshot)
        imported = runner.invoke(app, ["import", str(snapshot)])
        assert imported.exit_code == 0

        result = runner.invoke(app, ["metadata", "--json"])
        payload = json.loads(result.stdout)

        assert result.exit_code == 0
        assert payload["status"] == "available"
        assert payload["db_path"] == str((tmp_path / "sample.pkl.db").resolve())

    def test_metadata_reports_unavailable_for_legacy_database(self, sample_db: Path) -> None:
        result = runner.invoke(app, ["metadata", str(sample_db)])

        assert result.exit_code == 0
        assert "Status: unavailable" in result.stdout
        assert "Reason: metadata_missing" in result.stdout


class TestReportCommand:
    """Test report subcommands."""

    def test_report_help(self) -> None:
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0
        assert "Generate memory analysis reports" in result.stdout

    def test_peak_memory_report_text_output(self, tmp_path: Path) -> None:
        report_db = create_peak_report_db(tmp_path / "report.db")

        result = runner.invoke(app, ["report", "peak-memory", str(report_db)])

        assert result.exit_code == 0
        assert "Peak memory report" in result.stdout
        assert "Metric: active" in result.stdout
        assert "Allocator gap:" in result.stdout
        assert "Active memory by callstack:" in result.stdout
        assert "[static] allocEventId=-1, freeEventId=-1" in result.stdout

    def test_peak_memory_report_json_output(self, tmp_path: Path) -> None:
        report_db = create_peak_report_db(tmp_path / "report.db")

        result = runner.invoke(app, ["report", "peak-memory", str(report_db), "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["metric"] == "active"
        assert payload["event_id"] == 4
        assert payload["peak"]["peak_active_event_id"] == 4
        assert payload["allocator_gap"]["peak_reserved_event_id"] == 3
        assert isinstance(payload["callstack_groups"], list)

    def test_peak_memory_report_invalid_metric(self, tmp_path: Path) -> None:
        report_db = create_peak_report_db(tmp_path / "report.db")

        result = runner.invoke(
            app,
            ["report", "peak-memory", str(report_db), "--metric", "invalid"],
        )

        assert result.exit_code == 2
        assert "Invalid value" in result.stdout or "Invalid value" in result.stderr

    def test_peak_memory_report_exclude_static(self, tmp_path: Path) -> None:
        report_db = create_peak_report_db(tmp_path / "report.db")

        result = runner.invoke(
            app,
            ["report", "peak-memory", str(report_db), "--exclude-static", "--json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert "[static] allocEventId=-1, freeEventId=-1" not in {
            row["callstack"] for row in payload["callstack_groups"]
        }

    def test_peak_memory_report_configured_db_not_found(self, tmp_path: Path) -> None:
        config_dir = tmp_path / ".config" / "pt-snap-cli"
        config_dir.mkdir(parents=True)
        missing_db = tmp_path / "missing.db"
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"db_path": str(missing_db)}))

        result = runner.invoke(app, ["report", "peak-memory"])

        assert result.exit_code == 1
        assert "Database from global focus not found" in result.stdout
        assert str(missing_db) in result.stdout


class TestCapabilitiesAndOverviewCommands:
    def test_capabilities_text_lists_templates(self) -> None:
        result = runner.invoke(app, ["capabilities"])
        assert result.exit_code == 0
        assert "CLI version:" in result.stdout
        assert "leak_detection" in result.stdout
        assert "preexisting_live" in result.stdout
        assert "freed_block_lifetime" in result.stdout
        assert "pt-snap-helper" not in result.stdout
        assert "Use --json for full parameter contracts" in result.stdout

    def test_overview_text_reports_devices_and_metadata(self, sample_db: Path) -> None:
        result = runner.invoke(app, ["overview", str(sample_db)])
        assert result.exit_code == 0
        assert f"Database: {sample_db.resolve()}" in result.stdout
        assert "Import metadata: unavailable" in result.stdout
        assert "0: events 1..1" in result.stdout

    def test_overview_requires_database(self) -> None:
        result = runner.invoke(app, ["overview"])
        assert result.exit_code == 1
        assert "No database path specified" in unstyle(result.stdout)
