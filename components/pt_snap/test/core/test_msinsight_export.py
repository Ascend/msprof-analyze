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

"""Fixed interface contracts; GUI remains deferred, no vendor code execution."""

import copy
import dataclasses
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import _safe_call, app
from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.common.errors import ImportExecutionError, SourceChangedError
from pt_snap_cli.core.common.models import ImportOptions
from pt_snap_cli.core.dataset.dataset_contract import (
    ACTION_NAMES,
    BLOCK_COLUMNS,
    BLOCK_STATES,
    DICTIONARY_COLUMNS,
    MSINSIGHT_REVISION,
    TRACE_COLUMNS,
    validate_dataset,
)
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.importing.import_service import ImportService
from test.core.test_dataset_import import hashes
from test.snapshot.test_sharded_replay import lifecycle_data, write_source


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


def options(tmp_path, *, multiple=False, capacity=2, focus=True):
    data = lifecycle_data()
    data["device_traces"][0] = [e for e in data["device_traces"][0] if e["action"] != "oom"]
    if multiple:
        data["device_traces"] += [copy.deepcopy(data["device_traces"][0]), []]
        data["segments"] += [{**copy.deepcopy(s), "device": 1} for s in data["segments"]]
    return ImportOptions(
        write_source(tmp_path, data),
        tmp_path / "output",
        set_focus=focus,
        events_per_slice=capacity,
        format="msinsight",
    )


def rows(path, sql):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as conn:
        return conn.execute(sql).fetchall()


@pytest.mark.parametrize("capacity", [1, 2, 100, None])
@pytest.mark.parametrize("fmt", ["msinsight", "compatibility-v1"])
def test_physical_schema_inline_events_streams_stable_references_and_native_parity(tmp_path, capacity, fmt):
    request = dataclasses.replace(options(tmp_path, multiple=True, capacity=capacity), format=fmt)
    service = ImportService()
    result = service.import_snapshot(request)
    assert result.format == "compatibility-v1" and result.metadata.import_format_version == 1
    assert result.devices == (0, 1) and result.omitted_devices == (2,)
    assert result.focus_state.callstack_layout == "v1"
    manifest = json.loads((result.db_path / "manifest.json").read_text())
    assert manifest["sourceFile"] == str(request.snapshot_file.resolve())
    assert manifest["eventsPerSlice"] == (capacity or 500000)
    raw = request.snapshot_file.read_bytes()
    assert manifest["cacheHash"] == hashlib.sha256(b"mem_snapshot_parser_v3" + raw).hexdigest()
    assert result.metadata.source_sha256 == hashlib.sha256(raw).hexdigest() != manifest["cacheHash"]
    assert manifest["ptSnap"]["identity"]["targetRevision"] == MSINSIGHT_REVISION
    native = service.import_snapshot(
        dataclasses.replace(request, format=None, events_per_slice=capacity or 500000, set_focus=False)
    )
    compatible = DatasetResolver().inspect(result.db_path)
    native_dataset = DatasetResolver().inspect(native.db_path)
    assert validate_dataset(result.db_path).real_event_count == 10
    for device in (0, 1):
        lifetimes = {}
        for shard, native_shard in zip(
            compatible.device(device).slices, native_dataset.device(device).slices, strict=True
        ):
            path = result.db_path / shard.file
            for table, columns in (
                (f"trace_entry_{device}", TRACE_COLUMNS),
                (f"block_{device}", BLOCK_COLUMNS),
                ("dictionary", DICTIONARY_COLUMNS),
            ):
                schema = rows(path, f"PRAGMA table_info({table})")
                assert tuple((r[1], r[2]) for r in schema) == columns
                assert rows(path, f"SELECT type FROM sqlite_master WHERE name='{table}'") == [("table",)]
            assert not rows(path, "SELECT name FROM sqlite_master WHERE lower(name)='callstack'")
            assert rows(path, "SELECT import_format_version FROM pt_snap_metadata") == [(1,)]
            actual = rows(path, f"SELECT * FROM trace_entry_{device} ORDER BY id")
            expected = rows(
                native.db_path / native_shard.file,
                f"SELECT t.id,t.action,t.address,t.size,t.stream,t.allocated,t.active,t.reserved,c.callstack FROM trace_entry_{device} t JOIN callstack c ON c.id=t.callstackId ORDER BY t.id",
            )
            assert [row for row in actual if row[0] >= 0] == [row for row in expected if row[0] >= 0]
            assert sorted(row[1:] for row in actual if row[0] < 0) == sorted(row[1:] for row in expected if row[0] < 0)
            assert [r[0] for r in actual if r[0] >= 0] == list(range(shard.start_event_id, shard.end_event_id + 1))
            assert set(rows(path, 'SELECT "key","value" FROM dictionary WHERE "column"=\'action\'')) == {
                (str(k), v) for k, v in enumerate(ACTION_NAMES)
            }
            assert set(rows(path, 'SELECT "key","value" FROM dictionary WHERE "column"=\'state\'')) == {
                (str(k), v) for k, v in BLOCK_STATES
            }
            references = {r[0]: r[1:] for r in rows(path, "SELECT * FROM pt_snap_block_reference")}
            for block in rows(path, f"SELECT * FROM block_{device}"):
                signature = block[1:4] + block[5:]
                assert block[0] not in lifetimes or lifetimes[block[0]] == signature
                lifetimes[block[0]] = signature
                if block[6] >= 0:
                    assert block[6] == 3  # free_completed, NOT free_requested=2
                    assert references[block[0]][2] == "source.py:4 free_completed"
    before = hashes(result.db_path)
    with (
        SnapshotAnalyzer(result.db_path) as analyzer,
        SnapshotAnalyzer(native.db_path) as native_analyzer,
    ):
        assert analyzer.get_focus().callstack_layout == "v1"
        for device in (0, 1):
            for event in range(5):
                compatible_rows = analyzer.execute_query("event", {"id": event}, device_id=device)["rows"]
                native_rows = native_analyzer.execute_query("event", {"id": event}, device_id=device)["rows"]
                # Generation namespaces differ across physical formats; frame
                # digests and every event/frame value must remain equivalent.
                for event_rows in (compatible_rows, native_rows):
                    for row in event_rows:
                        for key in ("stack_id", "source_stack_id"):
                            row[key] = row[key].split(":frames:", 1)[-1]
                assert compatible_rows == native_rows
        assert not hasattr(analyzer, "import_snapshot")
    assert hashes(result.db_path) == before


def test_identical_complete_cache_reuses_without_loading_even_force(tmp_path, monkeypatch):
    request = options(tmp_path, focus=False)
    service = ImportService()
    first = service.import_snapshot(request)
    before = hashes(first.db_path)
    monkeypatch.setattr(
        service._msinsight_backend.replay,
        "stage",
        lambda *a, **k: pytest.fail("reused cache loaded pickle"),
    )
    for force in (False, True):
        reused = service.import_snapshot(dataclasses.replace(request, force=force))
        assert reused.reused and reused.metadata == first.metadata
    assert hashes(first.db_path) == before
    assert not (tmp_path / ".pt-snap").exists()


def test_consumer_tables_do_not_invalidate_compatible_cache(tmp_path, monkeypatch):
    request = options(tmp_path, focus=False)
    service = ImportService()
    first = service.import_snapshot(request)
    member = first.db_path / "device_0/slice_00000.db"
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.executescript(
            "CREATE TABLE memory_allocation_cache_v1_0(value TEXT);"
            "CREATE TABLE unrelated_consumer_cache(value TEXT);"
            "INSERT INTO unrelated_consumer_cache VALUES('keep');"
            "CREATE INDEX consumer_block_index ON block_0(address);"
            "ALTER TABLE trace_entry_0 ADD COLUMN consumer_note TEXT;"
            "ALTER TABLE block_0 ADD COLUMN consumer_note TEXT;"
        )
    (first.db_path / "parse.log").write_text("Insight log")
    monkeypatch.setattr(
        service._msinsight_backend.replay,
        "stage",
        lambda *a, **k: pytest.fail("cache hit must not replay"),
    )
    assert service.import_snapshot(request).reused
    with SnapshotAnalyzer(first.db_path) as analyzer:
        assert analyzer.execute_query("event", {"id": 0}, device_id=0)["rows"]
        assert analyzer.execute_query("block", {}, device_id=0)["rows"]
        assert analyzer.get_database_metadata()["status"] == "available"
    assert rows(member, "SELECT value FROM unrelated_consumer_cache") == [("keep",)]
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute("UPDATE block_0 SET size=size+1")
    assert service.import_snapshot(request).reused


def test_producer_metadata_reuses_without_replaying(tmp_path, monkeypatch):
    request = options(tmp_path, focus=False)
    service = ImportService()
    first = service.import_snapshot(request)
    path = first.db_path / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["parserCache"]
    path.write_text(json.dumps(manifest))
    before = hashes(first.db_path)
    monkeypatch.setattr(
        service._msinsight_backend.replay,
        "stage",
        lambda *a, **k: pytest.fail("producer seal cache hit must not replay"),
    )
    reused = service.import_snapshot(request)
    assert reused.reused and reused.metadata == first.metadata
    assert hashes(first.db_path) == before
    with SnapshotAnalyzer(first.db_path) as analyzer:
        assert analyzer.get_database_metadata()["status"] == "available"
    with closing(sqlite3.connect(first.db_path / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE block_0 SET size=size+1")
    assert service.import_snapshot(request).reused


@pytest.mark.parametrize("cli_capacity", [None, 2])
def test_external_insight_artifact_reuses_without_claiming_metadata(tmp_path, monkeypatch, cli_capacity):
    request = options(tmp_path, focus=False)
    service = ImportService()
    first = service.import_snapshot(request)
    path = first.db_path / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["ptSnap"]
    path.write_text(json.dumps(manifest))
    before = hashes(first.db_path)
    monkeypatch.setattr(
        service._msinsight_backend.replay,
        "stage",
        lambda *a, **k: pytest.fail("external cache hit must not replay"),
    )
    reused = service.import_snapshot(request)
    assert reused.reused and reused.metadata is None
    assert hashes(first.db_path) == before
    args = [
        "import",
        str(request.snapshot_file),
        "--format",
        "msinsight",
        "--output-dir",
        str(request.output_dir),
        "--no-focus",
        "--json",
    ]
    if cli_capacity is not None:
        args.extend(["--events-per-slice", str(cli_capacity)])
    output = CliRunner().invoke(app, args)
    assert output.exit_code == 0, output.output
    payload = json.loads(output.stdout)
    assert payload["metadata"] is None and payload["reused"] and payload["slice_count"] == 3
    with SnapshotAnalyzer(first.db_path) as analyzer:
        assert analyzer.execute_query("event", {"id": 4}, device_id=0)["rows"]
        assert analyzer.execute_query("block", {}, device_id=0)["rows"]
    assert hashes(first.db_path) == before


@pytest.mark.parametrize("sealed", [False, True])
@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("set_focus", [False, True])
@pytest.mark.parametrize(
    "slice_index,mutation,diagnostic",
    [
        (0, "UPDATE trace_entry_0 SET allocated=-1 WHERE id=0", "event_values"),
        (0, "UPDATE trace_entry_0 SET action=4 WHERE id<0", "event_action"),
        (0, "UPDATE block_0 SET requestedSize=-1", "block: invalid state/size"),
        (0, "UPDATE block_0 SET freeEventId=-2", "lifecycle"),
        (1, "UPDATE block_0 SET address=address+1 WHERE id=0", "block_identity"),
        (2, "UPDATE trace_entry_0 SET reserved=-1 WHERE id=4", "event_values"),
    ],
    ids=[
        "negative-bytes",
        "boundary-action",
        "block-size",
        "lifetime",
        "cross-slice",
        "last-slice",
    ],
)
def test_queries_validate_semantics_but_cache_import_does_not_scan(
    tmp_path, monkeypatch, sealed, external, set_focus, slice_index, mutation, diagnostic
):
    from pt_snap_cli.core.cache.snapshot_cache import seal_manifest, validate_cache
    from pt_snap_cli.core.common.errors import DatabaseSchemaError

    request = options(tmp_path, focus=False)
    service = ImportService()
    result = service.import_snapshot(request)
    path = result.db_path / "manifest.json"
    manifest = json.loads(path.read_text())
    if external:
        del manifest["ptSnap"]
    member = result.db_path / f"device_0/slice_{slice_index:05d}.db"
    with closing(sqlite3.connect(member)) as conn, conn:
        assert conn.execute(mutation).rowcount > 0
    seal_manifest(result.db_path, manifest)
    if not external:
        manifest["ptSnap"]["members"] = manifest["parserCache"]["members"]
    if not sealed:
        del manifest["parserCache"]
    path.write_text(json.dumps(manifest))
    # Cache admission checks structure; queries independently validate semantics.
    validate_cache(result.db_path, manifest["cacheHash"])
    with pytest.raises(DatabaseSchemaError, match=diagnostic):
        DatasetResolver().inspect(result.db_path)
    before = hashes(result.db_path)
    source_before = request.snapshot_file.read_bytes()
    focus = tmp_path / ".pt-snap/focus.json"
    focus.parent.mkdir()
    focus.write_bytes(b'{"db_path":"/previous/project.db","device_id":0}')
    focus_before = focus.read_bytes()
    monkeypatch.setattr(service._msinsight_backend.replay, "stage", lambda *a, **k: pytest.fail("must preserve"))
    for force in (False, True):
        assert service.import_snapshot(dataclasses.replace(request, force=force, set_focus=set_focus)).reused
        assert hashes(result.db_path) == before
        assert request.snapshot_file.read_bytes() == source_before
        if not set_focus:
            assert focus.read_bytes() == focus_before


@pytest.mark.parametrize("capacity", [None, 2, 3])
@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("sealed", [False, True])
def test_external_cache_honors_explicit_capacity(tmp_path, monkeypatch, capacity, force, sealed):
    request = options(tmp_path, focus=False)
    service = ImportService()
    result = service.import_snapshot(request)
    path = result.db_path / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["ptSnap"]
    if not sealed:
        del manifest["parserCache"]
    path.write_text(json.dumps(manifest))
    before = hashes(result.db_path)
    monkeypatch.setattr(service._msinsight_backend.replay, "stage", lambda *a, **k: pytest.fail("must not replay"))
    updated = dataclasses.replace(request, events_per_slice=capacity, force=force)
    if capacity == 3:
        with pytest.raises(ImportExecutionError, match="events_per_slice.*new output directory"):
            service.import_snapshot(updated)
    else:
        reused = service.import_snapshot(updated)
        assert reused.reused and reused.metadata is None and reused.slice_count == 3
    assert hashes(result.db_path) == before
    assert not (tmp_path / ".pt-snap").exists()


@pytest.mark.parametrize("force", [False, True])
def test_external_cache_cli_failure_preserves_artifact_and_focus(tmp_path, monkeypatch, force):
    request = options(tmp_path, focus=False)
    result = ImportService().import_snapshot(request)
    path = result.db_path / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["ptSnap"]
    path.write_text(json.dumps(manifest))
    before = hashes(result.db_path)
    source_before = request.snapshot_file.read_bytes()
    focus = tmp_path / ".pt-snap/focus.json"
    focus.parent.mkdir()
    focus.write_bytes(b'{"db_path":"/previous/project.db","device_id":0}')
    focus_before = focus.read_bytes()
    monkeypatch.setattr(
        "pt_snap_cli.core.importing.msinsight_export.MsinsightImportBackend.dump_to_dataset",
        lambda *a, **k: pytest.fail("rejected external cache must not replay or publish"),
    )
    args = [
        "import",
        str(request.snapshot_file),
        "--format",
        "msinsight",
        "--output-dir",
        str(request.output_dir),
        "--json",
    ]
    args.extend(["--events-per-slice", "3"])
    if force:
        args.append("--force")
    response = CliRunner().invoke(app, args)
    assert response.exit_code == 1, response.output
    assert response.stdout == ""
    error = json.loads(response.stderr)
    assert error["ok"] is False and error["error"]["code"] == "IMPORT_FAILED"
    assert "events_per_slice" in error["error"]["message"]
    assert "Traceback" not in response.stderr
    assert hashes(result.db_path) == before
    assert request.snapshot_file.read_bytes() == source_before
    assert focus.read_bytes() == focus_before


@pytest.mark.parametrize("external", [False, True])
def test_invalid_compatible_cache_is_preserved(tmp_path, monkeypatch, external):
    request = options(tmp_path, focus=False)
    service = ImportService()
    result = service.import_snapshot(request)
    path = result.db_path / "manifest.json"
    manifest = json.loads(path.read_text())
    if external:
        del manifest["ptSnap"]
    path.write_text("[" * 200000 + "0" + "]" * 200000)
    before = hashes(result.db_path)
    monkeypatch.setattr(service._msinsight_backend.replay, "stage", lambda *a, **k: pytest.fail("must preserve"))
    for force in (False, True):
        with pytest.raises(ImportExecutionError, match="preserved"):
            service.import_snapshot(dataclasses.replace(request, force=force))
        assert hashes(result.db_path) == before


def test_owned_cache_inspection_normalizes_deep_json(tmp_path):
    from pt_snap_cli.core.importing.msinsight_export import inspect_owned_cache

    (tmp_path / "manifest.json").write_text("[" * 200000 + "0" + "]" * 200000)
    with pytest.raises(ValueError, match="nesting"):
        inspect_owned_cache(tmp_path)


def test_query_and_metadata_reject_deep_manifest_without_traceback(tmp_path):
    from pt_snap_cli.core.common.errors import DatabaseSchemaError
    from pt_snap_cli.core.importing.import_metadata import ImportMetadataService

    result = ImportService().import_snapshot(options(tmp_path, focus=False))
    path = result.db_path / "manifest.json"
    path.write_text("[" * 200000 + "0" + "]" * 200000)
    before = hashes(result.db_path)
    with pytest.raises(DatabaseSchemaError):
        DatasetResolver().inspect(result.db_path)
    with pytest.raises(DatabaseSchemaError):
        ImportMetadataService().inspect(result.db_path)
    for command in ("overview", "metadata"):
        response = CliRunner().invoke(app, [command, str(result.db_path), "--json"])
        assert response.exit_code != 0
        assert "Traceback" not in response.output
    assert hashes(result.db_path) == before


def test_rollback_journal_has_an_explicit_diagnostic(tmp_path):
    request = options(tmp_path, focus=False)
    result = ImportService().import_snapshot(request)
    journal = result.db_path / "device_0/slice_00000.db-journal"
    journal.write_bytes(b"")
    before = hashes(result.db_path)
    with pytest.raises(ImportExecutionError, match="rollback journal.*retry later"):
        ImportService().import_snapshot(request)
    assert hashes(result.db_path) == before


def test_selected_device_export_still_supports_sealed_queries(tmp_path):
    request = dataclasses.replace(options(tmp_path, multiple=True, focus=False), device=1)
    result = ImportService().import_snapshot(request)
    assert result.devices == (1,)
    with SnapshotAnalyzer(result.db_path) as analyzer:
        assert analyzer.execute_query("event", {"id": 0}, device_id=1)["rows"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("ptSnap", [], "manifest.ptSnap: expected object"),
        ("identity", [], "manifest.ptSnap.identity: expected object"),
        ("exportContractVersion", 1, "Legacy export contract v1"),
    ],
)
def test_invalid_producer_extension_reports_context(tmp_path, field, value, message):
    request = options(tmp_path, focus=False)
    service = ImportService()
    result = service.import_snapshot(request)
    path = result.db_path / "manifest.json"
    manifest = json.loads(path.read_text())
    if field == "ptSnap":
        manifest[field] = value
    elif field == "identity":
        manifest["ptSnap"][field] = value
    else:
        manifest["ptSnap"]["identity"][field] = value
    path.write_text(json.dumps(manifest))
    before = hashes(result.db_path)
    with pytest.raises(ImportExecutionError, match=message):
        service.import_snapshot(request)
    assert hashes(result.db_path) == before


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("mutation", ["block", "trace"])
def test_resolver_accepts_valid_edits_without_digest_comparison(tmp_path, external, mutation):
    result = ImportService().import_snapshot(options(tmp_path, focus=False))
    if external:
        path = result.db_path / "manifest.json"
        manifest = json.loads(path.read_text())
        del manifest["ptSnap"]
        path.write_text(json.dumps(manifest))
    resolver = DatasetResolver()
    assert resolver.inspect(result.db_path) is not None
    member = result.db_path / "device_0/slice_00000.db"
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute(
            "DELETE FROM block_0 WHERE id=(SELECT MIN(id) FROM block_0)"
            if mutation == "block"
            else "UPDATE trace_entry_0 SET allocated=allocated+1"
        )
    before = hashes(result.db_path)
    assert resolver.inspect(result.db_path) is not None
    assert hashes(result.db_path) == before


@pytest.mark.parametrize("external", [False, True])
def test_live_consumer_wal_reuses_and_queries_committed_data(tmp_path, monkeypatch, external):
    request = options(tmp_path, focus=False)
    service = ImportService()
    result = service.import_snapshot(request)
    if external:
        path = result.db_path / "manifest.json"
        manifest = json.loads(path.read_text())
        del manifest["ptSnap"]
        path.write_text(json.dumps(manifest))
    monkeypatch.setattr(service._msinsight_backend.replay, "stage", lambda *a, **k: pytest.fail("must reuse"))
    member = result.db_path / "device_0/slice_00000.db"
    with closing(sqlite3.connect(member)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.executescript("CREATE TABLE consumer_data(value TEXT); INSERT INTO consumer_data VALUES('committed');")
        assert Path(str(member) + "-wal").exists()
        reused = service.import_snapshot(request)
        assert reused.reused and reused.metadata == (None if external else result.metadata)
        with SnapshotAnalyzer(result.db_path) as analyzer:
            assert analyzer.execute_query("event", {"id": 0}, device_id=0)["rows"]
        assert writer.execute("SELECT value FROM consumer_data").fetchall() == [("committed",)]
        # Cache reuse no longer scans base-table contents, including committed WAL.
        writer.execute("UPDATE block_0 SET size=size+1")
        writer.commit()
        assert service.import_snapshot(request).reused


def test_compatible_negative_ids_are_compact_and_boundary_ids_are_global(tmp_path):
    result = ImportService().import_snapshot(options(tmp_path, multiple=True, capacity=1, focus=False))
    manifest = json.loads((result.db_path / "manifest.json").read_text())
    boundary_ids = []
    for device, data in manifest["devices"].items():
        block_ids = set()
        for item in reversed(data["slices"]):
            path = result.db_path / item["file"]
            block_ids.update(row[0] for row in rows(path, f"SELECT id FROM block_{device} WHERE id<0"))
            boundary_ids.extend(
                row[0] for row in rows(path, f"SELECT id FROM trace_entry_{device} WHERE id<0 ORDER BY id DESC")
            )
            assert (
                rows(
                    path,
                    f"SELECT id FROM block_{device} EXCEPT SELECT blockId FROM pt_snap_block_reference",
                )
                == []
            )
        assert block_ids == set(range(-len(block_ids), 0))
    assert boundary_ids == list(range(-1, -len(boundary_ids) - 1, -1))


@pytest.mark.parametrize(
    "axis",
    [
        "source",
        "capacity",
        "device",
        "sourceFile",
        "hash",
        "version",
        "metadata",
        "last-member",
        "extra",
        "missing",
    ],
)
@pytest.mark.parametrize("force", [False, True])
def test_nonidentical_existing_output_never_replaced(tmp_path, axis, force):
    service = ImportService()
    request = options(tmp_path)
    first = service.import_snapshot(request)
    focus = (tmp_path / ".pt-snap/focus.json").read_bytes()
    manifest_path = first.db_path / "manifest.json"
    data = json.loads(manifest_path.read_text())
    if axis == "source":
        request.snapshot_file.write_bytes(request.snapshot_file.read_bytes() + b"trailing-source-bytes")
    elif axis == "capacity":
        request = dataclasses.replace(request, events_per_slice=3)
    elif axis == "device":
        request = dataclasses.replace(request, device=0)
    elif axis == "sourceFile":
        data["sourceFile"] = "/different/input.pkl"
    elif axis == "hash":
        data["cacheHash"] = "f" * 64
    elif axis == "version":
        data["ptSnap"]["identity"]["exportContractVersion"] += 1
    elif axis == "metadata":
        data["ptSnap"]["metadata"]["import_format_version"] = 2
    elif axis == "last-member":
        (first.db_path / "device_0/slice_00002.db").write_bytes(b"broken")
    elif axis == "extra":
        (first.db_path / "user-notes").write_text("preserve")
    else:
        # Test-owned member removal, never an external artifact.
        (first.db_path / "device_0/slice_00002.db").unlink()
    if axis in ("sourceFile", "hash", "version", "metadata"):
        manifest_path.write_text(json.dumps(data))
    before = hashes(first.db_path)
    with pytest.raises(ImportExecutionError, match="preserved even under --force"):
        service.import_snapshot(dataclasses.replace(request, force=force))
    assert hashes(first.db_path) == before
    assert (tmp_path / ".pt-snap/focus.json").read_bytes() == focus


@pytest.mark.parametrize("kind", ["empty", "unknown", "external", "file", "symlink", "dangling"])
def test_original_external_user_targets_preserved_under_force(tmp_path, kind):
    request = options(tmp_path)
    target = request.output_dir / "input.pkl.msinsight"
    target.parent.mkdir()
    if kind in ("symlink", "dangling"):
        victim = tmp_path / "victim"
        if kind == "symlink":
            victim.mkdir()
            (victim / "owner").write_text("safe")
        target.symlink_to(victim, target_is_directory=True)
    elif kind == "file":
        target.write_bytes(b"user bytes")
    else:
        target.mkdir()
        if kind == "external":
            # A genuine valid base artifact still lacks pt-snap ownership.
            from test.test_dataset_focus import make_dataset

            external = make_dataset(tmp_path / "external", devices=(0,), slices=1)
            import shutil

            shutil.copytree(external, target, dirs_exist_ok=True)
        if kind != "empty":
            (target / "owner").write_text("safe")
    before = hashes(target) if target.is_dir() else target.read_bytes() if target.is_file() else None
    with pytest.raises(ImportExecutionError):
        ImportService().import_snapshot(dataclasses.replace(request, force=True))
    assert target.exists() or target.is_symlink()
    if target.is_dir():
        assert hashes(target) == before
    if kind == "file":
        assert target.read_bytes() == before
    if kind == "symlink":
        assert (victim / "owner").read_text() == "safe"
    assert not (tmp_path / ".pt-snap").exists()


@pytest.mark.parametrize("kind", ["nonzero", "sparse", "oom", "unknown", "empty", "static-only", "empty-selection"])
def test_unsupported_input_fails_without_publication_or_focus(tmp_path, kind):
    request = options(tmp_path)
    data = lifecycle_data()
    data["device_traces"][0] = [e for e in data["device_traces"][0] if e["action"] != "oom"]
    if kind in ("nonzero", "sparse"):
        for index, event in enumerate(data["device_traces"][0]):
            event["id"] = index + 1 if kind == "nonzero" else index * 2
    elif kind in ("oom", "unknown"):
        data["device_traces"][0][0]["action"] = "oom" if kind == "oom" else "unknown"
    elif kind == "empty":
        data = {"segments": [], "device_traces": [[]]}
    elif kind == "static-only":
        data["device_traces"] = [[]]
    else:
        data["device_traces"].append([])
        request = dataclasses.replace(request, device=1)
    write_source(tmp_path, data)
    with pytest.raises(ImportExecutionError):
        ImportService().import_snapshot(request)
    assert not list(request.output_dir.iterdir())
    assert not (tmp_path / ".pt-snap").exists()


@pytest.mark.parametrize("phase", ["conversion", "metadata", "validation", "source", "focus", "rename", "race"])
def test_failures_preserve_old_focus_and_unknown_owner(tmp_path, monkeypatch, phase):
    request = options(tmp_path)
    old = tmp_path / ".pt-snap/focus.json"
    old.parent.mkdir()
    old.write_bytes(b'{"db_path":"/old/path","device_id":0}')
    before = old.read_bytes()
    service = ImportService()
    target = request.output_dir / "input.pkl.msinsight"

    def fail(*a, **k):
        raise OSError("injected " + phase)

    if phase == "conversion":
        monkeypatch.setattr("pt_snap_cli.core.importing.import_service.convert_shards", fail)
    elif phase == "metadata":
        monkeypatch.setattr(service._metadata_service, "write", fail)
    elif phase == "validation":
        monkeypatch.setattr("pt_snap_cli.core.importing.import_service.inspect_owned_cache", fail)
    elif phase == "source":
        monkeypatch.setattr(
            service,
            "_recheck_source",
            lambda *a: (_ for _ in ()).throw(SourceChangedError("source changed")),
        )
    elif phase == "focus":
        fs = FocusService()
        service._focus_service = fs

        def mutate(*a, **k):
            old.write_bytes(b"changed")
            fail()

        monkeypatch.setattr(fs._config, "write_project_focus", mutate)
    else:
        move = service._msinsight_backend._move

        def fault(source, destination, identity):
            if phase == "race":
                destination.mkdir()
                (destination / "owner").write_text("safe")
            else:
                move(source, destination, identity)
                fail()
            move(source, destination, identity)

        monkeypatch.setattr(service._msinsight_backend, "_move", fault)
    with pytest.raises(ImportExecutionError):
        service.import_snapshot(request)
    assert old.read_bytes() == before
    if phase == "race":
        assert (target / "owner").read_text() == "safe"
    else:
        assert not target.exists()


def test_cli_json_explicit_mode_default_adjacency_and_api_focus_parity(tmp_path, monkeypatch, capsys):
    request = options(tmp_path, capacity=None)
    args = ["import", str(request.snapshot_file), "--format", "msinsight", "--json"]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["format"] == "compatibility-v1" and data["slice_count"] == 1
    assert data["db_path"] == str(request.snapshot_file) + ".msinsight"
    with SnapshotAnalyzer(data["db_path"]) as analyzer:
        assert analyzer.get_focus().callstack_layout == data["focus_state"]["callstack_layout"] == "v1"
        cli = runner.invoke(
            app,
            ["query", data["db_path"], "--template-use", "event", "--params", '{"id":3}', "--json"],
        )
        assert cli.exit_code == 0
        assert json.loads(cli.output)["rows"] == analyzer.execute_query("event", {"id": 3})["rows"]
    reused = runner.invoke(app, [*args, "--force", "--no-focus"])
    assert reused.exit_code == 0 and json.loads(reused.output)["reused"]
    monkeypatch.setattr("sys.argv", ["pt-snap", *args, "--events-per-slice", "0"])
    assert _safe_call() != 0
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "INVALID_PARAMETER"
