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

"""Shared CLI output and JSON error adaptation; no product decisions live here."""

from __future__ import annotations

from contextvars import ContextVar
from typing import NoReturn, Tuple, Union, cast

import typer
from typer.models import OptionInfo

from pt_snap_cli.core import (
    DatabaseOverview,
    PeakMemoryReport,
    classify_error,
    dumps_json,
    json_error,
)
from pt_snap_cli.core.common.error_codes import ERROR

# Typer 0.27+ vendors Click, so its context cannot be read via click.get_current_context.
JSON_MODE: ContextVar[bool] = ContextVar("pt_snap_json_mode", default=False)


def json_mode() -> bool:
    return JSON_MODE.get()


def _set_json_mode(value: bool) -> bool:
    _ = JSON_MODE.set(bool(value))
    return value


def json_flag() -> OptionInfo:
    return cast(
        OptionInfo,
        typer.Option("--json", help="Emit machine-readable JSON", callback=_set_json_mode),
    )


def emit_json(payload: object) -> None:
    try:
        typer.echo(dumps_json(payload))
    except TypeError as exc:
        error(
            str(exc),
            code=ERROR,
            hint="Result contained a value that cannot be serialized to JSON.",
        )


def error(
    message: str,
    *,
    code: Union[str, None] = None,
    hint: Union[str, None] = None,
    extra_lines: Tuple[str, ...] = (),
    text_prefix: str = "Error: ",
) -> NoReturn:
    if json_mode():
        typer.echo(dumps_json(json_error(code or ERROR, message, hint)), err=True)
        raise typer.Exit(1) from None
    typer.secho(f"{text_prefix}{message}", fg=typer.colors.RED)
    for line in extra_lines:
        typer.echo(line)
    raise typer.Exit(1) from None


def error_from_exc(
    exc: BaseException,
    *,
    extra_lines: Tuple[str, ...] = (),
    text_prefix: str = "Error: ",
) -> NoReturn:
    code, hint = classify_error(exc)
    error(str(exc), code=code, hint=hint, extra_lines=extra_lines, text_prefix=text_prefix)


# pylint: disable-next=redefined-outer-name  # Preserve the public error= keyword.
def echo_callstack_layout(layout: Union[str, None], error: Union[str, None] = None) -> None:
    if layout == "v1":
        typer.echo("Callstack layout: v1 (inline text)")
    elif layout == "v2":
        typer.echo("Callstack layout: v2 (deduplicated)")
    elif error:
        typer.secho(f"Warning: {error}", fg=typer.colors.YELLOW)


def print_peak_memory_report(report: PeakMemoryReport) -> None:
    typer.secho("Peak memory report", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"Device: {report.device_id}")
    typer.echo(f"Metric: {report.metric}")
    typer.echo(f"Event ID: {report.event_id}")
    typer.echo()

    typer.secho("Peak counters:", fg=typer.colors.GREEN, bold=True)
    if report.peak:
        typer.echo(
            f"  allocated: {report.peak.get('peak_allocated')} at event {report.peak.get('peak_allocated_event_id')}"
        )
        typer.echo(f"  active: {report.peak.get('peak_active')} at event {report.peak.get('peak_active_event_id')}")
        typer.echo(
            f"  reserved: {report.peak.get('peak_reserved')} at event {report.peak.get('peak_reserved_event_id')}"
        )
    else:
        typer.echo("  No peak counters found.")
    typer.echo()

    typer.secho("Allocator gap:", fg=typer.colors.GREEN, bold=True)
    if report.allocator_gap:
        gap = report.allocator_gap
        typer.echo(
            f"  active peak event: {gap.get('peak_active_event_id')} reserved-active gap={gap.get('reserved_active_gap_at_active_peak')}"
        )
        typer.echo(
            f"  allocated peak event: {gap.get('peak_allocated_event_id')} reserved-allocated gap={gap.get('reserved_allocated_gap_at_allocated_peak')}"
        )
        typer.echo(
            f"  reserved peak event: {gap.get('peak_reserved_event_id')} reserved-active gap={gap.get('reserved_active_gap_at_reserved_peak')}"
        )
        typer.echo(f"  all peaks same event: {bool(gap.get('all_peaks_same_event'))}")
    else:
        typer.echo("  No allocator gap data found.")
    typer.echo()

    typer.secho("Active memory by callstack:", fg=typer.colors.GREEN, bold=True)
    if report.event_id is None:
        typer.echo("  Attribution: unavailable (no peak event).")
    elif report.has_more or report.truncated:
        typer.echo("  Attribution: partial / possibly incomplete (dynamic top_n cap reached).")
        typer.echo("  Increase --limit within a finite budget to check for additional groups.")
    else:
        typer.echo("  Attribution: complete for the effective filters.")
    typer.echo(
        f"  Parameters: include_static={report.effective_params.get('include_static')}, "
        f"min_size={report.effective_params.get('min_size')}, "
        f"top_n={report.effective_params.get('top_n')}"
    )
    typer.echo(
        f"  Percentage denominator: {report.percent_denominator}={report.included_bytes} bytes "
        "(included groups after filtering/top_n; not all active memory or block counts)."
    )
    coverage = f"{report.coverage_percent:.4f}%" if report.coverage_percent is not None else "unknown"
    typer.echo(
        f"  Active coverage at event {report.event_id}: {coverage} "
        f"(included={report.included_bytes} bytes, active={report.active_bytes_at_event} bytes)."
    )
    if not report.callstack_groups:
        typer.echo("  No active memory callstack groups found.")
        return
    for index, row in enumerate(report.callstack_groups, start=1):
        typer.echo(
            f"  [{index}] {row.get('category')} {row.get('size_bytes')} bytes, {row.get('block_count')} blocks ({row.get('percent_of_active_blocks')}%)"
        )
        typer.echo(f"      {row.get('callstack')}")
        if "stack_id" in row:
            typer.echo(
                f"      stack_id={row['stack_id']} kind={row.get('stack_kind')} "
                f"stack_truncated={row.get('stack_truncated')} "
                f"stack_bytes={row.get('stack_bytes')} "
                f"stack_original_bytes={row.get('stack_original_bytes')}"
            )
            if row.get("stack_kind") == "captured":
                typer.echo(
                    "      Full text: query event with "
                    f"id={row.get('stack_event_id')}, omit stack_bytes, same database/device."
                )


def print_database_overview(overview: DatabaseOverview) -> None:
    inspection = overview.metadata
    typer.echo(f"Database: {overview.db_path}")
    typer.echo(f"Focus source: {overview.focus_source}")
    typer.echo(f"Import metadata: {inspection.status}")
    if inspection.reason is not None:
        typer.echo(f"Metadata reason: {inspection.reason}")
    if not overview.devices:
        typer.echo("Devices: none")
        return
    typer.echo("Devices:")
    for device in overview.devices:
        if device.first_event_id is None or device.last_event_id is None:
            typer.echo(f"  {device.device_id}: no events")
        else:
            typer.echo(f"  {device.device_id}: events {device.first_event_id}..{device.last_event_id}")
