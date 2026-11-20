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

"""Report command group, backed by the shared report service."""

# Keep annotations evaluated: Python 3.7-compatible Typer reads Annotated
# metadata from inspect.signature before resolving postponed type hints.

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Union

import typer
from typing_extensions import Annotated, Literal

from pt_snap_cli.cli_limits import MaxScratchDBBytes, MaxWorkBytes, MaxWorkRows
from pt_snap_cli.cli_output import (
    error as _error,
)
from pt_snap_cli.cli_output import (
    error_from_exc as _error_from_exc,
)
from pt_snap_cli.cli_output import (
    json_flag as _json_flag,
)
from pt_snap_cli.cli_output import (
    print_peak_memory_report as _print_peak_memory_report,
)
from pt_snap_cli.completion import complete_device_ids
from pt_snap_cli.core import (
    DatabaseMissingError,
    DatabaseSchemaError,
    FocusFileInvalidError,
    FocusNotConfiguredError,
    FocusService,
    InvalidDeviceError,
    InvalidParameterError,
    QueryExecutionError,
    ReportService,
    TemplateNotFoundError,
    TemplateRenderError,
)
from pt_snap_cli.core.common.error_codes import DATABASE_NOT_FOUND, INVALID_PARAMETER
from pt_snap_cli.core.common.errors import PtSnapCoreError
from pt_snap_cli.core.common.query_limits import QueryLimits
from pt_snap_cli.memory_tree_render import render_memory_tree

report_app = typer.Typer(help="Generate memory analysis reports")


@report_app.command("memory-tree")
def report_memory_tree(
    event_id: Annotated[int, typer.Option("--event-id", help="Analyze live memory after this event")],
    db_path: Annotated[Union[Path, None], typer.Argument(help="Path to database (optional if configured)")] = None,
    device: Annotated[Union[int, None], typer.Option("--device", "-d", autocompletion=complete_device_ids)] = None,
    include_static: Annotated[bool, typer.Option("--include-static/--exclude-static")] = True,
    min_size: Annotated[int, typer.Option(help="Minimum individual block size in bytes")] = 0,
    output_format: Annotated[
        Literal["text", "html"],
        typer.Option("--format", help="Text breakdown or interactive HTML flamegraph on stdout"),
    ] = "text",
    timeout: Annotated[
        Union[float, None],
        typer.Option("--timeout", help="Query deadline in seconds; <=0 disables"),
    ] = None,
    max_work_rows: MaxWorkRows = None,
    max_work_bytes: MaxWorkBytes = None,
    max_scratch_db_bytes: MaxScratchDBBytes = None,
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Decompose event-time active memory by ordered allocation frames."""
    service = ReportService()
    try:
        if json_output and output_format != "text":
            raise ValueError("--json cannot be combined with --format html.")
        result = service.memory_tree_report(
            event_id=event_id,
            db_path=db_path,
            device_id=device,
            include_static=include_static,
            min_size=min_size,
            timeout_s=timeout,
            query_limits=QueryLimits.resolve(
                max_work_rows=max_work_rows,
                max_work_bytes=max_work_bytes,
                max_scratch_db_bytes=max_scratch_db_bytes,
            ),
        )
        if json_output:
            typer.echo(json.dumps({"event_id": event_id, **asdict(result)}, indent=2))
        else:
            typer.echo(render_memory_tree(result, event_id, html=output_format == "html"))
    except PtSnapCoreError as exc:
        _error_from_exc(exc)
    except ValueError as exc:
        _error(str(exc), code=INVALID_PARAMETER)
    finally:
        service.close()


@report_app.command("peak-memory")
def report_peak_memory(
    db_path: Annotated[Union[Path, None], typer.Argument(help="Path to database file (optional if configured)")] = None,
    device: Annotated[
        Union[int, None],
        typer.Option("--device", "-d", help="Device ID to report", autocompletion=complete_device_ids),
    ] = None,
    metric: Annotated[
        Literal["active", "allocated", "reserved"],
        typer.Option(help="Peak metric to report: active, allocated, or reserved"),
    ] = "active",
    include_static: Annotated[
        bool,
        typer.Option("--include-static/--exclude-static", help="Include static memory group"),
    ] = True,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum dynamic callstack groups (static/preexisting are extra)"),
    ] = 20,
    stack_bytes: Annotated[
        int,
        typer.Option(
            "--stack-bytes",
            help="Opt-in UTF-8 byte budget per callstack (0: identity only; negative: full text). Not a response byte cap or token budget.",
        ),
    ] = -1,
    start_id: Annotated[Union[int, None], typer.Option("--start-id", help="First real event ID in peak range")] = None,
    end_id: Annotated[Union[int, None], typer.Option("--end-id", help="Last real event ID in peak range")] = None,
    timeout: Annotated[
        Union[float, None],
        typer.Option("--timeout", help="One report-wide deadline in seconds; <=0 disables"),
    ] = None,
    max_work_rows: MaxWorkRows = None,
    max_work_bytes: MaxWorkBytes = None,
    max_scratch_db_bytes: MaxScratchDBBytes = None,
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Generate a peak memory attribution report."""
    focus_service = FocusService()
    report_service = ReportService(focus_service)
    try:
        report = report_service.peak_memory_report(
            db_path=db_path,
            device_id=device,
            metric=metric,
            include_static=include_static,
            limit=limit,
            stack_bytes=stack_bytes,
            start_id=start_id,
            end_id=end_id,
            timeout_s=timeout,
            query_limits=QueryLimits.resolve(
                max_work_rows=max_work_rows,
                max_work_bytes=max_work_bytes,
                max_scratch_db_bytes=max_scratch_db_bytes,
            ),
        )
    except ValueError as e:
        _error(str(e), code=INVALID_PARAMETER, hint="Use --metric active, allocated, or reserved.")
    except FocusFileInvalidError as e:
        _error_from_exc(e)
    except FocusNotConfiguredError as e:
        _error_from_exc(
            e,
            extra_lines=(
                "Use 'pt-snap focus <database_path>' to set a project database, or provide db_path argument.",
            ),
        )
    except DatabaseMissingError:
        try:
            state = focus_service.get_focus(explicit_db_path=db_path, explicit_device_id=device)
        except FocusFileInvalidError:
            state = None
        source = state.source if state is not None else "configured"
        path = state.db_path if state is not None else db_path
        extra: List[str] = []
        if state is not None and state.focus_file:
            extra.append(f"Focus file: {state.focus_file}")
        extra.append(
            "Use 'pt-snap focus <new_database_path>' to set a new project database, or provide db_path argument."
        )
        _error(
            f"Database from {source} focus not found: {path}",
            code=DATABASE_NOT_FOUND,
            hint="Use 'pt-snap focus <new_database_path>' or pass a database path that exists.",
            extra_lines=tuple(extra),
        )
    except InvalidDeviceError as e:
        _error_from_exc(e)
    except (
        TemplateNotFoundError,
        TemplateRenderError,
        InvalidParameterError,
        QueryExecutionError,
        DatabaseSchemaError,
    ) as e:
        _error_from_exc(e, text_prefix="Error generating report: ")
    finally:
        report_service.close()

    if json_output:
        typer.echo(json.dumps(asdict(report), indent=2))
        return
    _print_peak_memory_report(report)
