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

"""Native dataset publication: exclusive renames, explicit compensation, no crash guarantee."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Tuple, Union

from pt_snap_cli.core.common.errors import ImportExecutionError
from pt_snap_cli.core.dataset.dataset_contract import DatasetContractError
from pt_snap_cli.core.dataset.dataset_resolver import _hash_file
from pt_snap_cli.core.dataset.native_dataset_contract import (
    NativeManifest,
    read_native_manifest,
    require_native_members,
)
from pt_snap_cli.core.splitting.sharded_replay_service import (
    ShardedReplayResult,
    ShardedReplayService,
)
from pt_snap_cli.core.splitting.split_service import SplitService

DirectoryIdentity = Tuple[int, int, Union[int, None]]


@dataclass(frozen=True)
class TargetState:
    device: int
    inode: int
    files: Tuple[Tuple[str, str], ...]


class DatasetImportBackend:
    def __init__(self, replay: Union[ShardedReplayService, None] = None):
        self.replay = replay or ShardedReplayService()

    @staticmethod
    def target_path(source: Path, output_dir: Path) -> Path:
        return output_dir / f"{source.name}.pt-snap-native-v2"

    @staticmethod
    def inspect_target(target: Path) -> Union[Tuple[NativeManifest, TargetState], None]:
        if not target.exists() and not target.is_symlink():
            return None
        try:
            if target.resolve() != target or target.is_symlink() or not target.is_dir():
                raise ValueError("Target must be a canonical non-symlink native dataset directory")
            manifest = read_native_manifest(target)
            require_native_members(target, manifest)
            status = target.lstat()
            files = tuple(
                (name, _hash_file(target / name))
                for name in sorted(["manifest.json", *(s.file for d in manifest.devices for s in d.slices)])
            )
            return manifest, TargetState(status.st_dev, status.st_ino, files)
        except (DatasetContractError, OSError, ValueError) as exc:
            raise ImportExecutionError(f"Existing target is not a recognized native dataset; preserved: {exc}") from exc

    @staticmethod
    def _verify(path: Path, identity: DirectoryIdentity) -> None:
        if path.resolve() != path:
            raise OSError(f"Noncanonical or substituted directory: {path}")
        SplitService._verify_stage_identity(path, identity)

    @classmethod
    def _remove(cls, path: Path, identity: DirectoryIdentity) -> None:
        cls._verify(path, identity)
        # shutil.rmtree does not traverse child symlink targets. The root is held
        # by an inode-checked descriptor from secure task allocation/recognition.
        shutil.rmtree(path)

    @classmethod
    def _move(cls, source: Path, destination: Path, identity: DirectoryIdentity) -> None:
        cls._verify(source, identity)
        if destination.parent.resolve() != destination.parent or destination.is_symlink():
            raise OSError(f"Unsafe publication destination: {destination}")
        SplitService._publish_directory(source, destination)

    @classmethod
    def _matches(cls, path: Path, identity: DirectoryIdentity) -> bool:
        try:
            cls._verify(path, identity)
            return True
        except OSError:
            return False

    def dump_to_dataset(
        self,
        source: Path,
        target: Path,
        *,
        capacity: int,
        device: Union[int, None],
        expected: Union[TargetState, None],
        finalize: Callable[[ShardedReplayResult], None],
        post_publish: Union[Callable[[Path], None], None] = None,
        pre_publish: Union[Callable[[], None], None] = None,
    ) -> Path:
        if target.resolve() != target or target.parent.resolve() != target.parent or target.is_symlink():
            raise ImportExecutionError("Dataset output must be canonical and non-symlink.")
        stage: Union[Path, None] = None
        recovery: Union[Path, None] = None
        stage_id: Union[DirectoryIdentity, None] = None
        recovery_id: Union[DirectoryIdentity, None] = None
        old_id: Union[DirectoryIdentity, None] = None
        new_id: Union[DirectoryIdentity, None] = None
        preserve = False
        try:
            SplitService._preflight_publication()
            target.parent.mkdir(parents=True, exist_ok=True)
            current = self.inspect_target(target)
            if (current[1] if current else None) != expected:
                raise OSError("Dataset destination changed before staging; preserved")
            if expected is not None:
                old_id = SplitService._stage_identity(target)
            stage = Path(tempfile.mkdtemp(dir=target.parent, prefix=f".{target.name}.stage-"))
            stage_id = SplitService._stage_identity(stage)
            artifact = stage / "artifact"
            result = self.replay.stage(source, artifact, events_per_slice=capacity, device=device)
            self._verify(stage, stage_id)
            new_id = SplitService._stage_identity(artifact)
            finalize(result)
            self._verify(artifact, new_id)
            current = self.inspect_target(target) if expected is not None else None
            if (current[1] if current is not None else None) != expected:
                raise OSError("Dataset destination changed during import; preserved")
            if pre_publish is not None:
                pre_publish()
            try:
                if old_id is not None:
                    self._verify(target, old_id)
                    recovery = Path(tempfile.mkdtemp(dir=target.parent, prefix=f".{target.name}.recovery-"))
                    recovery_id = SplitService._stage_identity(recovery)
                    self._move(target, recovery / "previous", old_id)
                self._move(artifact, target, new_id)
                if post_publish is not None:
                    post_publish(target)
            except BaseException as publish_error:
                try:
                    # Detect successful rename BEFORE an injected call raises.
                    # Never remove an independently created/substituted target.
                    if self._matches(target, new_id):
                        self._remove(target, new_id)
                    if old_id is not None:
                        if not self._matches(target, old_id):
                            if (
                                recovery is None
                                or recovery_id is None
                                or not self._matches(recovery / "previous", old_id)
                            ):
                                raise OSError("Previous artifact is missing or substituted; recovery cannot be trusted")
                            self._verify(recovery, recovery_id)
                            previous = self.inspect_target(recovery / "previous")
                            if previous is None or previous[1] != expected:
                                raise OSError(
                                    "Recovery artifact changed; preserve evidence instead of restoring unknown data"
                                )
                            try:
                                self._move(recovery / "previous", target, old_id)
                            except BaseException:
                                # A late exception may follow a successful restore.
                                restored = self.inspect_target(target)
                                if not self._matches(target, old_id) or restored is None or restored[1] != expected:
                                    raise
                        restored = self.inspect_target(target)
                        if restored is None or restored[1] != expected:
                            raise OSError("Previous artifact was not restored exactly; preserve recovery evidence")
                except BaseException as rollback_error:
                    preserve = True
                    raise ImportExecutionError(
                        f"Dataset publication/focus failed; directory rollback also failed: {rollback_error}. "
                        f"Recovery directory: {recovery}; staging evidence: {stage}."
                    ) from publish_error
                raise
            # The transaction is committed only after the focus callback returns.
            if recovery is not None and old_id is not None:
                try:
                    previous = self.inspect_target(recovery / "previous")
                    if previous is None or previous[1] != expected:
                        raise OSError("Recovery artifact changed; do not delete unknown contents")
                    self._remove(recovery / "previous", old_id)
                except Exception as exc:
                    preserve = True
                    raise ImportExecutionError(
                        f"Dataset publication committed but recovery cleanup failed; preserved evidence at {recovery}: {exc}"
                    ) from exc
            return target
        except ImportExecutionError:
            raise
        except Exception as exc:
            raise ImportExecutionError(f"Dataset import backend failed: {exc}") from exc
        finally:
            try:
                if not preserve:
                    for path, identity in ((stage, stage_id), (recovery, recovery_id)):
                        if path is not None and identity is not None:
                            try:
                                self._remove(path, identity)
                            except OSError as exc:
                                raise ImportExecutionError(
                                    f"Dataset cleanup failed; preserved recovery evidence at {path}: {exc}"
                                ) from exc
            finally:
                for identity in (new_id, old_id, stage_id, recovery_id):
                    if identity is not None:
                        SplitService._close_stage_identity(identity)
