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

"""Query executor for running SQL queries with template rendering."""

from __future__ import annotations

import copy
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Mapping, Tuple, Union

from jinja2 import Environment, StrictUndefined, Template, TemplateSyntaxError
from typing_extensions import TypedDict

from pt_snap_cli._compat import zip_strict
from pt_snap_cli.context import Context
from pt_snap_cli.query.config import QueryConfig, QueryTemplate

# How often the SQLite progress handler samples wall-clock time.
_PROGRESS_HANDLER_INTERVAL = 1000

# Match a trailing numeric LIMIT clause (with optional OFFSET) at the end of a SQL string.
# Numeric limits let the executor tighten template-owned caps when the caller provides
# a smaller max_rows value.
_TRAILING_LIMIT_RE = re.compile(
    r"\bLIMIT\s+(?P<limit>-?\d+)(?P<offset>\s+OFFSET\s+\d+)?(?P<suffix>\s*;?\s*)$",
    re.IGNORECASE | re.DOTALL,
)


def injected_row_limit(validated: Mapping[str, Any], max_rows: Union[int, None]) -> Union[int, None]:
    """Return the ``limit`` value ``QueryExecutor.render()`` injects.

    A positive ``max_rows`` becomes that value unless the template already
    declared a non-negative ``limit``, in which case the smaller one wins.
    Negative template limits (unlimited) stay out of the ``min()``.
    """
    if max_rows is None or max_rows <= 0:
        return None
    template_limit = validated.get("limit")
    if isinstance(template_limit, int) and template_limit >= 0:
        return min(template_limit, max_rows)
    return max_rows


def tighten_existing_limit(existing_limit: int, injected: int) -> int:
    """Apply the same rule ``QueryExecutor._apply_limit`` uses on a trailing LIMIT."""
    if existing_limit < 0:
        return injected
    return min(existing_limit, injected)


def trailing_sql_limit(sql: str) -> Union[int, None]:
    """Return the trailing numeric ``LIMIT``, or ``None`` when absent."""
    match = _TRAILING_LIMIT_RE.search(sql)
    if match is None:
        return None
    return int(match.group("limit"))


def bump_trailing_limit(sql: str, extra: int = 1) -> str:
    """Increase a finite trailing ``LIMIT`` by ``extra`` so callers can probe ``has_more``.

    Unlimited (``LIMIT -1``) and SQL with no trailing limit are left unchanged.
    """
    match = _TRAILING_LIMIT_RE.search(sql)
    if match is None:
        return sql
    existing_limit = int(match.group("limit"))
    if existing_limit < 0:
        return sql
    offset = match.group("offset") or ""
    suffix = match.group("suffix") or ""
    return f"{sql[: match.start()]}LIMIT {existing_limit + extra}{offset}{suffix}"


def reported_sql_limit(
    validated: Mapping[str, Any],
    max_rows: Union[int, None],
    parameters: Mapping[str, Any],
) -> Union[int, None]:
    """Trailing SQL LIMIT after the same merge ``render()`` injects.

    Inner caps such as ``top_n`` (often inside a CTE) are not trailing
    LIMIT clauses, so ``_apply_limit`` appends ``max_rows``. That appended
    value is what this helper reports; ``top_n`` stays its own parameter.
    ``parameters`` is the template parameter map so callers can pass it
    without a second helper; the merge itself reads ``validated``.
    """
    _ = parameters
    return injected_row_limit(validated, max_rows)


class _CancellationOptions(TypedDict, total=False):
    cancelled: Callable[[], bool]


def cancellation_options(cancelled: Union[Callable[[], bool], None]) -> _CancellationOptions:
    return {"cancelled": cancelled} if cancelled is not None else {}


class QueryExecutionError(Exception):
    """Raised when query execution fails."""

    pass


class QueryTimeoutError(QueryExecutionError):
    """Raised when a query exceeds its configured execution timeout."""

    pass


class TemplateRenderError(Exception):
    """Raised when template rendering fails."""

    pass


def _is_sqlite_interrupt(error: BaseException) -> bool:
    detail = str(error).lower()
    return "interrupted" in detail or "cancelled" in detail


@contextmanager
def _sqlite_timeout(
    conn: sqlite3.Connection,
    timeout_s: Union[float, None],
    cancelled: Union[Callable[[], bool], None] = None,
) -> Generator[None, None, None]:
    """Abort the current SQLite statement after ``timeout_s`` wall-clock seconds.

    Uses a progress handler so the row cap (``LIMIT`` / ``max_rows``) stays
    independent of execution time. ``timeout_s`` is None or non-positive when
    the query should run without a time bound. The handler is always cleared
    so persistent connections do not leak a deadline into the next statement.
    """
    if (timeout_s is None or timeout_s <= 0) and cancelled is None:
        yield
        return
    deadline = time.monotonic() + float(timeout_s) if timeout_s is not None and timeout_s > 0 else None

    def _handler() -> int:
        return int((cancelled is not None and cancelled()) or (deadline is not None and time.monotonic() >= deadline))

    conn.set_progress_handler(_handler, _PROGRESS_HANDLER_INTERVAL)
    try:
        yield
    finally:
        conn.set_progress_handler(None, 0)


class QueryExecutor:
    """Executes SQL queries with template rendering support.

    Packaged templates are owned by :mod:`pt_snap_cli.query.registry`, which
    loads them recursively (one category per subdirectory) at import time.
    ``_configs`` only holds templates attached to this executor at runtime via
    :meth:`load_config` or :meth:`register_template`; lookups consult those
    first and then fall back to the registry.
    """

    def __init__(self, context: Context):
        """Initialize query executor.

        Args:
            context: Database context for executing queries.
        """
        self._context = context
        self._configs: Dict[str, QueryConfig] = {}
        self._env = Environment(
            undefined=StrictUndefined,
            autoescape=False,
        )  # nosec B701 # Renders SQL, not HTML; HTML escaping would corrupt SQL operators.
        # Cache of compiled Jinja templates keyed by template name so that
        # long-lived executors (e.g. a long-lived SnapshotAnalyzer) avoid re-parsing
        # identical template bodies on every query.
        self._compiled_cache: Dict[Tuple[str, str], Template] = {}

    def _compiled_template(self, template: QueryTemplate, sql: Union[str, None] = None) -> Template:
        """Return the cached compiled Jinja template for ``sql``.

        Compiles and caches on first access so repeat renders skip the
        ``Environment.from_string`` parse step. Variant templates cache
        each layout body separately.
        """
        body = sql if sql is not None else template.query
        cache_key = (template.name, body)
        cached = self._compiled_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            compiled = self._env.from_string(body)
        except TemplateSyntaxError as e:
            raise TemplateRenderError(f"Template syntax error in '{template.name}': {e}") from e
        self._compiled_cache[cache_key] = compiled
        return compiled

    def _sql_for_layout(self, template: QueryTemplate) -> str:
        """Select the SQL body for the current database callstack layout."""
        sql = template.sql_for_layout(self._callstack_layout())
        if sql is not None:
            return sql
        error = self._callstack_layout_error()
        if error:
            raise QueryExecutionError(f"Query execution failed: {error}")
        layout = self._callstack_layout()
        if layout is None:
            raise QueryExecutionError(
                f"Query execution failed: template '{template.name}' needs a v1 "
                "or v2 callstack layout, but this database's trace tables have "
                "neither an inline callstack column nor callstackId"
            )
        raise QueryExecutionError(
            f"Query execution failed: template '{template.name}' has no SQL variant for callstack layout {layout}"
        )

    def _callstack_layout(self) -> Union[str, None]:
        context = getattr(self, "_context", None)
        if context is None:
            return None
        layout = getattr(context, "callstack_layout", None)
        return layout if isinstance(layout, str) else None

    def _callstack_layout_error(self) -> Union[str, None]:
        context = getattr(self, "_context", None)
        if context is None:
            return None
        error = getattr(context, "callstack_layout_error", None)
        return error if isinstance(error, str) and error else None

    def _apply_limit(self, sql: str, limit: int) -> str:
        """Tighten a trailing numeric LIMIT or append one when absent."""
        match = _TRAILING_LIMIT_RE.search(sql)
        if match is None:
            return self._append_limit(sql, limit)

        existing_limit = int(match.group("limit"))
        effective_limit = tighten_existing_limit(existing_limit, limit)
        if effective_limit == existing_limit:
            return sql

        offset = match.group("offset") or ""
        suffix = match.group("suffix") or ""
        return f"{sql[: match.start()]}LIMIT {effective_limit}{offset}{suffix}"

    def _append_limit(self, sql: str, limit: int) -> str:
        """Append a ``LIMIT`` clause to ``sql`` when one is not present."""
        trimmed = sql.rstrip()
        if trimmed.endswith(";"):
            trimmed = trimmed[:-1].rstrip()
        return f"{trimmed} LIMIT {int(limit)}"

    def _timeout_error(self, timeout_s: float) -> QueryTimeoutError:
        return QueryTimeoutError(f"Query timed out after {timeout_s} seconds")

    def _execution_error(self, error: sqlite3.OperationalError) -> QueryExecutionError:
        detail = str(error)
        if re.search(r"no such table: (?:frame|callstack_frame|callstack_frame_manifest)\b", detail):
            return QueryExecutionError(
                "Query execution failed: structured callstack frames are unavailable. "
                "Re-import the original snapshot with this version of pt-snap; "
                "legacy callstack text cannot reconstruct original frame fields reliably."
            )
        if "no such table: callstack" in detail or re.search(r"no such column: (?:[\w]+\.)?callstackId", detail):
            layout = self._callstack_layout()
            if layout == "v1":
                return QueryExecutionError(
                    "Query execution failed: this SQL requires callstackId, "
                    "but this database uses the v1 inline-callstack layout"
                )
            if layout == "v2":
                return QueryExecutionError(
                    "Query execution failed: this SQL expects the v1 inline-callstack "
                    "layout, but this database uses the v2 callstackId layout"
                )
            return QueryExecutionError(
                "Query execution failed: this SQL requires a recognized v1 or v2 callstack layout"
            )
        return QueryExecutionError(f"Query execution failed: {error}")

    def render(
        self,
        template: QueryTemplate,
        params: Dict[str, Any],
        device_id: Union[int, None] = None,
        max_rows: Union[int, None] = None,
    ) -> str:
        """Render SQL template with parameters.

        Args:
            template: Query template to render.
            params: Parameters for template rendering.
            device_id: Optional device ID for device-specific tables.
            max_rows: Optional upper bound on returned rows. When positive,
                the value is pushed down to SQL as a ``LIMIT`` clause and
                also injected as the ``limit`` template variable so
                templates that already expose a ``LIMIT {{ limit }}``
                parameter stay consistent. When the rendered SQL already
                ends with a ``LIMIT`` (e.g. from ``top_n`` or another
                template-defined cap), no second ``LIMIT`` is appended.

        Returns:
            Rendered SQL string.

        Raises:
            TemplateRenderError: If template rendering fails.
        """
        try:
            validated_params = template.validate_params(params)
        except (TypeError, ValueError) as e:
            raise TemplateRenderError(f"Failed to validate parameters for template '{template.name}': {e}") from e

        render_context = dict(validated_params)
        if device_id is not None:
            render_context["device_id"] = device_id
            render_context["device_trace_table"] = f"trace_entry_{device_id}"
            render_context["device_block_table"] = f"block_{device_id}"

        effective_limit = injected_row_limit(validated_params, max_rows)
        if effective_limit is not None:
            render_context["limit"] = effective_limit

        jinja_template = self._compiled_template(template, self._sql_for_layout(template))
        try:
            rendered_sql = jinja_template.render(render_context)
        except Exception as e:
            raise TemplateRenderError(f"Failed to render template '{template.name}': {e}") from e

        if effective_limit is not None:
            rendered_sql = self._apply_limit(rendered_sql, effective_limit)

        return rendered_sql

    def clone_for_context(self, context: Context) -> QueryExecutor:
        """Copy runtime registrations to a worker without borrowing its connection."""
        worker = QueryExecutor(context)
        worker._configs = copy.deepcopy(self._configs)
        return worker

    def execute(
        self,
        sql: str,
        params: Union[List[Any], None] = None,
        timeout_s: Union[float, None] = None,
        *,
        consume: Union[Callable[[List[Dict[str, Any]]], None], None] = None,
        cancelled: Union[Callable[[], bool], None] = None,
    ) -> List[Dict[str, Any]]:
        """Execute raw SQL query.

        Args:
            sql: SQL query string.
            params: Optional list of parameters.
            timeout_s: Optional wall-clock execution timeout in seconds.

        Returns:
            List of result rows as dictionaries.

        Raises:
            QueryTimeoutError: If ``timeout_s`` elapses before the statement finishes.
            QueryExecutionError: If query execution fails.
        """
        try:
            with self._context.connect() as conn:
                with _sqlite_timeout(conn, timeout_s, cancelled):
                    cursor = conn.cursor()
                    try:
                        if params:
                            cursor.execute(sql, params)
                        else:
                            cursor.execute(sql)
                        columns = [desc[0] for desc in cursor.description]
                        if consume is None:
                            # Preserve standalone behavior and its established
                            # cursor contract. Dataset reads explicitly opt in.
                            return [
                                dict(
                                    zip_strict(
                                        columns,
                                        row,
                                    )
                                )
                                for row in cursor.fetchall()
                            ]
                        result = []
                        while True:
                            batch = cursor.fetchmany(256)
                            if not batch:
                                break
                            rows = [
                                dict(
                                    zip_strict(
                                        columns,
                                        row,
                                    )
                                )
                                for row in batch
                            ]
                            consume(rows)
                            result.extend(rows)
                        return result
                    finally:
                        cursor.close()
        except sqlite3.OperationalError as e:
            if timeout_s is not None and timeout_s > 0 and _is_sqlite_interrupt(e):
                raise self._timeout_error(timeout_s) from e
            raise self._execution_error(e) from e
        except QueryExecutionError:
            # Domain failures (including timeouts and budget callbacks) are
            # already normalized; preserve their type, message, and cause.
            raise
        except Exception as e:
            raise QueryExecutionError(f"Query execution failed: {e}") from e

    def count(
        self,
        sql: str,
        timeout_s: Union[float, None] = None,
        *,
        cancelled: Union[Callable[[], bool], None] = None,
    ) -> int:
        """Count the rows produced by a rendered query without materializing them."""
        query = sql.strip().rstrip(";").rstrip()
        count_sql = f"SELECT COUNT(*) FROM ({query}) AS pt_snap_count"  # nosec B608 # Wraps the explicit read-only SQL API query, not an unescaped parameter value.
        try:
            with self._context.connect() as conn:
                with _sqlite_timeout(conn, timeout_s, cancelled):
                    cursor = conn.cursor()
                    cursor.execute(count_sql)
                    row = cursor.fetchone()
                    return int(row[0]) if row is not None else 0
        except sqlite3.OperationalError as e:
            if timeout_s is not None and timeout_s > 0 and _is_sqlite_interrupt(e):
                raise self._timeout_error(timeout_s) from e
            raise self._execution_error(e) from e
        except QueryExecutionError:
            # Domain failures (including timeouts and budget callbacks) are
            # already normalized; preserve their type, message, and cause.
            raise
        except Exception as e:
            raise QueryExecutionError(f"Query execution failed: {e}") from e

    def execute_template(
        self,
        name: str,
        params: Union[Dict[str, Any], None] = None,
        device_id: Union[int, None] = None,
        config_name: Union[str, None] = None,
        max_rows: Union[int, None] = None,
        timeout_s: Union[float, None] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a named template query.

        Args:
            name: Template name to execute.
            params: Parameters for template rendering.
            device_id: Optional device ID to filter results.
            config_name: Optional config name if multiple configs loaded.
            max_rows: Optional row limit pushed down to SQL when positive.
            timeout_s: Optional wall-clock execution timeout in seconds.

        Returns:
            List of result rows as dictionaries.

        Raises:
            QueryExecutionError: If template not found or execution fails.
            QueryTimeoutError: If ``timeout_s`` elapses before the statement finishes.
            TemplateRenderError: If template rendering fails.
        """
        rows, _, _ = self.execute_template_page(
            name,
            params=params,
            device_id=device_id,
            config_name=config_name,
            max_rows=max_rows,
            timeout_s=timeout_s,
            probe_has_more=False,
        )
        return rows

    def execute_template_page(
        self,
        name: str,
        params: Union[Dict[str, Any], None] = None,
        device_id: Union[int, None] = None,
        config_name: Union[str, None] = None,
        max_rows: Union[int, None] = None,
        timeout_s: Union[float, None] = None,
        *,
        probe_has_more: bool = True,
        cancelled: Union[Callable[[], bool], None] = None,
    ) -> Tuple[List[Dict[str, Any]], bool, Union[int, None]]:
        """Execute a named template and report whether more rows exist.

        When ``probe_has_more`` is true and the rendered SQL has a finite
        trailing ``LIMIT``, one extra row is fetched to set ``has_more``
        without a ``COUNT(*)``. The extra row is dropped from the returned
        page. Execution timeout is independent of that row cap.
        """
        template = self._find_template(name, config_name)
        if template is None:
            raise QueryExecutionError(f"Template not found: {name}")

        # Preserve the historical execute_template short-circuit: unknown
        # devices yield an empty page without rendering. CLI/API validate
        # devices first, so only direct executor callers see this path.
        if device_id is not None and device_id not in self._context.device_ids:
            return [], False, None

        sql = self.render(template, params or {}, device_id, max_rows=max_rows)
        display_limit = trailing_sql_limit(sql)
        applied_limit = display_limit if display_limit is not None and display_limit >= 0 else None
        fetch_sql = bump_trailing_limit(sql, 1) if probe_has_more and applied_limit is not None else sql
        rows = self.execute(
            fetch_sql,
            timeout_s=timeout_s,
            **cancellation_options(cancelled),
        )
        has_more = applied_limit is not None and len(rows) > applied_limit
        if has_more and applied_limit is not None:
            rows = rows[:applied_limit]
        return rows, has_more, applied_limit

    def count_template(
        self,
        name: str,
        params: Union[Dict[str, Any], None] = None,
        device_id: Union[int, None] = None,
        config_name: Union[str, None] = None,
        timeout_s: Union[float, None] = None,
        *,
        ignore_row_window: bool = False,
        cancelled: Union[Callable[[], bool], None] = None,
    ) -> int:
        """Count rows returned by a named template without materializing them.

        When ``ignore_row_window`` is true, template ``limit`` / ``offset`` /
        ``top_n`` caps are neutralized so the count is the matching set rather
        than the current page.
        """
        template = self._find_template(name, config_name)
        if template is None:
            raise QueryExecutionError(f"Template not found: {name}")

        if device_id is not None and device_id not in self._context.device_ids:
            return 0

        count_params = dict(params or {})
        if ignore_row_window:
            if "limit" in template.parameters:
                count_params["limit"] = -1
            if "offset" in template.parameters:
                count_params["offset"] = 0
            if "top_n" in template.parameters:
                count_params["top_n"] = -1
        sql = self.render(template, count_params, device_id)
        return self.count(sql, timeout_s=timeout_s, **cancellation_options(cancelled))

    def execute_on_all_devices(
        self,
        name: str,
        params: Union[Dict[str, Any], None] = None,
        config_name: Union[str, None] = None,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Execute template on all available devices.

        Args:
            name: Template name to execute.
            params: Parameters for template rendering.
            config_name: Optional config name if multiple configs loaded.

        Returns:
            Dictionary mapping device IDs to results.
        """
        template = self._find_template(name, config_name)
        if template is None:
            raise QueryExecutionError(f"Template not found: {name}")

        results = {}
        for device_id in self._context.device_ids:
            try:
                results[device_id] = self.execute_template(name, params, device_id, config_name)
            except QueryExecutionError:
                results[device_id] = []

        return results

    def _find_template(
        self,
        name: str,
        config_name: Union[str, None] = None,
    ) -> Union[QueryTemplate, None]:
        """Find a template by name across loaded configs and registry.

        Args:
            name: Template name.
            config_name: Optional config to search in.

        Returns:
            QueryTemplate or None if not found.
        """
        from pt_snap_cli.query.registry import get_query

        if config_name:
            config = self._configs.get(config_name)
            return config.get_query(name) if config else None

        for config in self._configs.values():
            template = config.get_query(name)
            if template:
                return template

        return get_query(name)

    def load_config(self, path: Union[str, Path], name: Union[str, None] = None) -> None:
        """Load additional config from file.

        Args:
            path: Path to YAML config file.
            name: Optional name for the config. Defaults to file stem.
        """
        config = QueryConfig.load_yaml(path)
        config_name = name or Path(path).stem
        self._configs[config_name] = config

    def register_template(self, template: QueryTemplate, config_name: str = "default") -> None:
        """Register a template directly.

        Args:
            template: Template to register.
            config_name: Config name to register under.
        """
        if config_name not in self._configs:
            self._configs[config_name] = QueryConfig()
        self._configs[config_name].queries[template.name] = template

    def has_runtime_template(self, name: str) -> bool:
        """A local override cannot inherit a packaged dataset merge contract."""
        return any(name in config.queries for config in self._configs.values())

    def list_templates(self) -> List[str]:
        """List all available template names.

        Returns:
            List of template names.
        """
        from pt_snap_cli.query.registry import list_queries

        names = []
        for config in self._configs.values():
            names.extend(config.list_queries())
        names.extend(list_queries())
        return list(set(names))

    def validate_output(
        self,
        result: List[Dict[str, Any]],
        schema: List[Dict[str, Any]],
    ) -> bool:
        """Validate query result against output schema.

        Args:
            result: Query result rows.
            schema: Expected output schema.

        Returns:
            True if result matches schema.
        """
        if not result:
            return True

        expected_columns = {col["column"] for col in schema}
        actual_columns = set(result[0].keys())

        return expected_columns.issubset(actual_columns)
