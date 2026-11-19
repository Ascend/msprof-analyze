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

"""Exercise actual OS paths, SQLite handles and launchers on every CI platform.

These are deliberately ordinary non-slow tests. They do not simulate Windows
using POSIX paths and do not treat a Linux pass as macOS/Windows evidence.
"""

import dataclasses
import json
import os
import sqlite3
import stat
import subprocess
import sys
import sysconfig
import tempfile
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.context import Context
from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.common.query_limits import QueryLimits
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_scratch as scratch
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql
from pt_snap_cli.core.importing.import_service import ImportService
from test.core.test_dataset_import import hashes, source_options

ROOT = Path(__file__).resolve().parents[1]
SPECIAL_NAME = "平台 #100% + spaces"


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", lambda: home)
    for name in ("PT_SNAP_DB_PATH", "PT_SNAP_QUERY_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def readonly_dataset(tmp_path):
    parent = tmp_path / SPECIAL_NAME
    parent.mkdir()
    options = dataclasses.replace(source_options(parent), set_focus=False)
    root = ImportService().import_snapshot(options).db_path
    originals = {path: path.stat().st_mode for path in root.rglob("*") if path.is_file()}
    try:
        for path in originals:
            path.chmod(stat.S_IREAD)
            assert not path.stat().st_mode & stat.S_IWUSR
        yield root
    finally:
        # Windows cannot unlink a read-only file; restore only our fixture files.
        for path, mode in originals.items():
            if path.exists():
                path.chmod(mode)


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
@pytest.mark.parametrize("persistent", [False, True], ids=["scoped", "persistent"])
def test_context_special_paths_use_readonly_uri_and_release_handles(tmp_path, monkeypatch, relative, persistent):
    directory = tmp_path / SPECIAL_NAME
    directory.mkdir()
    path = directory / "snapshot #1%25.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            "CREATE TABLE dictionary (id INTEGER);"
            "CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY, callstack TEXT);"
            "INSERT INTO trace_entry_0 VALUES (7, 'selected database');"
        )
    before = path.read_bytes()
    opened = []
    connect = sqlite3.connect

    def record(uri, /, *args, **kwargs):
        assert isinstance(uri, str) and uri.startswith("file:")
        assert uri.endswith("?mode=ro") and "immutable" not in uri
        assert "%23" in uri and "%25" in uri and kwargs["uri"] is True
        connection = connect(uri, *args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", record)
    requested = path.relative_to(tmp_path) if relative else path
    with closing(Context(requested, persistent=persistent)) as context:
        with context.connect() as conn:
            assert tuple(conn.execute("SELECT * FROM trace_entry_0").fetchone()) == (
                7,
                "selected database",
            )
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("DELETE FROM trace_entry_0")
    assert opened
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    assert path.read_bytes() == before
    assert list(directory.iterdir()) == [path]
    renamed = path.with_name("released.db")
    path.rename(renamed)
    renamed.unlink()  # Fails on Windows if an owned SQLite handle escaped.
    assert not list(directory.iterdir())


@pytest.mark.parametrize("manifest_path", [False, True], ids=["directory", "manifest"])
def test_readonly_native_members_and_special_paths_remain_unchanged(readonly_dataset, manifest_path):
    root = readonly_dataset
    before = hashes(root)
    target = root / "manifest.json" if manifest_path else root
    with SnapshotAnalyzer(target) as analyzer:
        assert analyzer.get_database_overview()["dataset"]["real_event_count"] == 9
        assert analyzer.execute_query("event", {"id": 7})["rows"][0]["id"] == 7
        assert analyzer.execute_query("memory_peak")["rows"]
        assert analyzer.execute_query("block")["rows"]
    assert hashes(root) == before
    assert not any(root.rglob("*-wal"))
    assert not any(root.rglob("*-shm"))
    assert not any(root.rglob("*-journal"))
    # Renaming away and back checks directory/member handle release on Windows
    # without discarding the fixture's original permission-restoration paths.
    renamed = root.with_name("released dataset")
    root.rename(renamed)
    renamed.rename(root)


@pytest.mark.parametrize("fail", [False, True], ids=["success", "scratch-exhaustion"])
def test_scratch_uses_os_temp_directory_and_closes_before_cleanup(tmp_path, monkeypatch, readonly_dataset, fail):
    root = readonly_dataset
    before = hashes(root)
    temp_root = tmp_path / ("temporary " + SPECIAL_NAME)
    temp_root.mkdir()
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(temp_root))
    monkeypatch.setattr(tempfile, "tempdir", None)
    assert Path(tempfile.gettempdir()) == temp_root
    created, connections = [], []
    original_build = scratch._ScratchSources.build

    def observed_build(database, items, maximum):
        connections.append(database.connection)
        path = Path(database.connection.execute("PRAGMA database_list").fetchone()[2])
        assert path.parent.parent == temp_root
        assert path.is_file()
        created.append(path)
        return original_build(database, items, maximum)

    monkeypatch.setattr(scratch._ScratchSources, "build", observed_build)
    monkeypatch.setattr(dataset_lifecycle_sql, "_ATTACHED_OBSERVATION_LIMIT", 0)
    limits = QueryLimits(max_scratch_db_bytes=4096 if fail else 512 * 1024**2)
    with SnapshotAnalyzer(root, query_limits=limits) as analyzer:
        if fail:
            with pytest.raises(QueryExecutionError, match="scratch space exhausted"):
                analyzer.execute_query("block")
        else:
            rows = analyzer.execute_query("block")["rows"]
            assert rows
            # Compare with the attached route using the same finalized members.
            monkeypatch.setattr(dataset_lifecycle_sql, "_ATTACHED_OBSERVATION_LIMIT", 4096)
            assert analyzer.execute_query("block")["rows"] == rows
    assert created
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    assert not list(temp_root.iterdir())
    assert all(not path.exists() and not path.parent.exists() for path in created)
    assert hashes(root) == before
    temp_root.rmdir()


def test_installed_console_launcher_queries_special_paths_and_reports_json_errors(tmp_path, readonly_dataset):
    # Exercise the real generated console launcher, including Windows .exe, not
    # CliRunner or python -m. Clean-wheel acceptance separately checks packaging.
    launcher = Path(sysconfig.get_path("scripts")) / ("pt-snap.exe" if os.name == "nt" else "pt-snap")
    assert launcher.is_file(), f"Install the package in {sys.executable} before testing its launcher"
    env = os.environ.copy()
    env.pop("__PYVENV_LAUNCHER__", None)
    env["PYTHONPATH"] = str(ROOT / "src")  # Select this worktree in shared editable dev installs.
    env["PYTHONUTF8"] = "1"
    before = hashes(readonly_dataset)

    def run(*arguments):
        return subprocess.run(
            [str(launcher), *arguments],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )

    version = run("--version")
    assert version.returncode == 0, version.stderr
    assert "pt-snap" in version.stdout.lower()
    result = run("query", str(readonly_dataset), "--template-use", "memory_peak", "--json")
    assert result.returncode == 0 and result.stderr == "", result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True and payload["rows"]
    missing = run("overview", str(tmp_path / "missing #100% 数据.db"), "--json")
    assert missing.returncode == 1 and missing.stdout == "", missing.stdout + missing.stderr
    error = json.loads(missing.stderr)
    assert error["ok"] is False and error["error"]["code"] == "DATABASE_NOT_FOUND"
    assert hashes(readonly_dataset) == before
    assert not (tmp_path / ".pt-snap").exists()
    assert not any(readonly_dataset.rglob("*-journal"))
