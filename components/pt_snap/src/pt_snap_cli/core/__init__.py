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

"""Product services grouped into analysis, dataset, import and shared layers."""

from pt_snap_cli.core.analysis.capability_service import CapabilityService
from pt_snap_cli.core.analysis.focus_service import FocusService
from pt_snap_cli.core.analysis.overview_service import OverviewService
from pt_snap_cli.core.analysis.query_service import QueryService
from pt_snap_cli.core.analysis.report_service import ReportService
from pt_snap_cli.core.common.error_codes import classify_error
from pt_snap_cli.core.common.errors import (
    DatabaseMissingError,
    DatabaseSchemaError,
    FocusFileInvalidError,
    FocusNotConfiguredError,
    ImportExecutionError,
    ImportMetadataError,
    ImportToolMissingError,
    InvalidCategoryError,
    InvalidDeviceError,
    InvalidParameterError,
    PtSnapCoreError,
    QueryCancelledError,
    QueryExecutionError,
    QueryTimeoutError,
    SnapshotFileInvalidError,
    SourceChangedError,
    SplitError,
    TemplateNotFoundError,
    TemplateRenderError,
)
from pt_snap_cli.core.common.json_codec import (
    JSON_SCHEMA_VERSION,
    JsonValue,
    dumps_json,
    json_error,
    json_success,
    to_jsonable,
)
from pt_snap_cli.core.common.models import (
    CapabilityCatalog,
    DatabaseOverview,
    DeviceTraceBounds,
    FocusState,
    ImportMetadata,
    ImportOptions,
    ImportResult,
    MetadataInspection,
    PeakMemoryReport,
    QueryResult,
    ResolvedFocus,
    SplitOptions,
    SplitResult,
    TemplateInfo,
    TemplateParameter,
    TemplateSummary,
)
from pt_snap_cli.core.common.query_limits import QueryLimits
from pt_snap_cli.core.importing.import_metadata import ImportMetadataService
from pt_snap_cli.core.importing.import_service import ImportService
from pt_snap_cli.core.splitting.split_service import SplitService

__all__ = [
    "QueryCancelledError",
    "PtSnapCoreError",
    "FocusNotConfiguredError",
    "FocusFileInvalidError",
    "DatabaseMissingError",
    "DatabaseSchemaError",
    "InvalidDeviceError",
    "InvalidCategoryError",
    "TemplateNotFoundError",
    "TemplateRenderError",
    "QueryExecutionError",
    "InvalidParameterError",
    "QueryTimeoutError",
    "ImportToolMissingError",
    "SnapshotFileInvalidError",
    "ImportExecutionError",
    "ImportMetadataError",
    "SourceChangedError",
    "SplitError",
    "ResolvedFocus",
    "FocusState",
    "ImportMetadata",
    "MetadataInspection",
    "TemplateParameter",
    "TemplateSummary",
    "TemplateInfo",
    "QueryResult",
    "PeakMemoryReport",
    "ImportOptions",
    "ImportResult",
    "SplitOptions",
    "SplitResult",
    "DeviceTraceBounds",
    "DatabaseOverview",
    "CapabilityCatalog",
    "classify_error",
    "JSON_SCHEMA_VERSION",
    "JsonValue",
    "dumps_json",
    "json_error",
    "json_success",
    "to_jsonable",
    "FocusService",
    "ImportMetadataService",
    "QueryService",
    "QueryLimits",
    "ReportService",
    "ImportService",
    "SplitService",
    "CapabilityService",
    "OverviewService",
]
