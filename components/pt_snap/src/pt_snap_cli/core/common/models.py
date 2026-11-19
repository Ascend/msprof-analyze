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

from __future__ import annotations

# pyright: reportAny=error, reportExplicitAny=error, reportUnknownArgumentType=error, reportUnknownVariableType=error, reportUnknownMemberType=error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Union

from typing_extensions import Literal

from pt_snap_cli.config import FocusSource

CacheMissReason = Literal[
    "database_missing",
    "database_invalid",
    "metadata_missing",
    "metadata_invalid",
    "metadata_version_unsupported",
    "source_changed",
    "import_format_changed",
    "device_changed",
    "forced",
    "dataset_identity_changed",
]
MetadataStatus = Literal["available", "unavailable", "invalid"]
SplitFormat = Literal["pickle", "json"]


@dataclass(frozen=True)
class ResolvedFocus:
    db_path: Union[Path, None]
    device_id: Union[int, None]
    source: FocusSource
    focus_file: Union[Path, None] = None

    @property
    def is_configured(self) -> bool:
        return self.db_path is not None


@dataclass(frozen=True)
class FocusState:
    db_path: Union[Path, None]
    device_id: Union[int, None]
    available_devices: List[int] = field(default_factory=list)
    source: FocusSource = "none"
    focus_file: Union[Path, None] = None
    callstack_layout: Union[str, None] = None
    callstack_layout_error: Union[str, None] = None


@dataclass(frozen=True)
class TemplateParameter:
    type: str
    default: Union[object, None]
    required: bool
    description: str
    choices: Union[List[object], None] = None


@dataclass(frozen=True)
class TemplateSummary:
    name: str
    description: str
    category: Union[str, None]


@dataclass(frozen=True)
class TemplateInfo:
    name: str
    description: str
    category: Union[str, None]
    devices: Union[str, None]
    parameters: Dict[str, TemplateParameter]
    output_schema: Union[List[Dict[str, object]], None]
    semantics_version: Union[int, None] = None
    interpretation_limits: List[str] = field(default_factory=list)
    dataset_support: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryResult:
    total: int
    returned: int
    device_id: Union[int, None]
    rows: List[Dict[str, object]]
    template: Union[str, None] = None
    semantics_version: Union[int, None] = None
    has_more: bool = False
    truncated: bool = False
    total_is_exact: bool = False
    timeout_s: Union[float, None] = None
    scope: Union[Dict[str, object], None] = None


@dataclass(frozen=True)
class PeakMemoryReport:
    device_id: Union[int, None]
    metric: str
    event_id: Union[int, None]
    peak: Dict[str, object]
    allocator_gap: Union[Dict[str, object], None]
    callstack_groups: List[Dict[str, object]]
    has_more: bool = False
    truncated: bool = False
    total_is_exact: bool = False
    effective_params: Dict[str, object] = field(default_factory=dict)
    included_bytes: int = 0
    percent_denominator: str = "included_bytes"
    active_bytes_at_event: Union[int, None] = None
    coverage_percent: Union[float, None] = None
    source_coverage: Union[Dict[str, object], None] = None
    scope: Union[Dict[str, object], None] = None
    timeout_s: Union[float, None] = None
    budget_scope: str = "report_composition"


@dataclass(frozen=True)
class ImportOptions:
    """Options for `pt-snap import`.

    Attributes:
        snapshot_file: Path to the input `.pkl` or `.pickle` snapshot.
        output_dir: Parent of the generated standalone DB or native dataset.
            Defaults to the snapshot file's parent directory.
        events_per_slice: Positive real-event capacity per device shard; None
            preserves standalone behavior unless msinsight is explicit (500000).
            Negative boundaries do not count.
        format: None selects single-db or pt-snap-native-v2 from capacity;
            msinsight/compatibility-v1 explicitly selects fixed-target inline v1.
        device: Optional device id to focus on. When None, all available
            devices are imported.
        set_focus: When True (default), also write project focus so subsequent
            `pt-snap query` / `pt-snap report` commands reuse the new DB.
    """

    snapshot_file: Path
    output_dir: Union[Path, None] = None
    device: Union[int, None] = None
    set_focus: bool = True
    force: bool = False
    events_per_slice: Union[int, None] = None
    format: Union[str, None] = None


@dataclass(frozen=True)
class ImportMetadata:
    metadata_schema_version: int
    import_format_version: int
    source_sha256: str
    source_size: int
    source_name: str
    requested_device: Union[int, None]
    importer_name: str
    importer_version: str
    completed_at: str


@dataclass(frozen=True)
class MetadataInspection:
    db_path: Path
    status: MetadataStatus
    metadata: Union[ImportMetadata, None] = None
    reason: Union[CacheMissReason, None] = None


@dataclass(frozen=True)
class CacheDecision:
    reused: bool
    metadata: Union[ImportMetadata, None]
    reason: Union[CacheMissReason, None]


@dataclass(frozen=True)
class ImportResult:
    """Result of `pt-snap import`.

    Attributes:
        db_path: Path to the standalone SQLite database or native dataset directory.
        dataset_path: Native dataset directory, or None for standalone imports.
        devices/slice_count/omitted_devices: Complete native output inventory.
        device_id: Device id used during import, or None when not specified.
        focus_state: The FocusState written to project focus when
            options.set_focus is True, otherwise None.
    """

    db_path: Path
    device_id: Union[int, None]
    focus_state: Union[FocusState, None]
    reused: bool
    metadata: Union[ImportMetadata, None]
    cache_miss_reason: Union[CacheMissReason, None]
    dataset_path: Union[Path, None] = None
    devices: Tuple[int, ...] = ()
    slice_count: int = 0
    format: str = "single-db"
    omitted_devices: Tuple[int, ...] = ()


@dataclass(frozen=True)
class SplitOptions:
    snapshot_file: Path
    output: Path
    device: Union[int, None] = None
    slices: Union[int, None] = None
    max_entries: Union[int, None] = None
    format: str = "pickle"


@dataclass(frozen=True)
class SplitResult:
    output: Path
    files: Tuple[Path, ...]
    devices: Tuple[int, ...]
    format: SplitFormat


@dataclass(frozen=True)
class DeviceTraceBounds:
    device_id: int
    first_event_id: Union[int, None]
    last_event_id: Union[int, None]


@dataclass(frozen=True)
class DatabaseOverview:
    db_path: Path
    focus_source: FocusSource
    devices: List[DeviceTraceBounds]
    metadata: MetadataInspection
    dataset: Union[Dict[str, object], None] = None


@dataclass(frozen=True)
class CapabilityCatalog:
    cli_version: str
    templates: List[TemplateInfo]
