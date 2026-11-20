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

"""Synthetic schema-valid contracts, not evidence of an upstream replay defect."""

import copy
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.common.query_limits import QueryLimits
from pt_snap_cli.core.dataset.dataset_contract import validate_dataset
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_scratch as scratch
from pt_snap_cli.core.dataset.lifecycle import dataset_lifecycle_sql as sql
from pt_snap_cli.core.dataset.query import dataset_global
from test.test_dataset_focus import hashes, make_dataset


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.delenv("PT_SNAP_QUERY_TIMEOUT", raising=False)


def standalone(root, target):
    """Copy all real events and latest block observations into local SQL tables."""
    members = sorted(root.glob("device_0/*.db"))
    with closing(sqlite3.connect(target)) as out:
        with closing(sqlite3.connect(members[0])) as first:
            first.backup(out)
        with out:
            out.execute("DELETE FROM trace_entry_0 WHERE id<0")
            for path in members[1:]:
                with closing(sqlite3.connect(path)) as source:
                    out.executemany(
                        "INSERT INTO trace_entry_0 VALUES (?,?,?,?,?,?,?,?,?)",
                        source.execute("SELECT * FROM trace_entry_0 WHERE id>=0").fetchall(),
                    )
                    out.executemany(
                        "INSERT OR REPLACE INTO block_0 VALUES (?,?,?,?,?,?,?)",
                        source.execute("SELECT * FROM block_0").fetchall(),
                    )
    return target


def dataset_query(root, monkeypatch, route, template, params=None):
    """Force a real reducer on tiny inputs and prove it executed, without faking rows."""
    called = []
    original_attach = sql._AttachedSources.__enter__
    original_build = scratch._ScratchSources.build
    original_fallback = dataset_global._lifecycles

    def attached(database):
        result = original_attach(database)
        assert database.connection.execute("PRAGMA query_only").fetchone()[0] == 1
        assert {row[1] for row in database.connection.execute("PRAGMA database_list")} == {
            "main",
            "s0",
            "s1",
        }
        called.append("attached")
        return result

    def built(database, items, maximum):
        result = original_build(database, items, maximum)
        assert database.connection.execute("SELECT COUNT(*) FROM lifecycle_state").fetchone()[0]
        called.append("scratch")
        return result

    def fallback(*args):
        result = original_fallback(*args)
        called.append("fallback")
        return result

    with monkeypatch.context() as patch:
        # Zero ATTACH capacity selects the existing bounded Python path. Lowering
        # the observation threshold selects scratch without a huge fixture.
        patch.setattr(sql, "_attachment_limit", lambda: 0 if route == "fallback" else 2)
        patch.setattr(sql, "_ATTACHED_OBSERVATION_LIMIT", 0 if route == "scratch" else 4096)
        patch.setattr(sql._AttachedSources, "__enter__", attached)
        patch.setattr(scratch._ScratchSources, "build", built)
        patch.setattr(dataset_global, "_lifecycles", fallback)
        with SnapshotAnalyzer(root, query_limits=QueryLimits()) as analyzer:
            result = analyzer.execute_query(template, params, exact_total=True)
    assert called == [route]
    return result


def equivalent_dataset_results(results):
    normalized = []
    for result in results:
        value = copy.deepcopy(result)
        # Different execution plans legitimately perform different source reads.
        count = value["scope"]["source_coverage"].pop("source_queries")
        assert type(count) is int and count > 0
        normalized.append(value)
    assert normalized[1:] == [normalized[0]] * (len(normalized) - 1)


@pytest.mark.parametrize("state", [-1, 0, 1], ids=["inactive", "pending_free", "active"])
@pytest.mark.parametrize("free", [-1, 3], ids=["unknown_free", "completed_free"])
@pytest.mark.parametrize("terminal", [True, False], ids=["terminal", "earlier_only"])
def test_leak_state_contract_across_standalone_attached_scratch_and_fallback(
    tmp_path, monkeypatch, state, free, terminal
):
    root = make_dataset(tmp_path / "states", devices=(0,), slices=2)
    for index in range(2):
        with closing(sqlite3.connect(root / f"device_0/slice_{index:05d}.db")) as conn, conn:
            conn.execute("UPDATE trace_entry_0 SET action=5 WHERE id=1")
            conn.execute("UPDATE trace_entry_0 SET action=6 WHERE id=3")
            if index == 0 or terminal:
                conn.execute("INSERT INTO block_0 VALUES (0,100,8,8,?,0,?)", (state, free))
    # In particular, inactive + unknown-free is admitted by the format. This
    # crafted table combination makes no claim about what real replay produces.
    validate_dataset(root)
    single = standalone(root, tmp_path / "standalone.db")
    before = hashes(root)
    with SnapshotAnalyzer(single, query_limits=QueryLimits()) as analyzer:
        local = analyzer.execute_query("leak_detection", exact_total=True)
    assert [row["id"] for row in local["rows"]] == ([0] if free == -1 else [])
    assert all(set(row) == {"id", "address", "size", "allocEventId"} for row in local["rows"])
    results = [
        dataset_query(root, monkeypatch, route, "leak_detection") for route in ("attached", "scratch", "fallback")
    ]
    equivalent_dataset_results(results)
    expected = terminal and state in (0, 1) and free == -1
    for result in results:
        assert [row["id"] for row in result["rows"]] == ([0] if expected else [])
        assert result["total"] == int(expected) and result["total_is_exact"]
        assert not result["has_more"] and not result["truncated"]
        assert result["semantics_version"] == local["semantics_version"] == 1
        scope = result["scope"]
        assert scope["slice_indices"] == [0, 1] and scope["range_complete"]
        assert scope["boundary_events_included"] is False
        coverage = scope["source_coverage"]
        assert coverage["lifecycles"] == coverage["allocation_events_resolved"] == 1
        assert coverage["free_events_resolved"] == int(free == 3)
        assert coverage["allocation_source_complete"] and coverage["unproved_identities"] == 0
        for row in result["rows"]:
            assert row["terminal_survivor"] and row["observation_slice_index"] == 1
            assert row["state"] == state and row["state_scope"] == "latest_slice_observation"
            assert row["identity_status"] == "proved_allocation_event"
            assert row["allocation_source"]["slice_index"] == 0
            assert row["allocation_source"]["event"]["action"] == 4
            assert row["free_source"] is None and row["free_source_status"] == "live_or_unknown"
    assert hashes(root) == before


@pytest.mark.parametrize("boundary_action", [0, 2], ids=["segment_boundary", "segment_alloc_boundary"])
def test_unproved_collisions_stay_shard_local_but_proved_and_negative_tokens_merge(
    tmp_path, monkeypatch, boundary_action
):
    root = make_dataset(tmp_path / "identities", devices=(0,), slices=2)
    for index in range(2):
        with closing(sqlite3.connect(root / f"device_0/slice_{index:05d}.db")) as conn, conn:
            conn.execute("UPDATE trace_entry_0 SET action=5 WHERE id=1")
            conn.execute("UPDATE trace_entry_0 SET action=6 WHERE id=3")
            conn.execute("UPDATE trace_entry_0 SET action=? WHERE id=-1", (boundary_action,))
            # Same local ID, address and unproved allocation reference in both
            # shards must not become one proved lifecycle, even with equal bytes.
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)",
                [
                    (0, 100, 8, 8, -1, 0, 3),
                    (1, 100, 8, 8, 1, 1, -1),
                    (-1, 100, 8, 8, 1, -1, -1),
                    (-2, 100, 8, 8, 1, -1, -1),
                ],
            )
            if index == 1:
                conn.execute("INSERT INTO block_0 VALUES (2,100,8,8,0,2,-1)")
            assert conn.execute("SELECT action FROM trace_entry_0 WHERE id=-1").fetchone() == (boundary_action,)
    validate_dataset(root)
    single = standalone(root, tmp_path / "standalone.db")
    before = hashes(root)
    by_template = {}
    for template in ("block", "leak_detection", "freed_block_lifetime"):
        results = [dataset_query(root, monkeypatch, route, template) for route in ("attached", "scratch", "fallback")]
        equivalent_dataset_results(results)
        by_template[template] = results[0]
        coverage = results[0]["scope"]["source_coverage"]
        assert coverage["coverage_scope"] == "all_deduplicated_lifecycles_before_filters_and_page"
        assert coverage["lifecycles"] == 6
        assert coverage["allocation_events_resolved"] == 2
        assert coverage["free_events_resolved"] == 1
        assert coverage["unproved_identities"] == 2
        assert coverage["allocation_source_complete"] is False
    rows = by_template["block"]["rows"]
    unproved = [row for row in rows if row["id"] == 1]
    assert len(unproved) == 2
    for row in unproved:
        index = row["observation_slice_index"]
        assert row["lifecycle_id"].endswith(f":unproved:slice:{index}:block:1")
        assert row["identity_status"] == "unproved_shard_local"
        assert row["allocation_source"] is None and row["allocation_source_status"] == "missing"
        assert row["terminal_survivor"] == (index == 1)
    assert {row["observation_slice_index"] for row in unproved} == {0, 1}
    for row in rows:
        if row["id"] < 0:
            # A negative boundary event with the same numeric ID supplies no
            # allocation proof. The stable preexisting token remains separate.
            assert row["identity_status"] == "stable_negative_token"
            assert row["lifecycle_id"].endswith(f":preexisting:{row['id']}")
            assert row["allocation_source"] is None
            assert row["allocation_source_status"] == "unknown_preexisting"
    assert len({row["lifecycle_id"] for row in rows}) == 6
    assert [row["id"] for row in by_template["leak_detection"]["rows"]] == [2]
    assert by_template["freed_block_lifetime"]["rows"] == [
        {"lifetime_events": "<1k", "block_count": 1, "size_bytes": 8}
    ]
    with SnapshotAnalyzer(single, query_limits=QueryLimits()) as analyzer:
        # Local SQL checks the stored reference sign, not cross-shard source
        # proof: the unproved action=5 reference deliberately remains visible.
        local = analyzer.execute_query("leak_detection", exact_total=True)
        assert [row["id"] for row in local["rows"]] == [2, 1]
        assert analyzer.execute_query("block", exact_total=True)["total"] == 5
    assert hashes(root) == before


def test_public_metadata_explains_existing_scope_contract_without_version_change():
    with SnapshotAnalyzer(query_limits=QueryLimits()) as analyzer:
        leak = analyzer.get_template_info("leak_detection")
        block = analyzer.get_template_info("block")
        catalog = {entry["name"]: entry for entry in analyzer.list_capabilities()["templates"]}
    assert leak["semantics_version"] == 1
    assert leak["dataset_support"]["semantics"] == ("terminal_dataset_dynamic_survivors_not_confirmed_leaks")
    limits = " ".join(leak["interpretation_limits"])
    assert "Standalone SQL" in limits and "without state filtering or allocation-action proof" in limits
    assert "state IN (0,1)" in limits and "inactive plus unknown-free" in limits
    lifecycle = next(field for field in block["output_schema"] if field["column"] == "lifecycle_id")
    assert "unproved:slice:<index>:block:<id>" in " ".join(lifecycle["interpretation_limits"])
    for name, info in (("leak_detection", leak), ("block", block)):
        for field in (
            "semantics_version",
            "interpretation_limits",
            "output_schema",
            "dataset_support",
        ):
            assert catalog[name][field] == info[field]
