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

"""ID pages skip counted matches without materializing the skipped prefix."""

import dataclasses
import json
import sqlite3
import time
from contextlib import closing

import pytest

from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver, QueryBudget
from pt_snap_cli.core.importing.import_service import ImportService
from test.core.test_dataset_attribution import case, standalone
from test.core.test_dataset_import import source_options
from test.core.test_dataset_source_reuse import framed_dataset
from test.test_dataset_focus import hashes, make_dataset


@pytest.fixture(scope="module", params=["inline", "native"])
def paired_dataset(tmp_path_factory, request):
    directory = tmp_path_factory.mktemp(f"id-page-{request.param}")
    if request.param == "inline":
        root = case(directory, devices=(0,))
        single = standalone(root, directory)
    else:
        options = dataclasses.replace(source_options(directory), set_focus=False)
        importer = ImportService()
        root = importer.import_snapshot(options).db_path
        single = importer.import_snapshot(dataclasses.replace(options, events_per_slice=None)).db_path
    resolved = DatasetResolver().inspect(root)
    return root, single, resolved.device(0)


WINDOWS = [
    (0, -1, None),
    (0, 0, None),
    (0, 1, None),
    (1, 0, None),
    (1, 3, None),
    (2, 3, None),
    (3, 2, None),
    (7, 3, None),
    (8, -1, None),
    (9, 1, None),
    (15, 1, None),
    (16, 3, None),
    (1_000_000, 3, None),
    (2, -1, 2),
    (2, 3, 1),
    (2, 0, 1),
    (2, -1, 0),
    (2, -1, -1),
    (-3, 2, None),
]


def assert_shared_rows(actual, expected):
    """Compare common columns while checking new dataset event frame evidence."""
    assert len(actual) == len(expected)
    for row, reference in zip(actual, expected, strict=True):
        assert {key: row[key] for key in reference} == reference
        if "frames_status" in row:
            assert row["frames_status"] == "ordered"
            assert isinstance(row["frames"], list)
            assert (
                "\n".join(f"{frame['filename']}:{frame['line']} {frame['name']}" for frame in reversed(row["frames"]))
                == reference["callstack"]
            )


@pytest.mark.parametrize("template", ["event", "allocation"])
@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_id_windows_match_standalone_with_filters_and_sparse_ids(paired_dataset, template, direction):
    root, single, device = paired_dataset
    low, high = device.slices[0].start_event_id, device.slices[-1].end_event_id
    filters = [
        {},
        {"min_allocated": 1},
        {"min_active": 1, "min_reserved": 1},
        {"min_id": low + 1, "max_id": high - 1},
        {"min_id": low + 1, "max_id": low + 1},
    ]
    if template == "event":
        filters += [{"action": 4}, {"action": 6}, {"action": 99}, {"stream": 1}]
    before = hashes(root)
    with closing(QueryService()) as service, closing(sqlite3.connect(single)) as conn:
        for extra in filters:
            range_low, range_high = extra.get("min_id", low), extra.get("max_id", high)
            first, last, count = conn.execute(
                "SELECT MIN(id), MAX(id), COUNT(*) FROM trace_entry_0 WHERE id>=? AND id<=?",
                [range_low, range_high],
            ).fetchone()
            for offset, limit, max_rows in WINDOWS:
                params = {
                    "min_id": low,
                    "max_id": high,
                    "order_by": "id",
                    "order_dir": direction,
                    "offset": offset,
                    "limit": limit,
                    **extra,
                }
                for exact in (False, True):
                    actual = service.execute_query(template, params, root, max_rows=max_rows, exact_total=exact)
                    expected = service.execute_query(template, params, single, max_rows=max_rows, exact_total=exact)
                    assert_shared_rows(actual.rows, expected.rows)
                    for field in ("total", "returned", "has_more", "truncated", "total_is_exact"):
                        assert getattr(actual, field) == getattr(expected, field), (params, field)
                    assert actual.scope["actual_range"] == {
                        "first_event_id": first,
                        "last_event_id": last,
                        "real_event_count": count,
                    }
                    assert actual.scope["boundary_events_included"] is False
    assert hashes(root) == before


@pytest.mark.parametrize("template", ["event", "allocation"])
@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_id_slice_pages_preserve_scope_and_exact_total(paired_dataset, template, direction):
    root, single, device = paired_dataset
    with closing(QueryService()) as service:
        for item in (device.slices[0], device.slices[2], device.slices[-1]):
            for offset in (0, 1, 2, 3):
                params = {
                    "min_id": item.start_event_id,
                    "max_id": item.end_event_id,
                    "order_by": "id",
                    "order_dir": direction,
                    "offset": offset,
                    "limit": 2,
                }
                actual = service.execute_query(template, params, root, slice_index=item.index, exact_total=True)
                expected = service.execute_query(template, params, single, exact_total=True)
                assert_shared_rows(actual.rows, expected.rows)
                assert actual.total == expected.total
                assert actual.has_more == expected.has_more
                assert actual.truncated == expected.truncated
                assert actual.scope["slice_indices"] == [item.index]
                assert actual.scope["actual_range"]["real_event_count"] == expected.total


@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_id_page_fetches_only_landing_and_following_matching_shards(tmp_path, monkeypatch, direction):
    root = make_dataset(tmp_path / "filtered", devices=(0,), slices=4)
    for member in root.glob("device_0/*.db"):
        with closing(sqlite3.connect(member)) as conn, conn:
            conn.execute("UPDATE trace_entry_0 SET action=5 WHERE id IN (0,1,3,4,6,7)")
    queries = []
    original = DatasetSourceResolver.read

    def observed(self, path, sql, values=None):
        if "ORDER BY t.id" in sql:
            queries.append((path.name, values[-2:]))
        return original(self, path, sql, values)

    monkeypatch.setattr(DatasetSourceResolver, "read", observed)
    budget = QueryBudget(None, time.monotonic(), max_work_rows=13)
    with closing(QueryService()) as service:
        result = service.execute_query(
            "event",
            {"action": 5, "order_dir": direction, "offset": 1, "limit": 3},
            root,
            exact_total=True,
            _budget=budget,
        )
    if direction == "ASC":
        assert [row["id"] for row in result.rows] == [1, 3, 4]
        assert queries == [
            ("slice_00000.db", [3, 1]),
            ("slice_00001.db", [2, 0]),
            ("slice_00002.db", [1, 0]),
        ]
    else:
        assert [row["id"] for row in result.rows] == [6, 4, 3]
        assert queries == [
            ("slice_00003.db", [3, 1]),
            ("slice_00002.db", [2, 0]),
            ("slice_00001.db", [1, 0]),
        ]
    assert result.total == 6 and result.has_more and result.truncated
    assert budget.work_rows == 4 + 3 + 3 + 3  # counts + page + sources + output
    assert result.scope["actual_range"]["real_event_count"] == 8


@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_id_page_hydrates_only_final_event_sources_and_ordered_frames(tmp_path, monkeypatch, direction):
    root = framed_dataset(tmp_path, 40)
    reads = []
    original = DatasetSourceResolver.read

    def observed(self, path, sql, values=None):
        rows = original(self, path, sql, values)
        reads.append((sql, values, len(rows)))
        return rows

    monkeypatch.setattr(DatasetSourceResolver, "read", observed)
    budget = QueryBudget(None, time.monotonic())
    with closing(QueryService()) as service:
        result = service.execute_query(
            "event", {"order_dir": direction, "offset": 20, "limit": 2}, root, _budget=budget
        )
    ids = [20, 21] if direction == "ASC" else [19, 18]
    assert [row["id"] for row in result.rows] == ids
    assert all(row["frames"] == [{"name": "f"}] for row in result.rows)
    for sql, values, _ in reads:
        if " IN (" in sql:
            assert set(values) == set(ids)
        if "ORDER BY t.id" in sql:
            assert "callstack" not in sql and "frame" not in sql
    assert budget.work_rows == sum(count for _, _, count in reads) + 2 == 18
    assert result.scope["source_coverage"]["events_resolved"] == 2
    assert result.scope["source_coverage"]["ordered_frame_events"] == 2


@pytest.mark.parametrize("template", ["event", "allocation"])
@pytest.mark.parametrize("offset,limit", [(2**63 - 1, 1), (2**63, 0), (1, 2**63 - 1)])
def test_id_window_preserves_int64_overflow_errors(tmp_path, template, offset, limit):
    root = make_dataset(tmp_path / "overflow", devices=(0,))
    with closing(QueryService()) as service:
        with pytest.raises(QueryExecutionError, match="too large"):
            service.execute_query(template, {"offset": offset, "limit": limit}, root)


@pytest.mark.parametrize("template", ["event", "allocation"])
def test_zero_page_fetches_only_charged_counts_and_keeps_more(tmp_path, template):
    root = make_dataset(tmp_path / "empty-page", devices=(0,))
    budget = QueryBudget(None, time.monotonic(), max_work_rows=3)
    with closing(QueryService()) as service:
        result = service.execute_query(template, {"offset": 2, "limit": 0}, root, exact_total=True, _budget=budget)
        assert result.rows == [] and result.total == 6
        assert result.has_more and result.truncated and result.total_is_exact
        assert budget.work_rows == 3
        with pytest.raises(QueryExecutionError, match="work budget"):
            service.execute_query(
                template,
                {"offset": 2, "limit": 0},
                root,
                _budget=QueryBudget(None, time.monotonic(), max_work_rows=2),
            )


@pytest.fixture(scope="module")
def million_event_dataset(tmp_path_factory):
    root = make_dataset(tmp_path_factory.mktemp("million-id-page") / "dataset", devices=(0,), slices=4)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    per_shard = 250_003
    manifest["eventsPerSlice"] = per_shard
    manifest["devices"]["0"]["eventCount"] = 4 * per_shard
    for item in manifest["devices"]["0"]["slices"]:
        low = item["index"] * per_shard
        high = low + per_shard - 1
        item.update(startEventId=low, endEventId=high)
        with closing(sqlite3.connect(root / item["file"])) as conn, conn:
            conn.execute("DELETE FROM trace_entry_0 WHERE id>=0")
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,4,100,8,0,8,8,16,'shared')",
                ((event,) for event in range(low, high + 1)),
            )
    manifest_path.write_text(json.dumps(manifest))
    return root


@pytest.mark.slow
@pytest.mark.parametrize("template", ["event", "allocation"])
@pytest.mark.parametrize("direction", ["ASC", "DESC"])
def test_million_offset_keeps_fetched_work_constant(million_event_dataset, template, direction):
    work = []
    with closing(QueryService()) as service:
        for offset in (0, 1_000_000):
            budget = QueryBudget(None, time.monotonic(), max_work_rows=19)
            result = service.execute_query(
                template,
                {"order_dir": direction, "offset": offset, "limit": 5},
                million_event_dataset,
                exact_total=True,
                _budget=budget,
            )
            expected = (
                list(range(offset, offset + 5))
                if direction == "ASC"
                else list(range(1_000_011 - offset, 1_000_006 - offset, -1))
            )
            assert [row["id"] for row in result.rows] == expected
            assert result.total == 1_000_012 and result.returned == 5
            assert result.has_more and result.truncated and result.total_is_exact
            assert result.scope["actual_range"]["real_event_count"] == 1_000_012
            work.append((budget.work_rows, budget.work_bytes))
    assert work[0][0] == work[1][0] == (19 if template == "event" else 14)
    assert max(size for _, size in work) < 10_000


@pytest.mark.parametrize("template", ["event", "allocation"])
def test_negative_limit_keeps_existing_dataset_unbounded_normalization(tmp_path, template):
    root = make_dataset(tmp_path / "negative-limit", devices=(0,))
    with closing(QueryService()) as service:
        expected = service.execute_query(template, {"offset": 2, "limit": -1}, root)
        actual = service.execute_query(template, {"offset": 2, "limit": -(2**100)}, root)
        assert actual.rows == expected.rows
        assert actual.returned == 4 and not actual.has_more
        assert actual.truncated and not actual.total_is_exact
