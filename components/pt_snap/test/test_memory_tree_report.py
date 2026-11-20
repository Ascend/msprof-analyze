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
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.memory_tree_render import render_memory_tree
from test.frame_tree_helpers import create_frame_tree_db


@pytest.fixture
def frame_db(tmp_path: Path) -> Path:
    return create_frame_tree_db(tmp_path / "frames.db")


def test_report_cli_query_and_analyzer_share_exact_tree(frame_db: Path):
    runner = CliRunner()
    report = runner.invoke(app, ["report", "memory-tree", str(frame_db), "--event-id", "8", "--json"])
    assert report.exit_code == 0, report.output
    query = runner.invoke(
        app,
        [
            "query",
            str(frame_db),
            "--template-use",
            "active_memory_frame_tree_at_event",
            "--params",
            '{"event_id":8}',
            "--json",
        ],
    )
    assert query.exit_code == 0, query.output
    with SnapshotAnalyzer(db_path=frame_db) as analyzer:
        api = analyzer.execute_query("active_memory_frame_tree_at_event", params={"event_id": 8})
        assert api["rows"] == json.loads(report.output)["rows"] == json.loads(query.output)["rows"]
        assert api["total_is_exact"] and not api["truncated"]
        assert "size_bytes = self_bytes" in " ".join(
            analyzer.get_template_info("active_memory_frame_tree_at_event")["interpretation_limits"]
        )


def test_report_text_and_html_are_usable(frame_db: Path):
    runner = CliRunner()
    args = ["report", "memory-tree", str(frame_db), "--event-id", "8"]
    text = runner.invoke(app, args)
    assert text.exit_code == 0, text.output
    assert "[all active blocks]: 535 / 0 / 9" in text.output
    assert "model.py:20 forward: 375 / 50 / 4" in text.output
    html = runner.invoke(app, [*args, "--format", "html"])
    assert html.exit_code == 0, html.output
    assert html.output.startswith("<!doctype html>")
    assert "Reset zoom" in html.output and '"size_bytes": 535' in html.output
    assert "__TREE_DATA__" not in html.output
    assert runner.invoke(app, ["report", "memory-tree", str(frame_db)]).exit_code != 0
    conflict = runner.invoke(app, [*args, "--format", "html", "--json"])
    assert conflict.exit_code == 1
    assert json.loads(conflict.output)["error"]["code"] == "INVALID_PARAMETER"


def test_renderer_rejects_partial_tree_and_escapes_frame_text(frame_db: Path):
    service = ReportService()
    try:
        result = service.memory_tree_report(event_id=8, db_path=frame_db)
    finally:
        service.close()
    with pytest.raises(ValueError, match="complete frame tree"):
        render_memory_tree(replace(result, truncated=True), 8)
    result.rows[1]["label"] = '</script><script>alert("bad")</script>&训练'
    html = render_memory_tree(result, 8, html=True)
    assert '</script><script>alert("bad")' not in html
    assert "\\u003c/script\\u003e" in html
    payload = json.loads(html.split('<script id="tree-data" type="application/json">')[1].split("</script>")[0])
    assert payload["nodes"][1]["label"] == result.rows[1]["label"]


def test_report_legacy_schema_error_is_json_and_actionable(frame_db: Path):
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(frame_db)) as conn, conn:
        conn.execute("DROP TABLE callstack_frame")
    result = CliRunner().invoke(app, ["report", "memory-tree", str(frame_db), "--event-id", "8", "--json"])
    assert result.exit_code == 1
    assert "Re-import the original snapshot" in json.loads(result.output)["error"]["message"]


@pytest.mark.parametrize(
    "damage",
    [
        "empty",
        "duplicate",
        "orphan",
        "depth",
        "root_parent",
        "negative",
        "noninteger",
        "conservation",
    ],
)
@pytest.mark.parametrize("html", [False, True])
def test_renderer_rejects_invalid_complete_claims(frame_db: Path, damage: str, html: bool):
    service = ReportService()
    try:
        result = service.memory_tree_report(event_id=8, db_path=frame_db)
    finally:
        service.close()
    if damage == "empty":
        result.rows.clear()
    elif damage == "duplicate":
        result.rows.append(result.rows[-1].copy())
    elif damage == "orphan":
        result.rows[-1]["parent_id"] = "nonexistent"
    elif damage == "depth":
        result.rows[-1]["depth"] = 100
    elif damage == "root_parent":
        result.rows[0]["parent_id"] = "root"
    elif damage == "negative":
        result.rows[0]["size_bytes"] = -1
    elif damage == "noninteger":
        result.rows[0]["size_bytes"] = 535.0
    else:
        result.rows[0]["size_bytes"] = 536
    with pytest.raises(ValueError, match="complete frame tree"):
        render_memory_tree(result, 8, html=html)


def test_renderer_rejects_has_more_without_truncated(frame_db: Path):
    service = ReportService()
    try:
        result = service.memory_tree_report(event_id=8, db_path=frame_db)
    finally:
        service.close()
    with pytest.raises(ValueError, match="complete frame tree"):
        render_memory_tree(replace(result, has_more=True), 8, html=True)
    result.rows[1]["label"] = "line\nnext\r\x1b[31m"
    text = render_memory_tree(result, 8)
    assert "\x1b" not in text
    assert r"line\nnext\r\u001b[31m" in text
