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

import os
import pickle  # nosec B403 # Trusted snapshot format; restricted loader and consent boundary are documented.
import sqlite3
import tempfile
from contextlib import ExitStack, suppress
from pathlib import Path
from typing import Callable, Union

from pt_snap_cli._compat import unlink_missing_ok
from pt_snap_cli.core.common.errors import ImportExecutionError, ImportToolMissingError
from pt_snap_cli.snapshot.representation import UnsafePickleError


class SnapshotImportBackend:
    """Stable adapter over the first-party snapshot-to-database implementation."""

    def dump_to_db(
        self,
        snapshot_file: Path,
        output_dir: Path,
        device: Union[int, None] = None,
        finalize_temp_db: Union[Callable[[Path], None], None] = None,
        post_publish: Union[Callable[[Path], None], None] = None,
    ) -> Path:
        db_path = self.target_db_path(snapshot_file, output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        run_dump_to_db = self._load_run_dump_to_db()

        with tempfile.TemporaryDirectory(dir=output_dir) as tmp_dir_name, ExitStack() as cleanup:
            tmp_dir = Path(tmp_dir_name)
            tmp_db_path = tmp_dir / db_path.name
            try:
                ok = run_dump_to_db(
                    snapshot_file=str(snapshot_file),
                    dump_dir=str(tmp_dir),
                    device=device,
                )
            except UnsafePickleError as exc:
                raise ImportExecutionError(f"Snapshot pickle rejected: {exc}") from exc
            except (OSError, sqlite3.DatabaseError, pickle.UnpicklingError, ValueError) as exc:
                raise ImportExecutionError(f"Snapshot import backend failed: {exc}") from exc

            if not ok:
                raise ImportExecutionError("Snapshot import backend reported failure.")
            if not tmp_db_path.is_file():
                raise ImportExecutionError(f"Expected database not produced: {tmp_db_path}")

            if finalize_temp_db is not None:
                finalize_temp_db(tmp_db_path)

            had_destination = db_path.exists()
            backup_path: Union[Path, None] = None
            backup_fd: Union[int, None] = None

            def close_backup() -> None:
                if backup_fd is not None:
                    with suppress(OSError):
                        os.close(backup_fd)

            cleanup.callback(close_backup)
            try:
                if had_destination and post_publish is not None:
                    backup_fd, backup_name = tempfile.mkstemp(
                        dir=output_dir,
                        prefix=f".{db_path.name}.",
                        suffix=".rollback",
                    )
                    backup_path = Path(backup_name)
                    try:
                        try:
                            source_mode = db_path.stat().st_mode & 0o777
                        except OSError:
                            source_mode = 0o600
                        with open(db_path, "rb") as src:
                            while True:
                                chunk = src.read(1024 * 1024)
                                if not chunk:
                                    break
                                remaining = memoryview(chunk)
                                while remaining:
                                    written = os.write(backup_fd, remaining)
                                    if written <= 0:
                                        raise OSError("Could not write rollback backup")
                                    remaining = remaining[written:]
                        if hasattr(os, "fchmod"):
                            os.fchmod(backup_fd, source_mode or 0o600)
                    except BaseException:
                        try:
                            os.close(backup_fd)
                        except OSError:
                            pass
                        unlink_missing_ok(backup_path)
                        backup_path = None
                        backup_fd = None
                        raise
                os.replace(tmp_db_path, db_path)
            except OSError as exc:
                # Windows cannot unlink a file while its mkstemp handle is open.
                # Publication has not committed, so release the secure backup
                # before removing it; the original destination is still intact.
                close_backup()
                backup_fd = None
                if backup_path is not None:
                    try:
                        unlink_missing_ok(backup_path)
                    except OSError:
                        pass
                raise ImportExecutionError(f"Snapshot import backend failed: {exc}") from exc

            try:
                if post_publish is not None:
                    post_publish(db_path)
            except BaseException as publish_exc:
                try:
                    if backup_fd is not None and backup_path is not None:
                        # Read the secure backup fd into a file in our private
                        # staging directory. Never open the published path for
                        # writing: it may now alias an unrelated file.
                        os.lseek(backup_fd, 0, os.SEEK_SET)
                        with tempfile.NamedTemporaryFile(mode="wb", dir=tmp_dir, delete=False) as dst:
                            restore_path = Path(dst.name)
                            while True:
                                chunk = os.read(backup_fd, 1024 * 1024)
                                if not chunk:
                                    break
                                dst.write(chunk)
                            if hasattr(os, "fchmod"):
                                os.fchmod(dst.fileno(), os.fstat(backup_fd).st_mode & 0o777)
                        # Close the staging handle before replacing on Windows.
                        os.replace(restore_path, db_path)
                        os.close(backup_fd)
                        backup_fd = None
                        unlink_missing_ok(backup_path)
                        backup_path = None
                    else:
                        unlink_missing_ok(db_path)
                except OSError as rollback_exc:
                    recovery = (
                        f" Recovery backup: {backup_path}." if backup_path is not None and backup_path.exists() else ""
                    )
                    raise ImportExecutionError(
                        "Snapshot import post-publication action failed and database rollback "
                        f"also failed: {rollback_exc}.{recovery}"
                    ) from publish_exc
                raise

            if backup_fd is not None:
                try:
                    os.close(backup_fd)
                except OSError:
                    pass
                backup_fd = None
            if backup_path is not None:
                try:
                    unlink_missing_ok(backup_path)
                except OSError:
                    # Publication and focus are committed; an orphan backup is safer
                    # than reporting a failure after the transaction succeeded.
                    pass

        return db_path

    @staticmethod
    def target_db_path(snapshot_file: Path, output_dir: Path) -> Path:
        return output_dir / f"{snapshot_file.name}.db"

    @staticmethod
    def _load_run_dump_to_db():
        try:
            from pt_snap_cli.snapshot.tools.adaptors.snapshot2db import run_dump_to_db
        except ImportError as exc:
            raise ImportToolMissingError(
                "Snapshot import backend is unavailable. Reinstall msprof-analyze; the package may be incomplete."
            ) from exc
        return run_dump_to_db
