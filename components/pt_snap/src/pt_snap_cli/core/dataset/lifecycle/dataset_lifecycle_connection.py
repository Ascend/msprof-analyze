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

"""Shared deadline-aware SQLite connection ownership for lifecycle reductions."""

from __future__ import annotations

import math
import sqlite3
import time
from typing import List, Union

from pt_snap_cli.core.common.errors import QueryExecutionError
from pt_snap_cli.core.dataset.dataset_contract import SliceRecord
from pt_snap_cli.core.dataset.dataset_files import readonly_member_uri, require_readonly_member
from pt_snap_cli.core.dataset.dataset_sources import DatasetSourceResolver


class _AttachedSources:
    def __init__(
        self,
        sources: DatasetSourceResolver,
        items: Union[List[SliceRecord], None] = None,
        *,
        database: str = ":memory:",
    ) -> None:
        self.sources = sources
        self.items = sources.device.slices if items is None else items
        remaining = sources.budget.remaining()
        self.connection = sqlite3.connect(
            database, uri=True, timeout=min(5.0, remaining) if remaining is not None else 5.0
        )
        self.connection.row_factory = sqlite3.Row

    def _configure_deadline(self):
        budget = self.sources.budget
        remaining = budget.remaining()
        deadline = budget.started + budget.timeout_s if budget.timeout_s is not None else None
        self.connection.set_progress_handler(
            (lambda: int(time.monotonic() >= deadline)) if deadline is not None else None, 1000
        )
        # SQLite's default five-second lock wait must not outlive the operation.
        wait_ms = math.ceil(1000 * min(5.0, remaining)) if remaining is not None else 5000
        self.connection.execute(f"PRAGMA busy_timeout={wait_ms}")

    def __enter__(self):
        try:
            self._configure_deadline()
            self.connection.execute("PRAGMA trusted_schema=OFF")
            for item in self.items:
                self._configure_deadline()
                path = self.sources.dataset.root / item.file
                immutable = self.sources.dataset.callstack_layout == "v1"
                require_readonly_member(self.sources.dataset.root, path, immutable=immutable)
                uri = readonly_member_uri(path, immutable)
                self.connection.execute(f'ATTACH DATABASE ? AS "s{item.index}"', [uri])
            self.connection.execute("PRAGMA query_only=ON")
            self.sources.budget.remaining()
            return self
        except BaseException as exc:
            self.connection.set_progress_handler(None, 0)
            self.connection.close()
            if isinstance(exc, sqlite3.Error):
                self.sources.budget.remaining()
                raise QueryExecutionError(str(exc)) from exc
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.connection.set_progress_handler(None, 0)
        self.connection.close()
        return False

    def read(self, sql: str, values: Union[List[object], None] = None):
        budget = self.sources.budget
        cursor = self.connection.cursor()
        self.sources.query_count += 1
        try:
            self._configure_deadline()
            cursor.execute(sql, values or [])
            result = []
            while True:
                batch = cursor.fetchmany(256)
                if not batch:
                    break
                rows = [dict(row) for row in batch]
                budget.consume(rows)
                result.extend(rows)
            budget.remaining()
            return result
        except (sqlite3.Error, OverflowError) as exc:
            budget.remaining()  # Preserve the domain timeout on interruption.
            raise QueryExecutionError(str(exc)) from exc
        finally:
            cursor.close()
            self.connection.set_progress_handler(None, 0)
