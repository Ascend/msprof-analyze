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

"""Pure import-metadata value contract shared by standalone and dataset readers."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Mapping, cast

from pt_snap_cli.core.common.models import ImportMetadata


def required_int(value: object) -> int:
    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
    if type(value) is not int:
        raise TypeError("Expected integer metadata value")
    return cast(int, value)


def required_str(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("Expected non-empty metadata string")
    return value


def validate_import_metadata(metadata: ImportMetadata) -> None:
    if metadata.metadata_schema_version < 1 or metadata.import_format_version < 1:
        raise ValueError("Metadata versions must be positive integers")
    if not re.fullmatch(r"[0-9a-f]{64}", metadata.source_sha256):
        raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
    if metadata.source_size < 0 or not metadata.source_name:
        raise ValueError("Source metadata is invalid")
    if metadata.requested_device is not None and metadata.requested_device < 0:
        raise ValueError("requested_device must be non-negative")
    if not metadata.importer_name or not metadata.importer_version:
        raise ValueError("Importer metadata is invalid")
    parsed_time = datetime.fromisoformat(metadata.completed_at)
    if parsed_time.tzinfo is None or parsed_time.utcoffset() != timedelta(0):
        raise ValueError("completed_at must use UTC")


def metadata_from_mapping(row: Mapping[str, object]) -> ImportMetadata:
    device = row["requested_device"]
    metadata = ImportMetadata(
        required_int(row["metadata_schema_version"]),
        required_int(row["import_format_version"]),
        required_str(row["source_sha256"]),
        required_int(row["source_size"]),
        required_str(row["source_name"]),
        None if device is None else required_int(device),
        required_str(row["importer_name"]),
        required_str(row["importer_version"]),
        required_str(row["completed_at"]),
    )
    validate_import_metadata(metadata)
    return metadata
