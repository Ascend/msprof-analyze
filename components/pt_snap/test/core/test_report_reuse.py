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

"""Report composition reuses one inspected generation and one cumulative budget."""

import dataclasses
import json
import sqlite3
from contextlib import closing

import pytest

import pt_snap_cli.core.analysis.query_service as query_service_module
from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.core.common.errors import (
    DatabaseSchemaError,
    QueryExecutionError,
    QueryTimeoutError,
)
from pt_snap_cli.core.dataset.dataset_resolver import DatasetResolver
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from pt_snap_cli.core.importing.import_service import ImportService
from test.core.test_dataset_attribution import case
from test.core.test_dataset_import import source_options
from test.test_dataset_focus import make_dataset

PEAK_FIELDS = {
    "peak_allocated",
    "peak_allocated_event_id",
    "peak_active",
    "peak_active_event_id",
    "peak_reserved",
    "peak_reserved_event_id",
}


def cycle_dataset(tmp_path, count):
    root = make_dataset(tmp_path / "cycles", devices=(0,), slices=2)
    width = count // 2
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["eventsPerSlice"] = width
    manifest["devices"]["0"]["eventCount"] = count
    for index, record in enumerate(manifest["devices"]["0"]["slices"]):
        start, end = index * width, (index + 1) * width - 1
        record.update(startEventId=start, endEventId=end)
        with closing(sqlite3.connect(root / record["file"])) as conn, conn:
            conn.execute("DELETE FROM trace_entry_0")
            conn.executemany(
                "INSERT INTO trace_entry_0 VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    (
                        event,
                        (4, 5, 6)[event % 3],
                        1048576 + 64 * (event - event % 3),
                        64,
                        0,
                        64 if event % 3 == 0 else 0,
                        64 if event % 3 < 2 else 0,
                        128,
                        "work.py:42:run",
                    )
                    for event in range(start, end + 1)
                ),
            )
            conn.executemany(
                "INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)",
                ((event, 1048576 + 64 * event, 64, 64, -1, event, event + 2) for event in range(start, end + 1, 3)),
            )
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


@pytest.mark.parametrize("count", [6000, 60000])
def test_report_inspects_once_and_scans_counters_once(tmp_path, monkeypatch, count):
    root = cycle_dataset(tmp_path, count)
    inspect, execute = DatasetResolver.inspect, QueryService.execute_query
    inspections, calls, focuses = [], [], []
    resolve_focus = FocusService.resolve_focus

    def tracked_focus(self, *args, **kwargs):
        result = resolve_focus(self, *args, **kwargs)
        focuses.append(result)
        return result

    def tracked_inspect(self, path, **kwargs):
        result = inspect(self, path, **kwargs)
        inspections.append(result)
        return result

    def tracked_execute(self, template, *args, **kwargs):
        calls.append((template, kwargs.get("_budget"), kwargs.get("_resolved")))
        return execute(self, template, *args, **kwargs)

    monkeypatch.setattr(FocusService, "resolve_focus", tracked_focus)
    monkeypatch.setattr(DatasetResolver, "inspect", tracked_inspect)
    monkeypatch.setattr(QueryService, "execute_query", tracked_execute)
    service = ReportService()
    try:
        result = service.peak_memory_report(root, timeout_s=10)
    finally:
        service.close()
    assert len(inspections) == len(focuses) == 1
    assert [name for name, _, _ in calls] == ["allocator_gap", "active_memory_callstack_at_event"]
    assert len({id(budget) for _, budget, _ in calls}) == 1
    assert len({id(resolution) for _, _, resolution in calls}) == 1
    assert calls[0][2].dataset is inspections[0]
    assert 0 < calls[0][1].work_rows < count + 20
    assert result.scope["fingerprint"] == inspections[0].fingerprint
    assert set(result.peak) == PEAK_FIELDS
    assert result.event_id == 0 and result.active_bytes_at_event == 64
    assert result.included_bytes == 64 and result.coverage_percent == 100


@pytest.mark.parametrize("metric,event,active", [("allocated", 3, 60), ("active", 4, 90), ("reserved", 1, 20)])
def test_report_projects_independent_earliest_peaks_and_same_event_counters(tmp_path, metric, event, active):
    root = case(tmp_path, devices=(0,))
    counters = {1: (10, 20, 900), 3: (80, 60, 100), 4: (30, 90, 100), 15: (80, 90, 900)}
    for path in root.glob("device_0/*.db"):
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("UPDATE trace_entry_0 SET allocated=1,active=1,reserved=1")
            for event_id, values in counters.items():
                conn.execute(
                    "UPDATE trace_entry_0 SET allocated=?,active=?,reserved=? WHERE id=?",
                    (*values, event_id),
                )
    service = ReportService()
    try:
        result = service.peak_memory_report(root, metric=metric)
    finally:
        service.close()
    assert set(result.peak) == PEAK_FIELDS
    assert result.peak == {
        "peak_allocated": 80,
        "peak_allocated_event_id": 3,
        "peak_active": 90,
        "peak_active_event_id": 4,
        "peak_reserved": 900,
        "peak_reserved_event_id": 1,
    }
    assert result.event_id == event and result.active_bytes_at_event == active
    assert result.allocator_gap[f"reserved_active_gap_at_{metric}_peak"] == counters[event][2] - active


def test_report_attribution_reduces_static_blocks_but_keeps_shared_work_limit(tmp_path, monkeypatch):
    root = cycle_dataset(tmp_path, 60000)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.executemany(
            "INSERT INTO block_0 VALUES (?,?,?,?,?,?,?)",
            ((-100000 - index, 2000000 + index, 1, 1, 1, -1, -1) for index in range(100001)),
        )
    with closing(ReportService()) as service:
        result = service.peak_memory_report(root)
        assert result.source_coverage["active_blocks"] == 100_002
        assert sum(row["block_count"] for row in result.callstack_groups) == 100_002
        consume = QueryBudget.consume

        def exhaust_after_gap(self, rows):
            if rows and "peak_allocated" in rows[0]:
                self.max_work_rows = self.work_rows + len(rows)
            consume(self, rows)

        # Reduced attribution still spends the SAME remaining report budget.
        monkeypatch.setattr(QueryBudget, "consume", exhaust_after_gap)
        with pytest.raises(QueryExecutionError, match="work budget"):
            service.peak_memory_report(root)


def test_report_deadline_is_not_restarted_for_attribution(tmp_path, monkeypatch):
    root = cycle_dataset(tmp_path, 6000)
    consume = QueryBudget.consume

    def expire_after_gap(self, rows):
        consume(self, rows)
        if rows and "peak_allocated" in rows[0]:
            self.started -= 100

    monkeypatch.setattr(QueryBudget, "consume", expire_after_gap)
    service = ReportService()
    try:
        with pytest.raises(QueryTimeoutError):
            service.peak_memory_report(root, timeout_s=10)
    finally:
        service.close()


@pytest.mark.parametrize("changed", ["member", "manifest"])
def test_report_rejects_a_generation_change_between_steps(tmp_path, monkeypatch, changed):
    root = cycle_dataset(tmp_path, 6000)
    execute = QueryService.execute_query
    calls = []

    def mutate_after_gap(self, template, *args, **kwargs):
        result = execute(self, template, *args, **kwargs)
        calls.append(template)
        if template == "allocator_gap":
            if changed == "member":
                with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
                    conn.execute("UPDATE trace_entry_0 SET active=999 WHERE id=0")
            else:
                path = root / "manifest.json"
                path.write_text(path.read_text() + "\n")
        return result

    monkeypatch.setattr(QueryService, "execute_query", mutate_after_gap)
    service = ReportService()
    try:
        with pytest.raises(DatabaseSchemaError, match="changed"):
            service.peak_memory_report(root)
    finally:
        service.close()
    assert calls == ["allocator_gap"]


def test_report_empty_trace_retains_six_fields_without_attribution(tmp_path, monkeypatch):
    root = cycle_dataset(tmp_path, 6000)
    member = root / "device_0/slice_00000.db"
    with closing(sqlite3.connect(member)) as conn, conn:
        conn.execute("DELETE FROM trace_entry_0")
        conn.execute("DELETE FROM block_0")
    service = ReportService()

    def unexpected_attribution(*args, **kwargs):
        pytest.fail("Empty peak must not invent an attribution event")

    monkeypatch.setattr(service, "event_attribution", unexpected_attribution)
    try:
        result = service.peak_memory_report(member)
    finally:
        service.close()
    assert result.peak == dict.fromkeys(PEAK_FIELDS)
    assert result.event_id is None and result.allocator_gap is None
    assert result.callstack_groups == [] and result.total_is_exact


@pytest.mark.parametrize("empty", [False, True])
def test_native_report_matches_standalone_and_preserves_empty_range(tmp_path, empty):
    request = dataclasses.replace(source_options(tmp_path), set_focus=False)
    importer = ImportService()
    root = importer.import_snapshot(request).db_path
    single = importer.import_snapshot(dataclasses.replace(request, events_per_slice=None)).db_path
    service = ReportService()
    params = {"start_id": 18, "end_id": 26} if empty else {}
    try:
        actual = service.peak_memory_report(root, **params)
        expected = service.peak_memory_report(single, **params)
    finally:
        service.close()
    assert actual.peak == expected.peak
    assert actual.allocator_gap == expected.allocator_gap
    assert actual.event_id == expected.event_id
    assert actual.active_bytes_at_event == expected.active_bytes_at_event
    assert actual.included_bytes == expected.included_bytes
    assert set(actual.peak) == PEAK_FIELDS
    if empty:
        assert actual.event_id is None and actual.callstack_groups == []
        assert actual.scope["actual_range"]["real_event_count"] == 0


def test_report_rejects_generation_change_during_peak_step(tmp_path, monkeypatch):
    root = cycle_dataset(tmp_path, 6000)
    global_query = query_service_module.global_query

    def mutate_after_scan(*args, **kwargs):
        result = global_query(*args, **kwargs)
        path = root / "manifest.json"
        path.write_text(path.read_text() + "\n")
        return result

    monkeypatch.setattr(query_service_module, "global_query", mutate_after_scan)
    service = ReportService()
    try:
        with pytest.raises(DatabaseSchemaError, match="changed"):
            service.peak_memory_report(root)
    finally:
        service.close()
