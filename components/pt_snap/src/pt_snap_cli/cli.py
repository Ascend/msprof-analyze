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

# pylint: disable=too-many-lines  # Root command registrations stay together; behavior lives in services.
"""CLI entry point for pt-snap."""

# Keep annotations evaluated: Python 3.7-compatible Typer reads Annotated
# metadata from inspect.signature before resolving postponed type hints.

import json
import logging
import shlex
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Union, cast

import typer

try:
    from typer.exceptions import Abort, Exit
except ImportError:  # Typer versions supporting Python 3.7
    from click.exceptions import Abort, Exit
from typing_extensions import Annotated

try:
    # pylint: disable-next=ungrouped-imports  # Version-dependent Typer/Click fallback imports.
    from typer._click.exceptions import ClickException
except ImportError:  # typer < 0.27
    # pylint: disable-next=ungrouped-imports  # Version-dependent Typer/Click fallback imports.
    from click.exceptions import ClickException

try:
    from click.exceptions import Abort as ClickAbort
except ImportError:  # pragma: no cover
    ClickAbort = Abort

from pt_snap_cli import __version__
from pt_snap_cli.cli_limits import MaxScratchDBBytes, MaxWorkBytes, MaxWorkRows
from pt_snap_cli.cli_output import (
    JSON_MODE as _JSON_MODE,
)
from pt_snap_cli.cli_output import (
    echo_callstack_layout as _echo_callstack_layout,
)
from pt_snap_cli.cli_output import (
    emit_json as _emit_json,
)
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
    json_mode as _json_mode,
)
from pt_snap_cli.cli_output import (
    print_database_overview as _print_database_overview,
)
from pt_snap_cli.cli_reports import report_app
from pt_snap_cli.completion import (
    complete_categories,
    complete_device_ids,
    complete_template_names,
)
from pt_snap_cli.config import ENV_DB_PATH
from pt_snap_cli.core import (
    CapabilityService,
    DatabaseMissingError,
    DatabaseSchemaError,
    FocusFileInvalidError,
    FocusNotConfiguredError,
    FocusService,
    FocusState,
    ImportExecutionError,
    ImportMetadataService,
    ImportOptions,
    ImportResult,
    ImportService,
    ImportToolMissingError,
    InvalidCategoryError,
    InvalidDeviceError,
    JsonValue,
    OverviewService,
    QueryExecutionError,
    QueryService,
    SnapshotFileInvalidError,
    SplitError,
    SplitOptions,
    SplitResult,
    SplitService,
    TemplateInfo,
    TemplateNotFoundError,
    TemplateRenderError,
    dumps_json,
    json_error,
    json_success,
)
from pt_snap_cli.core.common.error_codes import DATABASE_NOT_FOUND, ERROR, INVALID_PARAMETER
from pt_snap_cli.core.common.errors import InvalidParameterError
from pt_snap_cli.core.common.query_limits import QueryLimits
from pt_snap_cli.query.config import OUTPUT_COLUMN_OPTIONAL
from pt_snap_cli.query.executor import reported_sql_limit
from pt_snap_cli.query.registry import discover_categories, get_query

app = typer.Typer(
    name="pt-snap",
    help="PyTorch Memory Snapshot Analysis Tool",
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(report_app, name="report")


def _focus_fields(state: FocusState) -> Dict[str, object]:
    db_path = str(state.db_path) if state.db_path is not None else None
    return {
        "configured": state.db_path is not None,
        "db_path": db_path,
        "focus_source": state.source,
        "focus_file": str(state.focus_file) if state.focus_file is not None else None,
        "device_id": state.device_id,
        "available_devices": list(state.available_devices),
        "callstack_layout": state.callstack_layout,
        "callstack_layout_error": state.callstack_layout_error,
        "db_exists": bool(state.db_path is not None and state.db_path.exists()),
    }


def _focus_json(state: FocusState, *, action: str, **extra: object) -> Dict[str, JsonValue]:
    return json_success(action=action, **_focus_fields(state), **extra)


def _import_json(result: ImportResult) -> Dict[str, JsonValue]:
    focus_state = _focus_fields(result.focus_state) if result.focus_state is not None else None
    return json_success(
        db_path=str(result.db_path),
        device_id=result.device_id,
        reused=result.reused,
        cache_miss_reason=result.cache_miss_reason,
        metadata=asdict(result.metadata) if result.metadata is not None else None,
        focus_state=focus_state,
        focus_source=(result.focus_state.source if result.focus_state is not None else None),
        **(
            {
                "dataset_path": str(result.dataset_path),
                "devices": list(result.devices),
                "slice_count": result.slice_count,
                "format": result.format,
                "omitted_devices": list(result.omitted_devices),
                "rebuilt": not result.reused,
            }
            if result.dataset_path is not None
            else {}
        ),
    )


def _import_snapshot_result(options: ImportOptions, *, json_output: bool) -> ImportResult:
    if not json_output:
        return ImportService().import_snapshot(options)
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        return ImportService().import_snapshot(options)
    finally:
        logging.disable(previous_disable)


def _split_json(result: SplitResult) -> Dict[str, JsonValue]:
    return json_success(
        output=str(result.output),
        files=[str(path) for path in result.files],
        devices=list(result.devices),
        format=result.format,
    )


def _template_info_dict(info: TemplateInfo) -> Dict[str, object]:
    return QueryService.template_info_to_dict(info)


def _effective_query_params(
    template: str,
    params: Dict[str, object],
    max_rows: Union[int, None] = None,
) -> Dict[str, object]:
    query_template = get_query(template)
    if query_template is None:
        return params
    try:
        validated = dict(query_template.validate_params(params))
    except (TypeError, ValueError) as exc:
        raise TemplateRenderError(f"Failed to validate parameters for template '{template}': {exc}") from exc
    sql_limit = reported_sql_limit(validated, max_rows, parameters=query_template.parameters)
    if sql_limit is not None:
        validated["limit"] = sql_limit
    return validated


def _focus_service() -> FocusService:
    return FocusService()


def _query_service() -> QueryService:
    return QueryService(_focus_service())


def _echo_output_schema_column(column: Mapping[str, object]) -> None:
    typer.echo(f"  {column['column']}: {column['type']}")
    for key in OUTPUT_COLUMN_OPTIONAL:
        if key not in column:
            continue
        value = column[key]
        if key == "interpretation_limits":
            typer.echo("    interpretation_limits:")
            for item in cast(List[str], value):
                typer.echo(f"      - {item}")
        else:
            typer.echo(f"    {key}: {value}")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"msprof-analyze pt-snap version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    _: Annotated[
        Union[bool, None],
        typer.Option("--version", "-v", help="Show version and exit", callback=version_callback),
    ] = None,
) -> None:
    """PyTorch Memory Snapshot Analysis Tool."""
    _JSON_MODE.set(False)


@app.command("focus")
def focus_database(
    db_path: Annotated[
        Union[Path, None],
        typer.Argument(help="Path to SQLite database, complete manifest.json, or dataset directory"),
    ] = None,
    device: Annotated[
        Union[int, None],
        typer.Option(
            "--device",
            "-d",
            help="Device ID to focus on",
            autocompletion=complete_device_ids,
        ),
    ] = None,
    session: Annotated[
        bool,
        typer.Option("--session", help="Print a shell export for this session only"),
    ] = False,
    global_focus: Annotated[bool, typer.Option("--global", help="Store the focus in legacy global config")] = False,
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Set the current analysis focus (database and optional device)."""
    focus_service = _focus_service()

    if db_path is None and device is None:
        try:
            state = focus_service.get_focus()
        except (FocusFileInvalidError, DatabaseSchemaError) as e:
            _error_from_exc(e)

        if json_output:
            _emit_json(_focus_json(state, action="read"))
            raise typer.Exit()
        if state.db_path:
            typer.echo(f"Current database ({state.source}): {state.db_path}")
            if state.focus_file:
                typer.echo(f"Focus file: {state.focus_file}")
            if state.device_id is not None:
                typer.echo(f"Focused device: {state.device_id}")
            _echo_callstack_layout(state.callstack_layout, state.callstack_layout_error)
            if not state.db_path.exists():
                typer.secho("Warning: Database file does not exist!", fg=typer.colors.YELLOW)
        else:
            typer.echo("No current focus set.")
            typer.echo("Usage: pt-snap focus <database_path> [--device <id>] [--session|--global]")
        raise typer.Exit()

    if session and global_focus:
        _error(
            "--session and --global cannot be used together.",
            code=INVALID_PARAMETER,
            hint="Choose either --session or --global.",
        )
    if session and device is not None:
        _error(
            "--device cannot be used with --session; session focus exports only a database path.",
            code=INVALID_PARAMETER,
            hint="Omit --device; session focus exports only PT_SNAP_DB_PATH.",
        )

    if db_path is None and device is not None:
        try:
            state = focus_service.set_device(device)
        except (
            FocusFileInvalidError,
            FocusNotConfiguredError,
            DatabaseMissingError,
            DatabaseSchemaError,
            InvalidDeviceError,
        ) as e:
            _error_from_exc(e)

        if json_output:
            _emit_json(_focus_json(state, action="set_device"))
            raise typer.Exit()
        typer.secho(f"Focused device ({state.source}): {device}", fg=typer.colors.GREEN)
        if state.source == "project" and state.focus_file:
            typer.echo(f"Focus file: {state.focus_file}")
        _echo_callstack_layout(state.callstack_layout, state.callstack_layout_error)
        raise typer.Exit()

    try:
        focus_db_path = db_path
        if focus_db_path is None:
            raise AssertionError("db_path must be provided when setting focus")
        if session:
            state = focus_service.validate_session_db(focus_db_path)
            export_line = f"export {ENV_DB_PATH}={shlex.quote(str(state.db_path))}"
            if json_output:
                _emit_json(
                    _focus_json(
                        state,
                        action="validate_session",
                        session_applied=False,
                        env={
                            "name": ENV_DB_PATH,
                            "value": str(state.db_path),
                            "export": export_line,
                        },
                    )
                )
                return
            typer.echo(export_line)
            return
        if global_focus:
            state = focus_service.set_global_focus(focus_db_path, device)
            action = "set_global"
            if not json_output:
                typer.secho(f"Using global database: {state.db_path}", fg=typer.colors.GREEN)
        else:
            state = focus_service.set_project_focus(focus_db_path, device)
            action = "set_project"
            if not json_output:
                typer.secho(f"Using project database: {state.db_path}", fg=typer.colors.GREEN)
                if state.focus_file:
                    typer.echo(f"Focus file: {state.focus_file}")
        if json_output:
            _emit_json(_focus_json(state, action=action))
            return
        if device is not None:
            typer.echo(f"Focused device: {device}")
        if state.available_devices:
            typer.echo(f"Available devices: {', '.join(map(str, state.available_devices))}")
        else:
            typer.echo("No devices found in database.")
        _echo_callstack_layout(state.callstack_layout, state.callstack_layout_error)
    except (
        DatabaseMissingError,
        DatabaseSchemaError,
        InvalidDeviceError,
        FocusFileInvalidError,
    ) as e:
        _error_from_exc(e)


@app.command("import")
def import_snapshot(
    snapshot_file: Annotated[Path, typer.Argument(help="Path to .pkl snapshot")],
    output_dir: Annotated[Union[Path, None], typer.Option("--output-dir", "-o")] = None,
    device: Annotated[Union[int, None], typer.Option("--device", "-d")] = None,
    no_focus: Annotated[bool, typer.Option("--no-focus", help="Skip focus update")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Rebuild native/single DB; never replace compatible output"),
    ] = False,
    events_per_slice: Annotated[
        Union[int, None],
        typer.Option(
            "--events-per-slice",
            help="Real events per device shard; native unless --format msinsight",
        ),
    ] = None,
    output_format: Annotated[
        Union[str, None],
        typer.Option(
            "--format",
            help="single-db, pt-snap-native-v2, or msinsight (compatibility-v1)",
        ),
    ] = None,
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Import a PyTorch memory snapshot into a SQLite database."""
    try:
        result = _import_snapshot_result(
            ImportOptions(
                snapshot_file=snapshot_file,
                output_dir=output_dir,
                device=device,
                set_focus=not no_focus,
                force=force,
                events_per_slice=events_per_slice,
                format=output_format,
            ),
            json_output=json_output,
        )
    except (
        ImportToolMissingError,
        ImportExecutionError,
        SnapshotFileInvalidError,
        InvalidParameterError,
    ) as e:
        _error_from_exc(e)

    if json_output:
        _emit_json(_import_json(result))
        return

    action = "Reused" if result.reused else "Imported"
    typer.echo(f"{action}: {result.db_path}")
    if result.dataset_path is not None:
        typer.echo(f"Format: {result.format}; devices: {list(result.devices)}; slices: {result.slice_count}")
    if result.cache_miss_reason is not None:
        typer.echo(f"Cache miss: {result.cache_miss_reason}")
    if result.focus_state is not None and result.focus_state.focus_file is not None:
        typer.echo(f"Focus: {result.focus_state.focus_file}")


@app.command("split")
def split_snapshot(
    snapshot_file: Annotated[
        Path,
        typer.Argument(
            help="Path to .pkl or .pickle snapshot",
            metavar="SNAPSHOT_PATH",
        ),
    ],
    output: Annotated[Path, typer.Option("--output", "-o", help="New output directory")],
    device: Annotated[Union[int, None], typer.Option("--device", "-d")] = None,
    slices: Annotated[Union[int, None], typer.Option("--slices", "-s")] = None,
    max_entries: Annotated[Union[int, None], typer.Option("--max-entries", "-m")] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: pickle or json",
            metavar="{pickle,json}",
        ),
    ] = "pickle",
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Split a snapshot into independently replayable device slices."""
    try:
        result = SplitService().split(
            SplitOptions(
                snapshot_file=snapshot_file,
                output=output,
                device=device,
                slices=slices,
                max_entries=max_entries,
                format=output_format,
            )
        )
    except SplitError as exc:
        _error_from_exc(exc)

    if json_output:
        _emit_json(_split_json(result))
        return

    typer.echo(f"Split: {result.output}")
    typer.echo(f"Devices: {', '.join(map(str, result.devices))}")
    typer.echo(f"Files: {len(result.files)}")


@app.command("metadata")
def show_database_metadata(
    db_path: Annotated[
        Union[Path, None],
        typer.Argument(help="Path to database, manifest.json, or dataset directory (optional if configured)"),
    ] = None,
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Show import metadata for a SnapshotDB."""
    focus_service = _focus_service()
    try:
        resolved = focus_service.resolve_focus(explicit_db_path=db_path)
        if resolved.db_path is None:
            raise FocusNotConfiguredError("No database path specified and no database configured.")
        service = ImportMetadataService()
        inspection = service.inspect(resolved.db_path)
    except (
        FocusFileInvalidError,
        FocusNotConfiguredError,
        DatabaseMissingError,
        DatabaseSchemaError,
    ) as e:
        _error_from_exc(e)

    if json_output:
        typer.echo(json.dumps(service.inspection_to_dict(inspection), indent=2))
        return

    typer.echo(f"Database: {inspection.db_path}")
    typer.echo(f"Status: {inspection.status}")
    if inspection.reason is not None:
        typer.echo(f"Reason: {inspection.reason}")
    if inspection.metadata is not None:
        typer.echo("Metadata:")
        for key, value in cast(Mapping[str, object], asdict(inspection.metadata)).items():
            typer.echo(f"  {key}: {value}")


@app.command("query")
def query_database(
    db_path: Annotated[
        Union[Path, None],
        typer.Argument(help="Path to database, manifest.json, or dataset directory (optional if configured)"),
    ] = None,
    template_use: Annotated[
        Union[str, None],
        typer.Option(
            "--template-use",
            help="Query template name to execute",
            autocompletion=complete_template_names,
        ),
    ] = None,
    params: Annotated[Union[str, None], typer.Option(help="Query parameters as JSON string")] = None,
    device: Annotated[
        Union[int, None],
        typer.Option(
            help="Device ID to query",
            autocompletion=complete_device_ids,
        ),
    ] = None,
    slice_index: Annotated[
        Union[int, None],
        typer.Option("--slice", help="Explicit dataset slice index for event inspection"),
    ] = None,
    list_templates: Annotated[bool, typer.Option("--list", help="List all available query templates")] = False,
    category: Annotated[
        Union[str, None],
        typer.Option(
            "--category",
            help="Filter templates by category",
            autocompletion=complete_categories,
        ),
    ] = None,
    template_info: Annotated[
        Union[str, None],
        typer.Option(
            "--template-info",
            help="Show detailed information about a template (including parameters, output schema, and field semantics)",
            autocompletion=complete_template_names,
        ),
    ] = None,
    max_rows: Annotated[
        Union[int, None],
        typer.Option(
            "-n",
            help="Maximum number of result rows to display (<= 0 for unlimited, default: unlimited)",
        ),
    ] = None,
    exact_total: Annotated[
        bool,
        typer.Option(
            "--exact-total",
            help="Compute an exact matching-row total with a COUNT query (default: total equals returned rows)",
        ),
    ] = False,
    timeout: Annotated[
        Union[float, None],
        typer.Option(
            "--timeout",
            help="Query execution timeout in seconds (separate from -n; <= 0 disables; default: PT_SNAP_QUERY_TIMEOUT or unlimited)",
        ),
    ] = None,
    max_work_rows: MaxWorkRows = None,
    max_work_bytes: MaxWorkBytes = None,
    max_scratch_db_bytes: MaxScratchDBBytes = None,
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Execute queries on the memory snapshot database."""
    focus_service = _focus_service()
    query_service = _query_service()
    try:
        query_limits = QueryLimits.resolve(
            max_work_rows=max_work_rows,
            max_work_bytes=max_work_bytes,
            max_scratch_db_bytes=max_scratch_db_bytes,
        )
    except InvalidParameterError as exc:
        query_service.close()
        _error_from_exc(exc)

    if category is not None and not list_templates and not template_use and not template_info:
        list_templates = True

    if list_templates:
        try:
            categories = discover_categories()
            category_labels = {cat: cat.replace("_", " ").title() + " Queries" for cat in categories}
            if category is not None:
                filter_cats = [category]
                _ = query_service.list_templates(category)
            else:
                filter_cats = categories
            listed: List[Dict[str, object]] = []
            any_found = False
            for cat in filter_cats:
                details = query_service.list_templates(cat, validate_category=False)
                if details:
                    any_found = True
                    if json_output:
                        listed.extend(
                            {
                                "name": info.name,
                                "description": info.description,
                                "category": info.category,
                            }
                            for info in details
                        )
                        continue
                    typer.secho(f"{category_labels[cat]}:", fg=typer.colors.GREEN, bold=True)
                    for info in details:
                        typer.secho(f"  {info.name}", fg=typer.colors.GREEN, bold=True)
                        typer.echo(f"    {info.description}")
                    typer.echo()
            if json_output:
                _emit_json(json_success(category=category, templates=listed))
                raise typer.Exit()
            if not any_found:
                typer.echo("No query templates available.")
        except InvalidCategoryError as e:
            _error_from_exc(e)
        raise typer.Exit()

    if template_info:
        try:
            info = query_service.get_template_info(template_info, query_limits=query_limits)
        except TemplateNotFoundError as e:
            _error_from_exc(e)

        if json_output:
            _emit_json(json_success(template=info.name, **_template_info_dict(info)))
            raise typer.Exit()

        typer.secho(f"Template: {info.name}", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"Description: {info.description}")
        typer.echo(f"Category: {info.category}")
        typer.echo(f"Devices: {info.devices}")
        typer.echo(f"Dataset Support: {json.dumps(info.dataset_support, sort_keys=True)}")
        typer.echo(f"Semantics Version: {info.semantics_version if info.semantics_version is not None else 'none'}")
        typer.echo()
        typer.echo("Parameters:")
        if info.parameters:
            for param_name, param_details in info.parameters.items():
                required_str = " (required)" if param_details.required else " (optional)"
                choices_str = (
                    f" [choices: {', '.join(str(choice) for choice in param_details.choices)}]"
                    if param_details.choices
                    else ""
                )
                default_str = f" [default: {param_details.default}]" if param_details.default is not None else ""
                typer.secho(
                    f"  {param_name}: {param_details.type}{required_str}{choices_str}{default_str}",
                    fg=typer.colors.YELLOW,
                )
                typer.echo(f"    {param_details.description}")
        else:
            typer.echo("  None")
        typer.echo()
        typer.echo("Output Schema:")
        if info.output_schema:
            for col in info.output_schema:
                _echo_output_schema_column(col)
        else:
            typer.echo("  Dynamic (depends on query)")
        if info.interpretation_limits:
            typer.echo()
            typer.echo("Interpretation Limits:")
            for limit in info.interpretation_limits:
                typer.echo(f"  - {limit}")
        typer.echo()
        typer.echo("Example Usage:")
        example_params = {}
        for param_name, param_details in info.parameters.items():
            if param_details.type == "int":
                example_params[param_name] = param_details.default if param_details.default is not None else 0
            elif param_details.type == "float":
                example_params[param_name] = param_details.default if param_details.default is not None else 0.0
            elif param_details.type == "str":
                if param_details.default is not None:
                    example_params[param_name] = param_details.default
                elif param_details.choices:
                    example_params[param_name] = param_details.choices[0]
                else:
                    example_params[param_name] = "example"
            elif param_details.type == "bool":
                example_params[param_name] = True
        if example_params:
            typer.echo(
                f"  pt-snap query {db_path or '<configured_db>'} --template-use {info.name} --params '{json.dumps(example_params)}'"
            )
        else:
            typer.echo(f"  pt-snap query {db_path or '<configured_db>'} --template-use {info.name}")
        raise typer.Exit()

    if not template_use:
        _error(
            "--template-use is required when not using --list or --template-info",
            code=INVALID_PARAMETER,
            hint="Pass --template-use, --list, or --template-info.",
        )

    try:
        loaded_params = (  # pyright: ignore[reportUnknownVariableType]
            json.loads(params) if params else {}
        )
        if not isinstance(loaded_params, dict):
            raise TemplateRenderError("Query parameters must be a JSON object.")
        query_params = cast(Dict[str, object], loaded_params)
        result = query_service.execute_query(
            template=template_use,
            params=query_params,
            db_path=db_path,
            device_id=device,
            max_rows=max_rows,
            exact_total=exact_total,
            timeout_s=timeout,
            slice_index=slice_index,
            query_limits=query_limits,
        )
        if json_output:
            resolved = focus_service.resolve_focus(
                explicit_db_path=db_path,
                explicit_device_id=device,
            )
            _emit_json(
                json_success(
                    db_path=(str(resolved.db_path) if resolved.db_path is not None else None),
                    focus_source=resolved.source,
                    device_id=result.device_id,
                    template=result.template,
                    effective_params=_effective_query_params(template_use, query_params, max_rows=max_rows),
                    semantics_version=result.semantics_version,
                    total=result.total,
                    returned=result.returned,
                    has_more=result.has_more,
                    truncated=result.truncated,
                    total_is_exact=result.total_is_exact,
                    timeout_s=result.timeout_s,
                    rows=result.rows,
                    **({"scope": result.scope} if result.scope is not None else {}),
                )
            )
            return
        if result.rows:
            typer.echo(f"Found {result.total} results, showing {result.returned}:")
            for row in result.rows:
                typer.echo(f"  {row}")
            if result.has_more:
                if result.total_is_exact and result.total > result.returned:
                    typer.echo(f"  ... and {result.total - result.returned} more (use -n to show more)")
                else:
                    typer.echo("  ... more available (use -n, offset, top_n, or --exact-total)")
        else:
            typer.echo("No results found.")
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
        if str(e) == "No devices found in database." and not json_output:
            typer.echo("No devices found in database.")
            raise typer.Exit() from None
        _error_from_exc(e)
    except TemplateNotFoundError as e:
        _error_from_exc(e, text_prefix="Error executing query: ")
    except (
        TemplateRenderError,
        QueryExecutionError,
        InvalidParameterError,
        DatabaseSchemaError,
        json.JSONDecodeError,
    ) as e:
        _error_from_exc(e, text_prefix="Error executing query: ")
    finally:
        query_service.close()


@app.command("config")
def show_config(
    clear: Annotated[bool, typer.Option("--clear", help="Clear all configuration")] = False,
    show_path: Annotated[bool, typer.Option("--path", help="Show config file path")] = False,
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Show or manage pt-snap configuration."""
    focus_service = _focus_service()
    config_path = str(focus_service.get_global_config_path())

    if show_path:
        if json_output:
            _emit_json(json_success(action="path", path=config_path))
        else:
            typer.echo(f"Config file: {focus_service.get_global_config_path()}")
        raise typer.Exit()

    if clear:
        focus_service.clear_global_focus()
        if json_output:
            _emit_json(json_success(action="clear", cleared=True, path=config_path))
        else:
            typer.secho("Configuration cleared.", fg=typer.colors.GREEN)
        raise typer.Exit()

    current_config = focus_service.show_global_config()
    if json_output:
        _emit_json(json_success(action="show", path=config_path, config=current_config))
        return
    if not current_config:
        typer.echo("No configuration set.")
    else:
        typer.echo("Current configuration:")
        for key, value in cast(Mapping[str, object], current_config).items():
            typer.echo(f"  {key}: {value}")


@app.command("capabilities")
def show_capabilities(
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """List CLI version, query template contracts."""
    service = CapabilityService()
    try:
        catalog = service.catalog()
    except InvalidParameterError as e:
        _error_from_exc(e)
    if json_output:
        _emit_json(json_success(**service.catalog_to_dict(catalog)))
        return
    typer.echo(f"CLI version: {catalog.cli_version}")
    typer.echo()
    typer.echo(f"Templates ({len(catalog.templates)}):")
    for info in catalog.templates:
        category = info.category if info.category is not None else "unknown"
        typer.secho(f"  {info.name}  ({category})", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"    {info.description}")
        if info.parameters:
            names = ", ".join(info.parameters)
            typer.echo(f"    parameters: {names}")
    typer.echo()
    typer.echo("Use --json for full parameter contracts, output schemas, and field semantics.")


@app.command("overview")
def show_database_overview(
    db_path: Annotated[
        Union[Path, None],
        typer.Argument(help="Path to database, manifest.json, or dataset directory (optional if configured)"),
    ] = None,
    json_output: Annotated[bool, _json_flag()] = False,
) -> None:
    """Show read-only SnapshotDB devices, trace bounds, and import metadata status."""
    service = OverviewService(_focus_service())
    try:
        overview = service.inspect(db_path)
    except (
        FocusFileInvalidError,
        FocusNotConfiguredError,
        DatabaseMissingError,
        DatabaseSchemaError,
    ) as e:
        _error_from_exc(e)
    finally:
        service.close()

    if json_output:
        _emit_json(json_success(**service.overview_to_dict(overview)))
        return
    _print_database_overview(overview)
    if overview.dataset is not None:
        typer.echo(f"Dataset: {overview.dataset['format']} ({overview.dataset['status']})")
        typer.echo(f"Slices/devices: {overview.dataset['devices']}")
        typer.echo("Text callstacks available; structured frames and cross-slice queries unavailable.")


# Flag-only options used when a parse failure happens before the --json callback.
# A following --json is treated as a value of the previous option otherwise.
_FLAG_ONLY_OPTIONS = frozenset(
    {
        "--json",
        "--version",
        "-v",
        "--session",
        "--global",
        "--no-focus",
        "--force",
        "--list",
        "--project",
        "--user",
        "--clear",
        "--path",
        "--help",
        "-h",
        "--include-static",
        "--exclude-static",
        "--exact-total",
    }
)


def _argv_token_takes_value(token: Union[str, None]) -> bool:
    """True when the next argv token would be this option's value."""
    if token is None or token in _FLAG_ONLY_OPTIONS or "=" in token:
        return False
    try:
        _ = float(token)
    except ValueError:
        return token.startswith("-")
    return False


def _argv_requests_json(argv: Sequence[str]) -> bool:
    """Best-effort pre-parse scan for a ``--json`` flag.

    ContextVar state is not set when Click fails before the option callback.
    Tokens after ``--`` are ignored. ``--json`` immediately after a
    value-taking option is treated as that option's value, not as the flag.
    ``--opt=value`` and numeric tokens such as ``-1`` do not consume the
    next argument.
    """
    previous: Union[str, None] = None
    for arg in argv:
        if arg == "--":
            break
        if arg == "--json" and not _argv_token_takes_value(previous):
            return True
        previous = arg
    return False


def _json_requested() -> bool:
    return _json_mode() or _argv_requests_json(sys.argv[1:])


def _emit_aborted() -> None:
    if _json_requested():
        typer.echo(
            dumps_json(
                json_error(
                    ERROR,
                    "Aborted!",
                    "The command was interrupted before it finished.",
                )
            ),
            err=True,
        )
        return
    typer.echo("Aborted!", err=True)


def _safe_call(args: Union[Sequence[str], None] = None, *, prog_name: Union[str, None] = None) -> int:
    try:
        # Typer 0.27's non-standalone _main catches Exit and returns the
        # code. Discarding that value made every domain _error() exit 0.
        rv = app(args=args, prog_name=prog_name, standalone_mode=False)
        code = rv if isinstance(rv, int) else 0
    except ClickException as exc:
        if _json_requested() or (args is not None and _argv_requests_json(args)):
            typer.echo(
                dumps_json(
                    json_error(
                        INVALID_PARAMETER,
                        exc.format_message(),
                        "Fix the command-line usage and retry. Use --help for options.",
                    )
                ),
                err=True,
            )
            return exc.exit_code
        exc.show()
        return exc.exit_code
    except Exit as exc:
        code = int(exc.exit_code)
    except (Abort, ClickAbort):
        _emit_aborted()
        return 1
    except KeyError as e:
        if str(e) in ("'COMP_WORDS'", "'COMP_LINE'", "'COMP_POINT'"):
            return 1
        raise
    if code == 130:
        _emit_aborted()
    return code


if __name__ == "__main__":
    sys.exit(_safe_call())
