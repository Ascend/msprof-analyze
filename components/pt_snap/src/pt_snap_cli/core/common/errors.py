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

from pathlib import Path
from typing import Tuple, Type

from typing_extensions import Literal


class PtSnapCoreError(Exception):
    pass


class FocusNotConfiguredError(PtSnapCoreError):
    pass


class FocusFileInvalidError(PtSnapCoreError):
    pass


class DatabaseMissingError(PtSnapCoreError):
    pass


class DatabaseSchemaError(PtSnapCoreError):
    pass


class InvalidDeviceError(PtSnapCoreError):
    pass


class InvalidCategoryError(PtSnapCoreError):
    pass


class TemplateNotFoundError(PtSnapCoreError):
    pass


class TemplateRenderError(PtSnapCoreError):
    pass


class QueryExecutionError(PtSnapCoreError):
    pass


class InvalidParameterError(QueryExecutionError):
    """Raised when a query argument or environment value is not valid."""

    pass


class QueryTimeoutError(QueryExecutionError):
    """Raised when a query exceeds its configured execution timeout."""

    pass


class QueryCancelledError(QueryExecutionError):
    """An obsolete query was interrupted; no partial result is returned."""


class ImportToolMissingError(PtSnapCoreError):
    """Raised when the built-in snapshot import backend is unavailable.

    The backend is part of msprof-analyze, so this indicates a packaging or
    installation problem rather than a missing optional tool.
    """

    pass


class SnapshotFileInvalidError(PtSnapCoreError):
    """Raised when a candidate snapshot pickle file cannot be used as input.

    Triggers include: path does not exist, path is not a regular file,
    suffix is not .pkl or .pickle, file cannot be unpickled, or the
    unpickled top-level object is not a dict.
    """

    pass


class ImportExecutionError(PtSnapCoreError):
    """Raised when the import backend itself fails to produce a database.

    Covers the snapshot adaptor returning False, raising an exception,
    or producing no .db artifact where one was expected.
    """

    pass


class ImportMetadataError(PtSnapCoreError):
    """Raised when import metadata cannot be read, written, or validated."""

    pass


class SourceChangedError(ImportExecutionError):
    """Raised when the source snapshot changes while an import is running."""

    pass


SplitPhase = Literal[
    "argument",
    "path",
    "device",
    "conflict",
    "load/engine",
    "generated-validation",
    "publication",
]


class SplitError(PtSnapCoreError):
    """A phase-identifying split failure suitable for CLI presentation."""

    phase: SplitPhase
    source_path: Path
    detail: str

    def __init__(self, phase: SplitPhase, source_path: Path, detail: str) -> None:
        self.phase = phase
        self.source_path = source_path
        self.detail = detail
        super().__init__(f"Split {phase} failed for '{source_path}': {detail}")

    def __reduce__(self) -> Tuple[Type[SplitError], Tuple[SplitPhase, Path, str]]:
        return type(self), (self.phase, self.source_path, self.detail)
