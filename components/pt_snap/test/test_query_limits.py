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

"""Query, API, report and capability adapters expose the same public limits."""

import json
import re
from contextlib import closing

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import QueryLimits, SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.core.common.errors import InvalidParameterError, QueryExecutionError
from test.core.test_dataset_attribution import case
from test.test_dataset_focus import make_dataset

runner = CliRunner()
ENV_NAMES = (
    "PT_SNAP_MAX_WORK_ROWS",
    "PT_SNAP_MAX_WORK_BYTES",
    "PT_SNAP_MAX_SCRATCH_DB_BYTES",
)


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in (*ENV_NAMES, "PT_SNAP_DB_PATH", "PT_SNAP_QUERY_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)


def test_analyzer_constructor_per_call_environment_and_catalog_precedence(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "public", devices=(0,))
    monkeypatch.setenv(ENV_NAMES[0], "1")
    with SnapshotAnalyzer(root, query_limits=QueryLimits(100)) as analyzer:
        expected = analyzer.execute_query("event")
        assert analyzer.execute_query("event") == expected
        assert expected["scope"]["work_budget"]["max_rows"] == 100
        assert analyzer.get_template_info("event")["dataset_support"]["work_limit_rows"] == 100
        assert all(t["dataset_support"]["work_limit_rows"] == 100 for t in analyzer.list_capabilities()["templates"])
        with pytest.raises(QueryExecutionError, match="max_work_rows=1"):
            analyzer.execute_query("event", query_limits=QueryLimits(1))
        with pytest.raises(InvalidParameterError, match="QueryLimits"):
            analyzer.execute_query("event", query_limits={"max_work_rows": 1})
        assert analyzer.execute_query("event") == expected
    with SnapshotAnalyzer(root) as analyzer:
        with pytest.raises(QueryExecutionError, match="max_work_rows=1"):
            analyzer.execute_query("event")
        assert analyzer.execute_query("event", query_limits=QueryLimits(100)) == expected


@pytest.mark.parametrize("command", [["query"], ["report", "peak-memory"], ["report", "memory-tree"]])
def test_query_and_report_help_show_all_three_flags(command):
    result = runner.invoke(app, [*command, "--help"])
    assert result.exit_code == 0
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    for flag in ("--max-work-rows", "--max-work-bytes", "--max-scratch-db-bytes"):
        assert flag in text


@pytest.mark.parametrize(
    "command",
    [
        ["query", "--template-use", "event"],
        ["report", "peak-memory"],
        ["report", "memory-tree", "--event-id", "0"],
    ],
)
@pytest.mark.parametrize(
    "flag,value",
    [("--max-work-rows", "0"), ("--max-work-bytes", "-1"), ("--max-scratch-db-bytes", "4095")],
)
def test_cli_invalid_values_fail_as_json_before_database_io(command, flag, value):
    result = runner.invoke(app, [*command, flag, value, "--json"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "INVALID_PARAMETER"
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("command", [["query", "--template-use", "event"], ["report", "peak-memory"]])
def test_cli_environment_is_validated_and_explicit_flags_override_it(tmp_path, monkeypatch, command):
    root = case(tmp_path, devices=(0,))
    monkeypatch.setenv(ENV_NAMES[0], "invalid")
    failed = runner.invoke(app, [*command, str(root), "--json"])
    assert failed.exit_code == 1
    assert json.loads(failed.stderr)["error"]["code"] == "INVALID_PARAMETER"
    monkeypatch.setenv(ENV_NAMES[1], "123456")
    passed = runner.invoke(app, [*command, str(root), "--max-work-rows", "1000", "--json"])
    assert passed.exit_code == 0, passed.output
    budget = json.loads(passed.stdout)["scope"]["work_budget"]
    assert budget["max_rows"] == 1000 and budget["max_bytes"] == 123456
    assert budget["max_scratch_db_bytes"] == QueryLimits().max_scratch_db_bytes


def test_cli_report_and_direct_report_use_same_limits(tmp_path):
    root = case(tmp_path, devices=(0,))
    limits = QueryLimits(1000, 123456, 0)
    with closing(ReportService()) as service:
        expected = service.peak_memory_report(root, query_limits=limits)
        attribution = service.event_attribution(4, db_path=root, query_limits=limits)
    result = runner.invoke(
        app,
        [
            "report",
            "peak-memory",
            str(root),
            "--max-work-rows",
            "1000",
            "--max-work-bytes",
            "123456",
            "--max-scratch-db-bytes",
            "0",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    actual = json.loads(result.stdout)
    assert actual["scope"] == expected.scope
    assert actual["callstack_groups"] == expected.callstack_groups
    assert attribution.scope["work_budget"] == expected.scope["work_budget"]


def test_template_info_and_capabilities_use_effective_environment_values(monkeypatch):
    monkeypatch.setenv(ENV_NAMES[0], "200000")
    monkeypatch.setenv(ENV_NAMES[1], "123456")
    monkeypatch.setenv(ENV_NAMES[2], "4096")
    result = runner.invoke(app, ["capabilities", "--json"])
    assert result.exit_code == 0, result.output
    for template in json.loads(result.stdout)["templates"]:
        assert template["dataset_support"]["work_limit_rows"] == 200000
        assert template["dataset_support"]["work_limit_bytes"] == 123456
        assert template["dataset_support"]["max_scratch_db_bytes"] == 4096
    info = runner.invoke(app, ["query", "--template-info", "event", "--max-work-rows", "300000", "--json"])
    assert info.exit_code == 0, info.output
    assert json.loads(info.stdout)["dataset_support"]["work_limit_rows"] == 300000


def test_invalid_limit_environment_is_json_error_for_capabilities(monkeypatch):
    monkeypatch.setenv(ENV_NAMES[0], "true")
    result = runner.invoke(app, ["capabilities", "--json"])
    assert result.exit_code == 1 and result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "INVALID_PARAMETER"


def test_memory_tree_forwards_limits_without_capping_standalone_output(tmp_path, monkeypatch):
    from pt_snap_cli.core.analysis.query_service import QueryService
    from test.frame_tree_helpers import create_frame_tree_db

    path = create_frame_tree_db(tmp_path / "frames.db")
    observed = []
    original = QueryService._new_budget

    def capture(self, timeout_s=None, query_limits=None):
        budget = original(self, timeout_s, query_limits)
        observed.append(budget)
        return budget

    monkeypatch.setattr(QueryService, "_new_budget", capture)
    monkeypatch.setenv(ENV_NAMES[0], "1")
    with closing(ReportService()) as service:
        expected = service.memory_tree_report(8, db_path=path, query_limits=QueryLimits(2))
    result = runner.invoke(
        app,
        [
            "report",
            "memory-tree",
            str(path),
            "--event-id",
            "8",
            "--max-work-rows",
            "2",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["rows"] == expected.rows
    assert expected.returned > 2
    assert len(observed) == 2 and observed[0] is not observed[1]
    assert all(budget.max_work_rows == 2 for budget in observed)
