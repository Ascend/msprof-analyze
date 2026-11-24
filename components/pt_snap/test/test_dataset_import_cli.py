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

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import _safe_call, app
from test.core.test_dataset_import import source_options


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


def test_dataset_cli_json_generation_reuse_force_focus_and_text(tmp_path):
    options = source_options(tmp_path, multiple=True)
    args = [
        "import",
        str(options.snapshot_file),
        "-o",
        str(options.output_dir),
        "--events-per-slice",
        "2",
    ]
    runner = CliRunner()
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["format"] == "pt-snap-native-v2"
    assert data["devices"] == [0, 1] and data["slice_count"] == 10
    assert data["omitted_devices"] == [2]
    assert data["dataset_path"] == data["db_path"]
    assert data["rebuilt"] and not data["reused"]
    assert data["focus_state"]["callstack_layout"] == "v2"
    reused = runner.invoke(app, [*args, "--no-focus", "--json"])
    assert reused.exit_code == 0
    assert json.loads(reused.output)["reused"] is True
    rebuilt = runner.invoke(app, [*args, "--force"])
    assert rebuilt.exit_code == 0 and "slices: 10" in rebuilt.output
    focus = runner.invoke(app, ["focus", data["dataset_path"], "--device", "1", "--json"])
    assert focus.exit_code == 0
    focused = json.loads(focus.output)
    with SnapshotAnalyzer(data["dataset_path"], device_id=1) as analyzer:
        state = analyzer.get_focus()
        assert state.db_path == focused["db_path"]
        assert state.available_devices == focused["available_devices"] == [0, 1]
        assert state.callstack_layout == focused["callstack_layout"] == "v2"
        assert state.device_id == focused["device_id"] == 1


@pytest.mark.parametrize(
    "arguments",
    [
        ["--events-per-slice", "0"],
        ["--events-per-slice", "nope"],
        ["--events-per-slice"],
        ["--format", "unknown"],
        ["--format", ""],
        ["--format", "pt-snap-native-v2"],
        ["--events-per-slice", "2", "--format", "single-db"],
        ["--events-per-slice", "2", "--format", "compatibility-v2"],
        ["--device", "-1"],
    ],
)
def test_dataset_cli_argument_error_json(tmp_path, arguments, monkeypatch, capsys):
    options = source_options(tmp_path)
    monkeypatch.setattr("sys.argv", ["pt-snap", "import", str(options.snapshot_file), "--json", *arguments])
    assert _safe_call() != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    data = json.loads(captured.err)
    assert data["ok"] is False and data["error"]["code"] == "INVALID_PARAMETER"
    assert not list(tmp_path.glob("*.pt-snap-native-v2"))
