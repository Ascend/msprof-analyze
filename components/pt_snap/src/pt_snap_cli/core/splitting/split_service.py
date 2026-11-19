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

import ctypes
import errno
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from stat import S_ISDIR, S_ISLNK
from typing import Dict, List, NoReturn, Tuple, Union, cast

from pt_snap_cli.core.common.errors import SplitError, SplitPhase
from pt_snap_cli.core.common.models import SplitFormat, SplitOptions, SplitResult
from pt_snap_cli.snapshot.representation import (
    UnsafePickleError,
    load_snapshot_representation,
    replay_snapshot,
    save_snapshot_representation,
)
from pt_snap_cli.snapshot.tools.slice_dump.hooker import SliceDumpHooker

_ENTRY_RANGE = re.compile(r"_entry_(\d+)_(\d+)\.pkl$")
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_RENAME_EXCL = 0x00000004
_StageIdentity = Tuple[int, int, Union[int, None]]


class SplitService:
    """Replay, validate, and atomically publish snapshot slices."""

    def split(self, options: SplitOptions) -> SplitResult:
        source = options.snapshot_file
        self._validate_before_load(options)
        try:
            self._preflight_publication()
        except Exception as exc:
            self._fail("publication", source, str(exc), exc)

        try:
            representation = load_snapshot_representation(source, "pickle")
        except UnsafePickleError as exc:
            self._fail("load/engine", source, f"unsafe pickle: {exc}", exc)
        except Exception as exc:
            self._fail("load/engine", source, str(exc), exc)

        traces = representation.get("device_traces")
        if not isinstance(traces, list):
            self._fail("device", source, "snapshot has no device trace list")
        nonempty_devices = [index for index, entries in enumerate(traces) if entries]
        if options.device is not None:
            if options.device not in nonempty_devices:
                self._fail(
                    "device",
                    source,
                    f"device {options.device} does not exist or has no trace entries",
                )
            devices = [options.device]
        else:
            devices = nonempty_devices
            if not devices:
                self._fail("device", source, "snapshot has no device with trace entries")

        output = options.output
        try:
            stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.pt-snap-", dir=str(output.parent)))
            stage_identity = self._stage_identity(stage)
        except Exception as exc:
            self._fail("publication", source, f"cannot create staging directory: {exc}", exc)
        published_files: List[Path] = []
        try:
            for device in devices:
                generated = self._slice_device(
                    representation,
                    source,
                    stage,
                    device,
                    options.slices,
                    options.max_entries,
                    cast(SplitFormat, options.format),
                )
                published_files.extend(generated)
            self._verify_stage_identity(stage, stage_identity)
            self._publish_directory(stage, output)
            self._close_stage_identity(stage_identity)
        except SplitError:
            self._cleanup_stage(stage, stage_identity)
            raise
        except Exception as exc:
            self._cleanup_stage(stage, stage_identity)
            self._fail("publication", source, str(exc), exc)

        return SplitResult(
            output=output,
            files=tuple(output / path.name for path in published_files),
            devices=tuple(devices),
            format=cast(SplitFormat, options.format),
        )

    def _validate_before_load(self, options: SplitOptions) -> None:
        source = options.snapshot_file
        if (options.slices is None) == (options.max_entries is None):
            self._fail("argument", source, "exactly one of --slices and --max-entries is required")
        strategy = options.slices if options.slices is not None else options.max_entries
        if strategy is None or strategy <= 0:
            self._fail("argument", source, "the split strategy value must be positive")
        if options.format not in ("pickle", "json"):
            self._fail("argument", source, "format must be exactly 'pickle' or 'json'")
        if not source.exists():
            self._fail("path", source, "source does not exist")
        if not source.is_file():
            self._fail("path", source, "source is not a regular file")
        if source.suffix.lower() not in (".pkl", ".pickle"):
            self._fail("path", source, "source suffix must be .pkl or .pickle")
        if options.device is not None and options.device < 0:
            self._fail("device", source, "device must be non-negative")
        if not options.output.parent.exists():
            self._fail("path", source, f"output parent does not exist: {options.output.parent}")
        if not options.output.parent.is_dir():
            self._fail("path", source, f"output parent is not a directory: {options.output.parent}")
        if os.path.lexists(options.output):
            self._fail("conflict", source, f"destination already exists: {options.output}")

    def _slice_device(
        self,
        representation: Dict[str, object],
        source: Path,
        stage: Path,
        device: int,
        slices: Union[int, None],
        max_entries: Union[int, None],
        output_format: SplitFormat,
    ) -> List[Path]:
        try:
            raw_dir = stage / f".device-{device}"
            raw_dir.mkdir()
            event_count = len(cast(List[List[object]], representation["device_traces"])[device])
            hooker = SliceDumpHooker(
                dump_dir=str(raw_dir),
                num_of_slices=slices if slices is not None else 1,
                max_entries=max_entries if max_entries is not None else event_count,
                dump_type="pkl",
            )
            # Slices serialize the original frame dictionaries, so eager Frame
            # objects would be rebuilt only to be discarded.
            _, replayed = replay_snapshot(representation, device, hooker=hooker, _raw_frames=True)
        except Exception as exc:
            self._fail("load/engine", source, f"device {device}: {exc}", exc)
        if not replayed:
            self._fail("load/engine", source, f"device {device}: replay engine returned false")

        try:
            raw_files = sorted(raw_dir.glob("*.pkl"), key=self._slice_start)
        except Exception as exc:
            self._fail("generated-validation", source, str(exc), exc)
        if not raw_files:
            self._fail("load/engine", source, f"device {device}: engine generated no slices")

        extension = "pkl" if output_format == "pickle" else "json"
        outputs: List[Path] = []
        for index, raw_file in enumerate(raw_files):
            try:
                slice_representation = load_snapshot_representation(raw_file, "pickle")
                output_file = stage / (f"{source.stem}__device-{device}__slice-{index}.{extension}")
                save_snapshot_representation(slice_representation, output_file, output_format)
                generated = load_snapshot_representation(output_file, output_format)
                traces = generated.get("device_traces")
                if (
                    not isinstance(traces, list)
                    or device >= len(traces)
                    or not isinstance(traces[device], list)
                    or not traces[device]
                ):
                    raise ValueError(f"generated slice has no trace entries for device {device}")
                _, replayed = replay_snapshot(generated, device, _raw_frames=True)
                if not replayed:
                    raise ValueError("replay returned false")
            except Exception as exc:
                self._fail(
                    "generated-validation",
                    source,
                    f"generated slice for device {device} failed validation: {exc}",
                    exc,
                )
            outputs.append(output_file)
        shutil.rmtree(raw_dir)
        return outputs

    @staticmethod
    def _slice_start(path: Path) -> int:
        match = _ENTRY_RANGE.search(path.name)
        if match is None:
            raise ValueError(f"Unexpected engine output name: {path.name}")
        return int(match.group(1))

    @staticmethod
    def _stage_identity(stage: Path) -> _StageIdentity:
        status = stage.lstat()
        if S_ISLNK(status.st_mode) or not S_ISDIR(status.st_mode):
            raise OSError(errno.EINVAL, "staging path is not an owned directory", stage)
        descriptor: Union[int, None] = None
        if os.name != "nt":
            descriptor = os.open(stage, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                held_status = os.fstat(descriptor)
                if (held_status.st_dev, held_status.st_ino) != (status.st_dev, status.st_ino):
                    raise OSError(errno.ESTALE, "staging directory identity changed", stage)
            except Exception:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
        return status.st_dev, status.st_ino, descriptor

    @classmethod
    def _verify_stage_identity(cls, stage: Path, identity: _StageIdentity) -> None:
        status = stage.lstat()
        if S_ISLNK(status.st_mode) or not S_ISDIR(status.st_mode):
            raise OSError(errno.EINVAL, "staging path is not an owned directory", stage)
        expected = identity[:2]
        if (status.st_dev, status.st_ino) != expected:
            raise OSError(errno.ESTALE, "staging directory identity changed", stage)
        descriptor = identity[2]
        if descriptor is not None:
            held_status = os.fstat(descriptor)
            if (held_status.st_dev, held_status.st_ino) != expected:
                raise OSError(errno.ESTALE, "staging directory identity changed", stage)

    @staticmethod
    def _close_stage_identity(identity: _StageIdentity) -> None:
        descriptor = identity[2]
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    @classmethod
    def _cleanup_stage(cls, stage: Path, identity: _StageIdentity) -> None:
        try:
            cls._verify_stage_identity(stage, identity)
            shutil.rmtree(stage)
        except Exception:
            return
        finally:
            cls._close_stage_identity(identity)

    @staticmethod
    def _preflight_publication() -> None:
        if sys.platform == "darwin":
            if getattr(ctypes.CDLL(None, use_errno=True), "renamex_np", None) is None:
                raise OSError(errno.ENOTSUP, "renamex_np(RENAME_EXCL) is unavailable")
            return
        if sys.platform.startswith("linux"):
            if getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None) is None:
                raise OSError(errno.ENOTSUP, "renameat2(RENAME_NOREPLACE) is unavailable")
            return
        if os.name == "nt":
            return
        raise OSError(errno.ENOTSUP, "atomic no-replace directory rename is unavailable")

    @staticmethod
    def _publish_directory(stage: Path, destination: Path) -> None:
        if sys.platform == "darwin":
            libc = ctypes.CDLL(None, use_errno=True)
            renamex_np = libc.renamex_np
            renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
            renamex_np.restype = ctypes.c_int
            if renamex_np(os.fsencode(stage), os.fsencode(destination), _RENAME_EXCL) != 0:
                error_number = ctypes.get_errno()
                raise OSError(error_number, os.strerror(error_number), destination)
            return
        if sys.platform.startswith("linux"):
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is None:
                raise OSError(errno.ENOTSUP, "atomic no-replace directory rename is unavailable")
            renameat2.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            renameat2.restype = ctypes.c_int
            if (
                renameat2(
                    _AT_FDCWD,
                    os.fsencode(stage),
                    _AT_FDCWD,
                    os.fsencode(destination),
                    _RENAME_NOREPLACE,
                )
                != 0
            ):
                error_number = ctypes.get_errno()
                raise OSError(error_number, os.strerror(error_number), destination)
            return
        if os.name == "nt":
            os.rename(stage, destination)
            return
        raise OSError(errno.ENOTSUP, "atomic no-replace directory rename is unavailable")

    @staticmethod
    def _fail(
        phase: SplitPhase,
        source: Path,
        detail: str,
        cause: Union[BaseException, None] = None,
    ) -> NoReturn:
        error = SplitError(phase=phase, source_path=source, detail=detail)
        if cause is None:
            raise error
        raise error from cause
