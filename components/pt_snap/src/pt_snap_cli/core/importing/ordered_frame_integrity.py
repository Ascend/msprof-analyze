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

"""Producer-owned frame validation, separate from consumer/base-table seals."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Dict

from pt_snap_cli.core.common.frame_json import _bounded_depth, _finite_float, _invalid_constant
from pt_snap_cli.core.dataset.dataset_contract import _unique_object
from pt_snap_cli.core.dataset.dataset_files import readonly_member_uri, require_readonly_member
from pt_snap_cli.core.dataset.query.dataset_frames import SCHEMA


def require_frame_declaration(manifest: Dict[str, object]) -> None:
    extensions = manifest.get("extensions")
    frames = extensions.get("ptSnapOrderedFrames") if isinstance(extensions, dict) else None
    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
    if not isinstance(frames, dict) or type(frames.get("version")) is not int or frames["version"] != 2:
        raise ValueError("Producer ordered-frame declaration is missing or unsupported")


def frame_member_digest(root: Path, member: Path, device: int) -> str:
    """Validate normalized evidence and stream its exact logical content.

    Event coverage may be partial: unencodable optional evidence is intentionally
    omitted by the writer. Every stored reference and frame must still be valid.
    Consumer tables, columns and indexes outside this extension are not hashed.
    """
    # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
    if type(device) is not int or device < 0:
        raise ValueError("Invalid ordered-frame device")
    require_readonly_member(root, member, immutable=True)
    digest = hashlib.sha256()
    with closing(sqlite3.connect(readonly_member_uri(member), uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        for table, schema in SCHEMA.items():
            if conn.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchall() != [("table",)]:
                raise ValueError(f"Ordered-frame table is missing: {table}")
            actual = [(r[1], r[2], r[5]) for r in conn.execute(f'PRAGMA table_info("{table}")')]
            if actual != schema:
                raise ValueError(f"Invalid ordered-frame schema: {table}")
            for column, kind, _ in schema:
                if (
                    kind == "INTEGER"
                    and conn.execute(
                        f'SELECT 1 FROM "{table}" WHERE typeof("{column}") != \'integer\' OR "{column}" < 0 LIMIT 1'  # nosec B608 # Schema identifiers come from the fixed frame-table inventory and integer device ID.
                    ).fetchone()
                ):
                    raise ValueError(f"Invalid ordered-frame integer: {table}.{column}")

        checks = (
            "SELECT 1 FROM pt_snap_stack_frame f LEFT JOIN pt_snap_stack s ON s.stackId=f.stackId "
            "LEFT JOIN pt_snap_frame_value v ON v.id=f.frameId WHERE s.stackId IS NULL OR v.id IS NULL LIMIT 1",
            "SELECT 1 FROM pt_snap_stack s LEFT JOIN (SELECT stackId,COUNT(*) AS n,MIN(frameIndex) AS lo,"
            "MAX(frameIndex) AS hi FROM pt_snap_stack_frame GROUP BY stackId) f ON f.stackId=s.stackId "
            "WHERE s.frameCount!=COALESCE(f.n,0) OR (s.frameCount>0 AND (f.lo!=0 OR f.hi!=s.frameCount-1)) LIMIT 1",
            f"SELECT 1 FROM pt_snap_event_stack e LEFT JOIN pt_snap_stack s ON s.stackId=e.stackId "
            f'LEFT JOIN "trace_entry_{device}" t ON t.id=e.eventId '
            "WHERE s.stackId IS NULL OR t.id IS NULL LIMIT 1",  # nosec B608 # Schema identifiers come from the fixed frame-table inventory and integer device ID.
        )
        for sql in checks:
            if conn.execute(sql).fetchone():
                raise ValueError("Invalid ordered-frame reference, frame count or sequence")

        for table, schema in SCHEMA.items():
            columns = ",".join(f'"{name}"' for name, _, _ in schema)
            keys = ",".join(f'"{name}"' for name, _, pk in schema if pk)
            digest.update(table.encode("ascii") + b"\n")
            for row in conn.execute(f'SELECT {columns} FROM "{table}" ORDER BY {keys}'):  # nosec B608 # Schema identifiers come from the fixed frame-table inventory and integer device ID.
                if table == "pt_snap_frame_value":
                    if not isinstance(row[1], str):
                        raise ValueError("Ordered frame must contain JSON text")
                    try:
                        frame = json.loads(
                            row[1],
                            object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant,
                            parse_float=_finite_float,
                        )
                        if not isinstance(frame, dict) or not _bounded_depth([frame]):
                            raise ValueError("Ordered frame must be a bounded JSON object")
                    except (RecursionError, OverflowError) as exc:
                        raise ValueError("Invalid ordered-frame JSON") from exc
                digest.update(
                    json.dumps(row, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")
                )
                digest.update(b"\n")
    return digest.hexdigest()
