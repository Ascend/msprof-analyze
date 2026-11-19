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

"""Embedded snapshot commands retain the original parser and JSON contracts."""

import json
import os
import subprocess
import sys
from inspect import signature

import pytest
from click.testing import CliRunner

from msprof_analyze.cli.pt_snap_cli import pt_snap_command, run_pt_snap


def _runner():
    # Click 8.1 (Python 3.7) defaults to mixing stderr into stdout.
    if "mix_stderr" in signature(CliRunner).parameters:
        return CliRunner(mix_stderr=False)
    return CliRunner()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--help"],
        ["import", "--help"],
        ["split", "--help"],
        ["query", "--help"],
        ["focus", "--help"],
        ["config", "--help"],
        ["overview", "--help"],
        ["metadata", "--help"],
        ["capabilities", "--help"],
        ["report", "--help"],
        ["report", "memory-tree", "--help"],
        ["report", "peak-memory", "--help"],
    ],
)
def test_complete_command_tree_is_available(arguments):
    result = _runner().invoke(pt_snap_command, arguments)
    assert result.exit_code == 0, result.output
    assert "msprof-analyze pt-snap" in result.output


def test_capabilities_are_clean_json_and_match_original_cli():
    from pt_snap_cli.cli import _safe_call

    runner = _runner()
    prefixed = runner.invoke(pt_snap_command, ["capabilities", "--json"])
    assert prefixed.exit_code == 0, prefixed.output
    assert prefixed.stderr == ""
    with runner.isolation() as streams:
        assert _safe_call(["capabilities", "--json"]) == 0
        original = streams[0].getvalue().decode()
    assert json.loads(prefixed.stdout) == json.loads(original)


def test_parser_failure_retains_json_stderr_and_nonzero_exit():
    result = _runner().invoke(pt_snap_command, ["query", "--json", "--unknown-option"])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "INVALID_PARAMETER"


def test_forwarding_preserves_unicode_spaces_and_double_dash(monkeypatch):
    from pt_snap_cli import cli

    observed = []
    monkeypatch.setattr(
        cli, "_safe_call", lambda args, **kwargs: observed.append((args, kwargs)) or 7
    )
    args = ["import", "--", "中文 路径/快照.pkl"]
    result = _runner().invoke(pt_snap_command, args)
    assert result.exit_code == 7
    assert observed == [(args, {"prog_name": "msprof-analyze pt-snap"})]


def test_host_minimum_python_is_forwarded_without_a_component_version_gate(monkeypatch):
    from pt_snap_cli import cli

    import msprof_analyze.cli.pt_snap_cli as adapter

    observed = []
    monkeypatch.setattr(adapter.sys, "version_info", (3, 7, 5))
    monkeypatch.setattr(
        cli, "_safe_call", lambda args, **kwargs: observed.append((args, kwargs)) or 0
    )
    assert run_pt_snap(["--help"]) == 0
    assert observed == [(["--help"], {"prog_name": "msprof-analyze pt-snap"})]


def test_console_prefix_does_not_load_legacy_analysis_stack(tmp_path):
    code = (
        "import sys; from msprof_analyze.cli.pt_snap_cli import main; "
        "sys.argv=['msprof-analyze','pt-snap','capabilities','--json']; "
        "status=main(); "
        "assert 'msprof_analyze.cli.entrance' not in sys.modules; "
        "assert 'pandas' not in sys.modules; sys.exit(status)"
    )
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code],
        cwd=tmp_path,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
    assert result.stderr == ""


def test_public_api_alias_is_original_analyzer():
    from pt_snap_cli.api import (
        QueryLimits as OriginalLimits,
    )
    from pt_snap_cli.api import (
        SnapshotAnalyzer as OriginalAnalyzer,
    )

    from msprof_analyze.pt_snap import QueryLimits, SnapshotAnalyzer

    assert SnapshotAnalyzer is OriginalAnalyzer
    assert QueryLimits is OriginalLimits
