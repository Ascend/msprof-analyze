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

"""Runtime acceptance shared by Python 3.7.5 and current Python releases.

Run this file against the installed host wheel, outside the source checkout, to
validate its actual minimum-version dependency resolution and entry points.
"""

import importlib
import json
import pickle
import sys
from pathlib import Path
from typing import Optional, get_type_hints

# This acceptance file also runs unchanged on the host's minimum interpreter.
# ruff: noqa: UP045
import pt_snap_cli
import pytest
from click.testing import CliRunner
from pt_snap_cli._compat import unlink_missing_ok, zip_strict
from pt_snap_cli.snapshot.util.sqlite_meta import _map_py_type_to_sqlite

from msprof_analyze.cli.pt_snap_cli import pt_snap_command
from msprof_analyze.pt_snap import SnapshotAnalyzer


def test_runtime_modules_compile_and_import_on_the_running_interpreter():
    root = Path(pt_snap_cli.__file__).parent
    for path in root.rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        parts = path.relative_to(root).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        importlib.import_module(".".join(("pt_snap_cli",) + parts))
    assert sys.version_info >= (3, 7, 5)
    assert get_type_hints(SnapshotAnalyzer.execute_query)


def test_distribution_declares_the_documented_patch_version_minimum():
    try:
        from importlib.metadata import distribution
    except ImportError:
        from importlib_metadata import distribution
    from packaging.specifiers import SpecifierSet

    supported = SpecifierSet(distribution("msprof-analyze").metadata["Requires-Python"])
    assert "3.7.4" not in supported
    assert "3.7.5" in supported
    assert "3.7.9" in supported


@pytest.mark.parametrize("first,second", [([1, 2], [3]), ([1], [2, 3])])
def test_strict_zip_preserves_length_validation_and_lazy_consumption(first, second):
    paired = zip_strict(iter(first), iter(second))
    assert next(paired) == (first[0], second[0])
    with pytest.raises(ValueError):
        next(paired)
    assert list(zip_strict([], [])) == []
    assert list(zip_strict([1, 2], [3, 4])) == [(1, 3), (2, 4)]


def test_cleanup_ignores_only_missing_files(tmp_path, monkeypatch):
    path = tmp_path / "cleanup"
    unlink_missing_ok(path)
    path.write_text("owned test data", encoding="utf-8")
    unlink_missing_ok(path)
    assert not path.exists()

    def denied(self):
        raise PermissionError("preserve I/O failures")

    monkeypatch.setattr(Path, "unlink", denied)
    with pytest.raises(PermissionError):
        unlink_missing_ok(path)


def test_nullable_sqlite_affinity_works_without_pep604_types():
    assert _map_py_type_to_sqlite(Optional[int]) == "INTEGER"
    assert _map_py_type_to_sqlite(Optional[str]) == "TEXT"


def _snapshot():
    frame = [{"filename": "模型.py", "line": 4, "name": "allocate"}]
    events = [
        {
            "action": action,
            "addr": 1000,
            "size": size,
            "stream": stream,
            "frames": frame,
        }
        for action, size, stream in (
            ("alloc", 16, 0),
            ("alloc", 8, 1),
            ("free_requested", 16, 0),
            ("free_completed", 16, 0),
            ("alloc", 16, 0),
        )
    ]
    segments = []
    for stream, blocks, total in (
        (0, [(1000, 16, 14), (1040, 8, 6)], 64),
        (1, [(1000, 8, 5)], 32),
    ):
        occupied = sum(item[1] for item in blocks)
        segments.append(
            {
                "device": 0,
                "address": 1000,
                "total_size": total,
                "stream": stream,
                "segment_type": "small",
                "is_expandable": False,
                "frames": [],
                "allocated_size": occupied,
                "active_size": occupied,
                "blocks": [
                    {
                        "address": address,
                        "size": size,
                        "requested_size": requested,
                        "state": "active_allocated",
                        "frames": frame,
                    }
                    for address, size, requested in blocks
                ],
            }
        )
    return {"segments": segments, "device_traces": [events]}


@pytest.mark.parametrize("layout", ["single-db", "pt-snap-native-v2", "msinsight"])
def test_unicode_import_reuse_query_reports_and_split(tmp_path, monkeypatch, layout):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    source = tmp_path / "中文 路径" / "内存 快照.pickle"
    source.parent.mkdir()
    source.write_bytes(pickle.dumps(_snapshot(), protocol=4))
    runner = CliRunner()

    def invoke(*arguments):
        result = runner.invoke(pt_snap_command, list(map(str, arguments)))
        assert result.exit_code == 0, result.output
        return result.stdout

    options = [
        "import",
        source,
        "--output-dir",
        tmp_path / "parsed",
        "--format",
        layout,
        "--no-focus",
        "--json",
    ]
    if layout != "single-db":
        options += ["--events-per-slice", "2"]
    imported = json.loads(invoke(*options))
    assert not imported["reused"]
    assert json.loads(invoke(*options))["reused"]
    database = imported["db_path"]
    assert json.loads(invoke("overview", database, "--json"))["ok"]
    tree = json.loads(
        invoke(
            "query",
            database,
            "--template-use",
            "active_memory_frame_tree_at_event",
            "--params",
            '{"event_id":4}',
            "--json",
        )
    )
    assert tree["rows"][0]["size_bytes"] == 32
    assert tree["rows"][0]["block_count"] == 3
    assert tree["rows"][0]["requested_bytes"] == 25
    with SnapshotAnalyzer(database) as analyzer:
        assert (
            analyzer.execute_query(
                "active_memory_frame_tree_at_event", {"event_id": 4}
            )["rows"]
            == tree["rows"]
        )
    assert (
        "<html"
        in invoke(
            "report", "memory-tree", database, "--event-id", "4", "--format", "html"
        ).lower()
    )
    assert (
        json.loads(invoke("report", "peak-memory", database, "--json"))[
            "included_bytes"
        ]
        == 32
    )
    split = json.loads(
        invoke(
            "split",
            source,
            "--output",
            tmp_path / "slices",
            "--max-entries",
            "3",
            "--json",
        )
    )
    assert len(split["files"]) == 2
    assert all(Path(path).is_file() for path in split["files"])
