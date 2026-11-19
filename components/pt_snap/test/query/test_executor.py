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

"""Tests for query executor."""

import sqlite3
from contextlib import closing

import pytest

from pt_snap_cli.context import Context
from pt_snap_cli.query.config import QueryParameter, QueryTemplate
from pt_snap_cli.query.executor import (
    QueryExecutionError,
    QueryExecutor,
    QueryTimeoutError,
    TemplateRenderError,
)


@pytest.mark.parametrize("method", ["execute", "count"])
def test_sqlite_cancellation_without_timeout_clears_progress_handler(tmp_path, method):
    path = tmp_path / "cancel.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE dictionary (id INTEGER PRIMARY KEY, value TEXT)")
        conn.commit()
    context = Context(path, persistent=True)
    try:
        executor = QueryExecutor(context)
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks >= 3

        sql = (
            "WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) "
            "SELECT SUM(x) AS value FROM n"
        )
        with pytest.raises(QueryExecutionError, match="interrupted"):
            getattr(executor, method)(sql, cancelled=cancelled)
        assert checks == 3
        assert executor.execute("SELECT 42 AS value") == [{"value": 42}]
    finally:
        context.close()


def test_executor_clone_keeps_runtime_templates_without_sharing_registrations():
    first = QueryExecutor(context=None)
    first.register_template(QueryTemplate(name="custom", query="SELECT 1", parameters={}))
    worker = first.clone_for_context(None)
    assert worker.has_runtime_template("custom")
    worker.register_template(QueryTemplate(name="worker_only", query="SELECT 2", parameters={}))
    assert not first.has_runtime_template("worker_only")


class TestQueryExecutor:
    def test_render_simple_template(self):
        template = QueryTemplate(
            name="test",
            query="SELECT * FROM table WHERE size >= {{ min_size }}",
            parameters={
                "min_size": QueryParameter(name="min_size", type="int", default=0),
            },
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        sql = executor.render(template, {"min_size": 1024})
        assert "SELECT * FROM table WHERE size >= 1024" == sql

    def test_render_with_device_trace_table(self):
        template = QueryTemplate(
            name="test",
            query="SELECT * FROM {{ device_trace_table }} WHERE id = 1",
            parameters={},
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        sql = executor.render(template, {}, device_id=0)
        assert "SELECT * FROM trace_entry_0 WHERE id = 1" == sql

    def test_render_with_device_block_table(self):
        template = QueryTemplate(
            name="test",
            query="SELECT * FROM {{ device_block_table }} WHERE id = 1",
            parameters={},
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        sql = executor.render(template, {}, device_id=0)
        assert "SELECT * FROM block_0 WHERE id = 1" == sql

    def test_render_with_conditional(self):
        template = QueryTemplate(
            name="test",
            query="SELECT * FROM table{% if filter %} WHERE type = '{{ filter }}'{% endif %}",
            parameters={
                "filter": QueryParameter(name="filter", type="str", default=None),
            },
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        sql_with_filter = executor.render(template, {"filter": "alloc"})
        assert "WHERE type = 'alloc'" in sql_with_filter

        sql_without_filter = executor.render(template, {})
        assert "WHERE" not in sql_without_filter

    def test_render_invalid_syntax(self):
        template = QueryTemplate(
            name="test",
            query="SELECT * FROM table {% invalid %}",
            parameters={},
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        with pytest.raises(TemplateRenderError, match="Template syntax error"):
            executor.render(template, {})

    def test_render_missing_required_param(self):
        template = QueryTemplate(
            name="test",
            query="SELECT * FROM table WHERE id = {{ id }}",
            parameters={
                "id": QueryParameter(name="id", type="int", required=True),
            },
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        with pytest.raises(TemplateRenderError, match="Required parameter"):
            executor.render(template, {})

    def test_render_invalid_parameter_type_is_normalized(self):
        template = QueryTemplate(
            name="test",
            query="SELECT {{ count }}",
            parameters={
                "count": QueryParameter(name="count", type="int", required=True),
            },
        )
        executor = QueryExecutor(context=None)

        with pytest.raises(TemplateRenderError, match="cannot be converted to int"):
            executor.render(template, {"count": "invalid"})

    def test_validate_output(self):
        executor = QueryExecutor.__new__(QueryExecutor)

        schema = [
            {"column": "id", "type": "int"},
            {"column": "name", "type": "str"},
        ]

        result = [
            {"id": 1, "name": "test", "extra": "value"},
            {"id": 2, "name": "test2"},
        ]

        assert executor.validate_output(result, schema) is True

    def test_validate_output_missing_column(self):
        executor = QueryExecutor.__new__(QueryExecutor)

        schema = [
            {"column": "id", "type": "int"},
            {"column": "required_column", "type": "str"},
        ]

        result = [
            {"id": 1, "name": "test"},
        ]

        assert executor.validate_output(result, schema) is False

    def test_validate_output_empty_result(self):
        executor = QueryExecutor.__new__(QueryExecutor)

        schema = [
            {"column": "id", "type": "int"},
        ]

        assert executor.validate_output([], schema) is True

    def test_max_rows_appends_limit_when_template_has_none(self) -> None:
        """A positive max_rows must be pushed down as LIMIT for templates
        that don't already declare one (e.g. ``leak_detection``).
        """
        template = QueryTemplate(
            name="no_limit",
            query="SELECT id FROM t ORDER BY id",
            parameters={},
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        sql = executor.render(template, {}, max_rows=5)
        assert sql.endswith("LIMIT 5"), sql

    def test_max_rows_uses_template_limit_when_template_owns_one(self) -> None:
        """When the template already exposes ``limit`` via ``LIMIT {{ limit }}``
        the executor must inject the effective limit into that variable
        instead of appending a second LIMIT clause.
        """
        template = QueryTemplate(
            name="with_limit",
            query="SELECT id FROM t ORDER BY id LIMIT {{ limit|int }}",
            parameters={
                "limit": QueryParameter(name="limit", type="int", default=-1),
            },
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        sql = executor.render(template, {}, max_rows=5)
        # Exactly one LIMIT and it carries the pushed-down value.
        upper = sql.upper()
        assert upper.count("LIMIT") == 1
        assert sql.endswith("LIMIT 5"), sql

    def test_max_rows_zero_or_none_keeps_template_default(self) -> None:
        """``max_rows <= 0`` (including None) must not override the
        template's default LIMIT, so a template with ``LIMIT -1`` stays
        unlimited.
        """
        template = QueryTemplate(
            name="with_limit",
            query="SELECT id FROM t LIMIT {{ limit|int }}",
            parameters={
                "limit": QueryParameter(name="limit", type="int", default=-1),
            },
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        assert executor.render(template, {}, max_rows=None).endswith("LIMIT -1")
        assert executor.render(template, {}, max_rows=0).endswith("LIMIT -1")
        assert executor.render(template, {}, max_rows=-1).endswith("LIMIT -1")

    def test_max_rows_min_of_template_and_caller(self) -> None:
        """If the user also passes ``params={'limit': 3}``, the effective
        limit pushed to SQL is min(template_limit, max_rows).
        """
        template = QueryTemplate(
            name="with_limit",
            query="SELECT id FROM t LIMIT {{ limit|int }}",
            parameters={
                "limit": QueryParameter(name="limit", type="int", default=-1),
            },
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        # Template limit (3) is smaller than max_rows (10): use 3.
        assert executor.render(template, {"limit": 3}, max_rows=10).endswith("LIMIT 3")
        # max_rows (10) is smaller than template limit (50): use 10.
        assert executor.render(template, {"limit": 50}, max_rows=10).endswith("LIMIT 10")
        # Zero is an explicit empty result, not an unlimited value.
        assert executor.render(template, {"limit": 0}, max_rows=10).endswith("LIMIT 0")

    def test_max_rows_does_not_double_limit(self) -> None:
        """Templates that cap rows with a non-``limit`` variable (e.g.
        ``top_n``) keep their own LIMIT and the executor must not append
        a second one.
        """
        template = QueryTemplate(
            name="with_top_n",
            query="SELECT callstack FROM t GROUP BY callstack LIMIT {{ top_n|int }}",
            parameters={
                "top_n": QueryParameter(name="top_n", type="int", default=20),
            },
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        sql = executor.render(template, {}, max_rows=100)
        # ``LIMIT`` appears exactly once and reflects the template's own
        # ``top_n`` default, not the caller's ``max_rows``.
        assert sql.upper().count("LIMIT") == 1
        assert sql.endswith("LIMIT 20"), sql

    def test_max_rows_tightens_non_limit_template_cap(self) -> None:
        """A caller cap must also tighten templates that use ``top_n``."""
        template = QueryTemplate(
            name="with_top_n",
            query="SELECT callstack FROM t GROUP BY callstack LIMIT {{ top_n|int }}",
            parameters={
                "top_n": QueryParameter(name="top_n", type="int", default=20),
            },
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        sql = executor.render(template, {}, max_rows=5)

        assert sql.upper().count("LIMIT") == 1
        assert sql.endswith("LIMIT 5"), sql

    def test_reported_sql_limit_is_trailing_not_inner_top_n(self) -> None:
        """Inner top_n is not a trailing LIMIT; -n is appended."""
        from pt_snap_cli.query.executor import _TRAILING_LIMIT_RE, reported_sql_limit

        parameters = {"top_n": QueryParameter(name="top_n", type="int", default=20)}
        validated = {"top_n": 20}
        assert reported_sql_limit(validated, 50, parameters=parameters) == 50
        assert reported_sql_limit(validated, 5, parameters=parameters) == 5
        assert reported_sql_limit(validated, None, parameters=parameters) is None

        limit_parameters = {"limit": QueryParameter(name="limit", type="int", default=-1)}
        assert reported_sql_limit({"limit": -1}, 50, parameters=limit_parameters) == 50
        assert reported_sql_limit({"limit": 10}, 50, parameters=limit_parameters) == 10

        template = QueryTemplate(
            name="inner_top_n",
            query=("WITH x AS (SELECT 1 AS n LIMIT {{ top_n|int }}) SELECT * FROM x ORDER BY n"),
            parameters=parameters,
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}
        sql = executor.render(template, {}, max_rows=50)
        match = _TRAILING_LIMIT_RE.search(sql)
        assert match is not None
        assert int(match.group("limit")) == 50
        assert sql.upper().count("LIMIT") == 2

    def test_jinja_template_compiled_once_per_template(self) -> None:
        """Long-lived executors (a long-lived SnapshotAnalyzer) must avoid re-parsing the
        same template body on every render call.
        """
        template = QueryTemplate(
            name="cached",
            query="SELECT {{ device_id }}",
            parameters={},
        )
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        first = executor._compiled_template(template)
        second = executor._compiled_template(template)
        assert first is second
        assert ("cached", template.query) in executor._compiled_cache

    def test_jinja_cache_distinguishes_same_name_with_new_query(self) -> None:
        first_template = QueryTemplate(name="cached", query="SELECT 1")
        second_template = QueryTemplate(name="cached", query="SELECT 2")
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._env = QueryExecutor(context=None)._env
        executor._compiled_cache = {}

        first = executor._compiled_template(first_template)
        second = executor._compiled_template(second_template)

        assert first is not second
        assert len(executor._compiled_cache) == 2

    def test_list_templates(self):
        executor = QueryExecutor.__new__(QueryExecutor)
        executor._configs = {}
        executor._context = None

        template = QueryTemplate(name="test_query", query="SELECT 1")
        executor.register_template(template)

        assert "test_query" in executor.list_templates()

    def test_packaged_templates_resolve_through_registry_only(self):
        """Regression for issue #121: the executor owns no template directory.

        Packaged templates live in category subdirectories and are loaded by
        the registry; a freshly constructed executor must find them through the
        registry fallback while holding no configs of its own.
        """
        from pt_snap_cli.query.registry import _load_all_templates

        _load_all_templates()
        executor = QueryExecutor(context=None)

        assert executor._configs == {}
        assert executor._find_template("leak_detection") is not None
        assert "leak_detection" in executor.list_templates()

    def test_runtime_registered_template_shadows_registry(self):
        from pt_snap_cli.query.registry import _load_all_templates

        _load_all_templates()
        executor = QueryExecutor(context=None)
        override = QueryTemplate(name="leak_detection", query="SELECT 'override'")
        executor.register_template(override)

        assert executor._find_template("leak_detection") is override

    def test_execute_on_all_devices(self):
        """Test execute_on_all_devices runs template on each device."""
        mock_context = _make_mock_context(device_ids=[0, 1])
        executor = QueryExecutor(mock_context)
        executor.register_template(
            QueryTemplate(
                name="device_test",
                description="Test",
                query="SELECT {{ device_id }} as dev",
            )
        )

        results = executor.execute_on_all_devices("device_test")
        assert 0 in results
        assert 1 in results

    def test_execute_on_all_devices_template_not_found(self):
        """Test execute_on_all_devices raises for missing template."""
        mock_context = _make_mock_context(device_ids=[0])
        executor = QueryExecutor(mock_context)

        from pt_snap_cli.query.executor import QueryExecutionError

        with pytest.raises(QueryExecutionError, match="Template not found"):
            executor.execute_on_all_devices("nonexistent")

    def test_execute_on_all_devices_empty_device_list(self):
        """Test execute_on_all_devices with no devices returns empty dict."""
        mock_context = _make_mock_context(device_ids=[])
        executor = QueryExecutor(mock_context)
        executor.register_template(QueryTemplate(name="empty_test", description="Test", query="SELECT 1"))

        results = executor.execute_on_all_devices("empty_test")
        assert results == {}

    def test_legacy_callstack_schema_error_is_actionable(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("CREATE TABLE dictionary (table_name TEXT)")
            conn.execute("CREATE TABLE trace_entry_0 (id INTEGER, callstack TEXT)")
        executor = QueryExecutor(Context(db_path))
        executor.register_template(
            QueryTemplate(
                name="legacy_callstack",
                query="SELECT callstack FROM callstack",
            )
        )

        with pytest.raises(QueryExecutionError, match="v1 inline-callstack layout"):
            executor.execute_template("legacy_callstack", device_id=0)

    def test_qualified_legacy_callstack_schema_error_is_actionable(self, tmp_path):
        db_path = tmp_path / "legacy-qualified.db"
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("CREATE TABLE dictionary (table_name TEXT)")
            conn.execute("CREATE TABLE trace_entry_0 (id INTEGER)")
        executor = QueryExecutor(Context(db_path))
        executor.register_template(
            QueryTemplate(
                name="qualified_legacy_callstack",
                query="SELECT t.callstackId FROM trace_entry_0 t",
            )
        )

        with pytest.raises(QueryExecutionError, match="recognized v1 or v2"):
            executor.execute_template("qualified_legacy_callstack", device_id=0)

    def test_variant_template_uses_inline_sql_on_v1_database(self, tmp_path):
        db_path = tmp_path / "v1.db"
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("CREATE TABLE dictionary (table_name TEXT)")
            conn.execute("CREATE TABLE trace_entry_0 (id INTEGER, size INTEGER, callstack TEXT)")
            conn.execute("INSERT INTO trace_entry_0 (id, size, callstack) VALUES (1, 10, 'train.py:1')")
        executor = QueryExecutor(Context(db_path))
        executor.register_template(
            QueryTemplate(
                name="variant_event",
                query_variants={
                    "v1": "SELECT callstack FROM {{ device_trace_table }}",
                    "v2": "SELECT callstackId FROM {{ device_trace_table }}",
                },
            )
        )

        rows = executor.execute_template("variant_event", device_id=0)
        assert rows == [{"callstack": "train.py:1"}]


def _make_mock_context(device_ids: list[int]):
    """Create a mock Context with the given device IDs."""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.device_ids = device_ids
    return mock


@pytest.mark.parametrize("method", ["execute", "count"])
@pytest.mark.parametrize(
    "failure",
    [
        QueryExecutionError("Dataset query work budget exceeded; no partial global result."),
        QueryExecutionError("Query execution failed: already normalized"),
        QueryTimeoutError("Query timed out after 1 seconds"),
    ],
)
def test_existing_query_errors_cross_executor_unchanged(method, failure):
    context = _make_mock_context(device_ids=[0])
    context.connect.side_effect = failure
    with pytest.raises(type(failure)) as caught:
        getattr(QueryExecutor(context), method)("SELECT 1")
    assert caught.value is failure
    assert str(caught.value) == str(failure)


@pytest.mark.parametrize("method", ["execute", "count"])
@pytest.mark.parametrize("failure", [RuntimeError("backend failed"), sqlite3.OperationalError("broken SQL")])
def test_unknown_query_failures_are_wrapped_once(method, failure):
    context = _make_mock_context(device_ids=[0])
    context.connect.side_effect = failure
    with pytest.raises(QueryExecutionError) as caught:
        getattr(QueryExecutor(context), method)("SELECT 1")
    assert str(caught.value) == f"Query execution failed: {failure}"
    assert caught.value.__cause__ is failure


@pytest.mark.parametrize("error_type", [QueryExecutionError, QueryTimeoutError])
def test_consumer_domain_error_discards_prior_batches_and_keeps_connection_usable(error_type):
    context = _make_mock_context(device_ids=[0])
    failure = error_type("consumer budget exhausted")
    batches = []

    def consume(rows):
        batches.append(len(rows))
        if len(batches) == 2:
            raise failure

    with closing(sqlite3.connect(":memory:")) as connection:
        context.connect.return_value.__enter__.return_value = connection
        executor = QueryExecutor(context)
        with pytest.raises(error_type) as caught:
            executor.execute(
                "WITH RECURSIVE rows(id) AS (SELECT 0 UNION ALL "
                "SELECT id+1 FROM rows WHERE id<256) SELECT id FROM rows",
                timeout_s=10,
                consume=consume,
            )
        assert caught.value is failure
        assert batches == [256, 1]
        assert executor.execute("SELECT 42 AS answer") == [{"answer": 42}]
