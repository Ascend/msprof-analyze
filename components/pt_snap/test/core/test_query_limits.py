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

"""Public immutable limits resolve once per operation, without weakening defaults."""

import dataclasses
import sqlite3
from contextlib import closing

import pytest

from pt_snap_cli.core import QueryLimits, QueryService, ReportService
from pt_snap_cli.core.common.errors import (
    InvalidParameterError,
    QueryExecutionError,
    QueryTimeoutError,
)
from pt_snap_cli.core.common.query_limits import resolve_query_limits
from pt_snap_cli.core.dataset.dataset_sources import QueryBudget
from test.core.test_dataset_attribution import case
from test.core.test_dataset_lifecycle_scratch import limited_connections, many_owners
from test.core.test_dataset_sql_pushdown import large_dataset
from test.test_dataset_focus import make_dataset

ENV_NAMES = (
    "PT_SNAP_MAX_WORK_ROWS",
    "PT_SNAP_MAX_WORK_BYTES",
    "PT_SNAP_MAX_SCRATCH_DB_BYTES",
)


@pytest.fixture(autouse=True)
def isolate_limits(monkeypatch):
    for name in (*ENV_NAMES, "PT_SNAP_QUERY_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_immutable_and_do_not_read_environment(monkeypatch):
    monkeypatch.setenv(ENV_NAMES[0], "1")
    limits = QueryLimits()
    assert dataclasses.asdict(limits) == {
        "max_work_rows": 100_000,
        "max_work_bytes": 64 * 1024**2,
        "max_scratch_db_bytes": 512 * 1024**2,
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        limits.max_work_rows = 1
    assert not hasattr(limits, "work_rows")
    assert QueryLimits.resolve().max_work_rows == 1


@pytest.mark.parametrize("field", ["max_work_rows", "max_work_bytes"])
@pytest.mark.parametrize("value", [True, False, 1.0, -1, 0, "10"])
def test_work_limits_require_positive_non_boolean_integers(field, value):
    with pytest.raises(InvalidParameterError, match=field):
        QueryLimits(**{field: value})


@pytest.mark.parametrize("value", [True, False, 4096.0, -1, 1, 4095, 4 * 1024**3 + 1, "0"])
def test_scratch_limits_are_validated_before_execution(value):
    with pytest.raises(InvalidParameterError, match="max_scratch_db_bytes"):
        QueryLimits(max_scratch_db_bytes=value)


@pytest.mark.parametrize("value", [0, 4096, 4097, 4 * 1024**3])
def test_scratch_disabled_and_boundary_values(value):
    assert QueryLimits(max_scratch_db_bytes=value).max_scratch_db_bytes == value


@pytest.mark.parametrize("name", ENV_NAMES)
@pytest.mark.parametrize("value", ["false", "1.5", "1e6", "unlimited", "64MiB", "1_000"])
def test_invalid_environment_is_a_domain_error(name, value, monkeypatch):
    monkeypatch.setenv(name, value)
    with pytest.raises(InvalidParameterError, match=name):
        QueryLimits.resolve()


def test_per_field_explicit_environment_default_precedence(monkeypatch):
    monkeypatch.setenv(ENV_NAMES[0], "invalid but overridden")
    monkeypatch.setenv(ENV_NAMES[1], " 123456 ")
    monkeypatch.setenv(ENV_NAMES[2], " ")
    assert QueryLimits.resolve(max_work_rows=200_000) == QueryLimits(200_000, 123456)
    assert resolve_query_limits(QueryLimits(55)) == QueryLimits(55)
    with pytest.raises(InvalidParameterError, match="QueryLimits"):
        resolve_query_limits(QueryBudget(None, 0))


def test_new_operations_have_fresh_counters_and_effective_metadata(tmp_path, monkeypatch):
    root = make_dataset(tmp_path / "reuse", devices=(0,))
    monkeypatch.setenv(ENV_NAMES[0], "1")
    limits = QueryLimits(100)
    with closing(QueryService(query_limits=limits)) as service:
        first = service.execute_query("event", db_path=root)
        second = service.execute_query("event", db_path=root)
        assert first == second
        assert first.scope["work_budget"]["max_rows"] == 100
        info = service.get_template_info("event").dataset_support
        assert info["work_limit_rows"] == 100
        assert info["max_scratch_db_bytes"] == limits.max_scratch_db_bytes
        with pytest.raises(QueryExecutionError, match="max_work_rows=1"):
            service.execute_query("event", db_path=root, query_limits=QueryLimits(1))
        assert service.execute_query("event", db_path=root) == first
        assert (
            service.get_template_info("event", query_limits=QueryLimits(200)).dataset_support["work_limit_rows"] == 200
        )
    with closing(QueryService()) as service:
        with pytest.raises(QueryExecutionError, match="max_work_rows=1"):
            service.execute_query("event", db_path=root)
        monkeypatch.setenv(ENV_NAMES[0], "100")
        assert service.execute_query("event", db_path=root).rows == first.rows


def test_byte_budget_counts_long_source_text_before_display_truncation(tmp_path):
    root = make_dataset(tmp_path / "long-text", devices=(0,), slices=1)
    with closing(sqlite3.connect(root / "device_0/slice_00000.db")) as conn, conn:
        conn.execute("UPDATE trace_entry_0 SET callstack=?", ("训练.py:42:run\n" * 1000,))
    with closing(QueryService()) as service:
        with pytest.raises(QueryExecutionError, match="max_work_bytes=1024"):
            service.execute_query(
                "event",
                {"stack_bytes": 0},
                db_path=root,
                query_limits=QueryLimits(max_work_bytes=1024),
            )
        result = service.execute_query(
            "event",
            {"stack_bytes": 0},
            db_path=root,
            query_limits=QueryLimits(max_work_bytes=1024 * 1024),
        )
    assert result.returned == 2
    assert result.scope["work_budget"]["max_bytes"] == 1024 * 1024


def test_report_limits_are_shared_cumulatively_and_reset_per_report(tmp_path, monkeypatch):
    root = case(tmp_path, devices=(0,))
    original = QueryService.execute_query
    stages = []

    def tracked(self, template, *args, **kwargs):
        budget = kwargs["_budget"]
        before = budget.work_rows
        result = original(self, template, *args, **kwargs)
        stages.append((budget, budget.work_rows - before))
        return result

    monkeypatch.setattr(QueryService, "execute_query", tracked)
    with closing(ReportService(query_limits=QueryLimits(1000))) as report_service:
        expected = report_service.peak_memory_report(root)
        assert len(stages) == 2 and stages[0][0] is stages[1][0]
        assert all(count > 0 for _, count in stages)
        maximum = max(count for _, count in stages)
        assert sum(count for _, count in stages) > maximum
        with pytest.raises(QueryExecutionError, match=f"max_work_rows={maximum}"):
            report_service.peak_memory_report(root, query_limits=QueryLimits(maximum))
        actual = report_service.peak_memory_report(root)
        assert actual == expected
        assert actual.scope["work_budget"]["max_rows"] == 1000


def test_report_deadline_is_not_restarted_with_explicit_limits(tmp_path, monkeypatch):
    root = case(tmp_path, devices=(0,))
    original = QueryService.execute_query

    def expire_after_peak(self, template, *args, **kwargs):
        result = original(self, template, *args, **kwargs)
        if template == "allocator_gap":
            kwargs["_budget"].started -= 100
        return result

    monkeypatch.setattr(QueryService, "execute_query", expire_after_peak)
    with closing(ReportService()) as service:
        with pytest.raises(QueryTimeoutError):
            service.peak_memory_report(root, query_limits=QueryLimits(1000), timeout_s=1)


def test_public_scratch_failure_reports_effective_limit_and_zero_keeps_work_cap(tmp_path, monkeypatch):
    root = many_owners(tmp_path)
    limited_connections(monkeypatch, 1)
    with closing(QueryService()) as service:
        with pytest.raises(QueryExecutionError, match="max_scratch_db_bytes=4096"):
            service.execute_query("block", db_path=root, query_limits=QueryLimits(1000, max_scratch_db_bytes=4096))
        expected = service.execute_query("block", db_path=root)
        disabled = service.execute_query("block", db_path=root, query_limits=QueryLimits(max_scratch_db_bytes=0))
        assert disabled.rows == expected.rows
        assert disabled.scope["work_budget"]["max_scratch_db_bytes"] == 0
        with pytest.raises(QueryExecutionError, match="max_work_rows=1"):
            service.execute_query("block", db_path=root, query_limits=QueryLimits(1, max_scratch_db_bytes=0))


@pytest.fixture(scope="module")
def large_limits_dataset(tmp_path_factory):
    return large_dataset(tmp_path_factory.mktemp("public-query-limits"))


@pytest.mark.parametrize(
    "template,params,returned",
    [
        ("event", {"offset": 100_000, "limit": 5, "order_by": "allocated", "order_dir": "ASC"}, 5),
        ("leak_detection", {"limit": -1}, 120_000),
    ],
)
def test_explicitly_raised_limits_enable_deep_pages_and_large_results(large_limits_dataset, template, params, returned):
    with closing(QueryService()) as service:
        with pytest.raises(QueryExecutionError, match="work budget"):
            service.execute_query(template, params, db_path=large_limits_dataset)
        result = service.execute_query(
            template,
            params,
            db_path=large_limits_dataset,
            exact_total=True,
            query_limits=QueryLimits(max_work_rows=1_000_000, max_work_bytes=512 * 1024**2),
        )
    assert result.total == 120_000 and result.returned == returned
    assert result.total_is_exact
    if template == "event":
        assert [row["id"] for row in result.rows] == list(range(100_000, 100_005))


def test_report_resolves_environment_once_for_all_steps(tmp_path, monkeypatch):
    root = case(tmp_path, devices=(0,))
    original = QueryService.execute_query
    monkeypatch.setenv(ENV_NAMES[0], "1000")

    def change_environment(self, template, *args, **kwargs):
        result = original(self, template, *args, **kwargs)
        if template == "allocator_gap":
            monkeypatch.setenv(ENV_NAMES[0], "invalid between report steps")
        return result

    monkeypatch.setattr(QueryService, "execute_query", change_environment)
    with closing(ReportService()) as service:
        result = service.peak_memory_report(root)
        assert result.scope["work_budget"]["max_rows"] == 1000
        with pytest.raises(InvalidParameterError, match=ENV_NAMES[0]):
            service.peak_memory_report(root)


@pytest.mark.parametrize("constructor", [QueryService, ReportService])
def test_service_constructor_rejects_mutable_budget_or_wrong_config(constructor):
    with pytest.raises(InvalidParameterError, match="QueryLimits"):
        constructor(query_limits=QueryBudget(None, 0))


def test_excessively_long_environment_integer_is_a_domain_error(monkeypatch):
    import sys

    if not hasattr(sys, "get_int_max_str_digits") or not sys.get_int_max_str_digits():
        pytest.skip("Interpreter has no configured integer-string conversion limit")
    monkeypatch.setenv(ENV_NAMES[0], "9" * (sys.get_int_max_str_digits() + 1))
    with pytest.raises(InvalidParameterError, match=ENV_NAMES[0]):
        QueryLimits.resolve()
