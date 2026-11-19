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

"""Offline acceptance: generated SQLite is synthetic, NEVER original-producer/GUI evidence."""

import dataclasses
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from typer.testing import CliRunner

from benchmarks.interop_acceptance import (
    REVISION,
    cli_acceptance,
    compare_artifact,
    compare_forward,
    inventory,
    physical_oracle,
    read_json,
    verify_receipt,
)
from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.cli import app
from pt_snap_cli.core.common.errors import ImportExecutionError
from pt_snap_cli.core.dataset.dataset_support import DATASET_SUPPORT
from pt_snap_cli.core.importing.import_service import ImportService
from test.core.test_dataset_attribution import add_frames, case
from test.core.test_msinsight_export import options


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)


@pytest.mark.parametrize("device", [0, 2])
def test_text_contracts_against_independent_physical_reference(tmp_path, device):
    root = case(tmp_path)
    result = compare_artifact(root, device, tmp_path / "reference.db")
    # This independent physical reference has text stacks only. Frame paths
    # have separate real-import differential coverage against a structured DB.
    assert set(result["templates"]) == set(DATASET_SUPPORT) - {"active_memory_frame_tree_at_event"}
    assert result["real_events"] == 16 and result["canonical_lifecycles"] == 10
    assert result["raw_block_rows"] == 61 and result["repeated_block_rows"] == 51
    assert result["GUI"] == "human-deferred/pending/not-run"
    assert result["original_producer"] == "not-run by this runner"


def test_hash_first_receipt_rejects_changed_members_and_dangling_sidecars(tmp_path):
    root = case(tmp_path)
    receipt = {"revision": REVISION, "artifactHashes": inventory(root)}
    verify_receipt(root, receipt)
    manifest = root / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum"):
        verify_receipt(root, receipt)
    receipt["artifactHashes"] = inventory(root)
    (root / "device_0/slice_00000.db-wal").symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="symlink"):
        verify_receipt(root, receipt)


def test_reference_is_exclusive_and_ambiguous_address_is_not_identity(tmp_path):
    root = case(tmp_path)
    reference = tmp_path / "reference.db"
    reference.write_bytes(b"do not replace")
    with pytest.raises(FileExistsError):
        compare_artifact(root, 0, reference)
    assert reference.read_bytes() == b"do not replace"
    oracle = physical_oracle(root, 0)
    assert len([b for b in oracle["blocks"].values() if b["address"] == 100]) == 2
    # Lifecycle 0 completes at event 10: its last real observation is slice 5.
    with closing(sqlite3.connect(root / "device_0/slice_00005.db")) as conn, conn:
        changed = conn.execute("UPDATE block_0 SET size=size+1 WHERE id=0")
        assert changed.rowcount == 1
    with pytest.raises(ValueError, match="Ambiguous"):
        physical_oracle(root, 0)


def test_whole_dataset_focus_cli_api_report_and_truncated_scope(tmp_path):
    root = case(tmp_path)
    before = inventory(root)
    runner = CliRunner()
    focus = runner.invoke(app, ["focus", str(root / "manifest.json"), "--device", "0", "--json"])
    assert focus.exit_code == 0, focus.output
    query_args = [
        "query",
        "--template-use",
        "event",
        "--params",
        '{"order_by":"active","order_dir":"DESC","limit":3,"offset":1}',
        "-n",
        "2",
        "--exact-total",
        "--json",
    ]
    cli = runner.invoke(app, query_args)
    assert cli.exit_code == 0, cli.output
    result = json.loads(cli.output)
    with SnapshotAnalyzer(root) as analyzer:
        api = analyzer.execute_query(
            "event",
            {"order_by": "active", "order_dir": "DESC", "limit": 3, "offset": 1},
            device_id=0,
            max_rows=2,
            exact_total=True,
        )
        for key in ("rows", "total", "has_more", "truncated", "total_is_exact", "scope"):
            assert result[key] == api[key]
        assert result["scope"]["range_complete"] and result["truncated"]
        assert analyzer.get_database_overview()["import_metadata"]["reason"] == "metadata_missing"
    report = runner.invoke(
        app,
        [
            "report",
            "peak-memory",
            str(root),
            "--device",
            "0",
            "--metric",
            "reserved",
            "--start-id",
            "4",
            "--end-id",
            "15",
            "--limit",
            "-1",
            "--json",
        ],
    )
    assert report.exit_code == 0, report.output
    data = json.loads(report.output)
    assert data["source_coverage"]["allocation_source_complete"]
    assert data["scope"]["range_complete"]
    assert inventory(root) == before


@pytest.mark.parametrize("version,corrupt", [(1, None), (999, None), (1, "gap"), (1, "absent")])
def test_reader_only_frames_evidence_is_distinct_from_original_text(tmp_path, version, corrupt):
    root = case(tmp_path)
    frame = add_frames(root, version, corrupt)
    with SnapshotAnalyzer(root) as analyzer:
        row = analyzer.execute_query("event", {"id": 0, "stack_bytes": 0})["rows"][0]
        if version == 1 and corrupt is None:
            assert row["frames"] == [frame, frame, {"name": "event:0"}]
        else:
            assert row["frames"] is None and row["frames_status"] == "text_only"


def test_compatible_owned_cache_reuse_and_external_force_preserve_actual_bytes(tmp_path):
    request = dataclasses.replace(options(tmp_path, focus=False), set_focus=False)
    service = ImportService()
    result = service.import_snapshot(request)
    before = inventory(result.db_path)
    assert service.import_snapshot(request).reused
    assert service.import_snapshot(dataclasses.replace(request, force=True)).reused
    manifest = result.db_path / "manifest.json"
    raw = json.loads(manifest.read_text())
    raw.pop("ptSnap")  # external original-shaped cache, not our ownership attestation
    manifest.write_text(json.dumps(raw))
    external = inventory(result.db_path)
    reused = service.import_snapshot(dataclasses.replace(request, force=True))
    assert reused.reused and reused.metadata is None
    assert inventory(result.db_path) == external
    # Lightweight reuse accepts content edits and must preserve the edited bytes.
    with closing(sqlite3.connect(result.db_path / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE block_0 SET size=size+1")
    edited = inventory(result.db_path)
    assert service.import_snapshot(dataclasses.replace(request, force=True)).reused
    assert inventory(result.db_path) == edited
    # Structural damage must still be rejected without replacing the artifact.
    with closing(sqlite3.connect(result.db_path / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("DROP TABLE block_0")
    invalid = inventory(result.db_path)
    with pytest.raises(ImportExecutionError, match="preserv"):
        service.import_snapshot(dataclasses.replace(request, force=True))
    assert inventory(result.db_path) == invalid
    assert before != external


@pytest.mark.parametrize("kind", ["trace", "block", "dictionary"])
def test_physical_row_bounds_include_negative_trace_and_dictionary(tmp_path, kind):
    root = case(tmp_path)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        if kind == "trace":
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,2,0,0,0,0,0,0,'')",
                ((-100 - n,) for n in range(20001)),
            )
        elif kind == "block":
            conn.executemany("INSERT INTO block_0 VALUES (?,0,0,0,1,-1,-1)", ((-100 - n,) for n in range(20001)))
        else:
            conn.executemany(
                "INSERT INTO dictionary VALUES ('extra','extra',?,'x')",
                ((str(n),) for n in range(257)),
            )
    with pytest.raises(ValueError, match="20000|256 rows"):
        physical_oracle(root, 0)


def test_regular_bounded_json_source_and_inventory_before_materialization(tmp_path, monkeypatch):
    large = tmp_path / "large.json"
    large.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        read_json(large)
    with pytest.raises(ValueError, match="regular"):
        read_json(tmp_path)
    large.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError, match="Duplicate"):
        read_json(large)
    root = case(tmp_path)
    receipt = {"revision": REVISION, "artifactHashes": inventory(root)}
    source = tmp_path / "too-large.pkl"
    source.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="small hash-only"):
        verify_receipt(root, receipt, source)
    for n in range(257):
        (root / f"extra-{n}").touch()
    with pytest.raises(ValueError, match="256-entry"):
        inventory(root)


def test_acceptance_output_cannot_mutate_an_input_artifact(tmp_path):
    root = case(tmp_path)
    before = inventory(root)
    with pytest.raises(ValueError, match="overlap"):
        compare_artifact(root, 0, root / "new-reference.db")
    assert inventory(root) == before


def test_forward_physical_contract_detects_changed_observation(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    original = case(first)
    compatible = case(second)
    assert compare_forward(original, compatible, 0)["status"] == "passed"
    with closing(sqlite3.connect(compatible / "device_0/slice_00007.db")) as conn, conn:
        conn.execute("UPDATE block_0 SET state=0 WHERE id=3")
    with pytest.raises(AssertionError, match="forward physical"):
        compare_forward(original, compatible, 0)


@pytest.mark.parametrize(
    "change",
    [
        "stable_tokens",
        "size",
        "state",
        "multiplicity",
        "real_zero_id",
        "real_size",
        "unstable_token",
    ],
)
def test_forward_token_namespaces_preserve_all_fields_and_multiplicity(tmp_path, change):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    original, compatible = case(first), case(second)
    for index in range(8):
        with closing(sqlite3.connect(compatible / f"device_0/slice_{index:05d}.db")) as conn, conn:
            if change == "stable_tokens":
                conn.execute("UPDATE block_0 SET id=id-1000 WHERE id<0")
            elif change == "size":
                conn.execute("UPDATE block_0 SET size=size+1 WHERE id=-21")
            elif change == "state":
                conn.execute("UPDATE block_0 SET state=0 WHERE id=-21")
            elif change == "multiplicity":
                conn.execute(
                    "INSERT INTO block_0 SELECT -999,address,size,requestedSize,state,allocEventId,freeEventId FROM block_0 WHERE id=-21"
                )
            elif change == "real_zero_id":
                conn.execute("UPDATE block_0 SET id=999 WHERE id=0")
            elif change == "real_size":
                conn.execute("UPDATE block_0 SET size=size+1 WHERE id=0")
            elif index == 7:
                conn.execute("UPDATE block_0 SET address=address+1 WHERE id=-21")
    if change == "stable_tokens":
        assert "UNPROVED" in compare_forward(original, compatible, 0)["negative_identity"]
    else:
        with pytest.raises((AssertionError, ValueError), match="forward physical|Ambiguous"):
            compare_forward(original, compatible, 0)


def test_real_console_module_chain_writes_only_owned_test_focus(tmp_path):
    root = case(tmp_path)
    before = inventory(root)
    output = tmp_path / "evidence"
    output.mkdir()
    records = cli_acceptance(root, 0, output)
    assert len(records) == 3 and all(r["exit"] == 0 for r in records)
    assert (output / ".pt-snap/focus.json").is_file()
    assert inventory(root) == before


def test_cli_subprocess_relative_pythonpath_keeps_exact_worktree_source(tmp_path):
    root = case(tmp_path)
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"revision": REVISION, "artifactHashes": inventory(root)}))
    repository = Path(__file__).resolve().parents[1]
    output = tmp_path / "evidence"
    result = subprocess.run(
        [
            sys.executable,
            "benchmarks/interop_acceptance.py",
            "--artifact",
            str(root),
            "--receipt",
            str(receipt),
            "--device",
            "0",
            "--output",
            str(output),
        ],
        cwd=repository,
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    records = json.loads((output / "acceptance.json").read_text())["cli_acceptance"]
    assert len(records) == 3
    assert all(r["source_api"] == str(repository / "src/pt_snap_cli/api.py") for r in records)
    assert all(r["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(repository / "src") for r in records)
