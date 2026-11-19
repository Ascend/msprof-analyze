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

import importlib
import pickle
import sys
from contextlib import closing
from pathlib import Path

import pytest

from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.context import Context
from pt_snap_cli.core.common.errors import (
    ImportExecutionError,
    ImportToolMissingError,
    InvalidDeviceError,
    SnapshotFileInvalidError,
)
from pt_snap_cli.core.common.models import ImportOptions
from test.snapshot.test_file_util import UNSAFE_PICKLE_PAYLOAD, write_unsafe_reduce_pickle

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "snapshots"
EMPTY_CACHE_SNAPSHOT = FIXTURE_DIR / "snapshot_with_empty_cache.pkl"
MULTI_DEVICE_SNAPSHOT = FIXTURE_DIR / "snapshot_with_multi_devices.pkl"


@pytest.fixture(autouse=True)
def isolate_focus_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PT_SNAP_DB_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _import_service_type():
    from pt_snap_cli.core.importing.import_service import ImportService

    return ImportService


def test_import_writes_db_and_sets_focus(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    project_dir = tmp_path / "project"
    output_dir = tmp_path / "output"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    result = service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=output_dir))

    assert result.db_path.exists()
    assert result.db_path.suffix == ".db"
    assert (project_dir / ".pt-snap" / "focus.json").exists()
    assert not (output_dir / ".pt-snap" / "focus.json").exists()
    assert result.reused is False
    assert result.cache_miss_reason == "database_missing"


@pytest.mark.slow
def test_import_with_multi_device_fixture(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()

    result = service.import_snapshot(ImportOptions(snapshot_file=MULTI_DEVICE_SNAPSHOT, output_dir=tmp_path))

    assert len(Context(result.db_path).discover_devices()) >= 2


def test_import_returns_focus_state(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()

    result = service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path))

    assert result.focus_state is not None
    assert result.focus_state.source == "project"


def test_import_snapshot_file_invalid_missing(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()

    with pytest.raises(SnapshotFileInvalidError):
        service.import_snapshot(ImportOptions(snapshot_file=tmp_path / "missing.pkl"))


def test_import_snapshot_file_invalid_suffix(tmp_path: Path) -> None:
    """Wrong suffix is rejected before the snapshot backend is invoked."""
    import_service_cls = _import_service_type()
    service = import_service_cls()
    snapshot_file = tmp_path / "foo.txt"
    snapshot_file.write_bytes(b"any content is fine here - suffix is the only check")

    with pytest.raises(SnapshotFileInvalidError, match=r"\.pkl|\.pickle|suffix"):
        service.import_snapshot(ImportOptions(snapshot_file=snapshot_file))


def test_import_snapshot_file_invalid_corrupt_pickle(tmp_path: Path) -> None:
    """A .pkl file that cannot be unpickled surfaces as an import execution error.

    After removing the redundant upfront pickle.load, the suffix check passes
    for ``.pkl`` and the failure is reported by the snapshot backend, which
    surfaces as :class:`ImportExecutionError`.
    """
    import_service_cls = _import_service_type()
    service = import_service_cls()
    snapshot_file = tmp_path / "corrupt.pkl"
    # Real pickle protocol header followed by garbage: passes suffix check,
    # fails inside the shared first-party representation loader.
    snapshot_file.write_bytes(b"\x80\x04not a valid pickle stream")

    with pytest.raises(ImportExecutionError, match=r"backend (failed|reported failure)"):
        service.import_snapshot(ImportOptions(snapshot_file=snapshot_file))

    assert not (tmp_path / "corrupt.pkl.db").exists()


def test_import_rejects_pickle_with_non_allowlisted_global(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    snapshot_file = write_unsafe_reduce_pickle(tmp_path / "evil.pkl")

    with pytest.raises(ImportExecutionError, match=r"Snapshot pickle rejected:.*Unsafe pickle"):
        service.import_snapshot(ImportOptions(snapshot_file=snapshot_file))

    assert UNSAFE_PICKLE_PAYLOAD["executed"] is False
    assert not (tmp_path / "evil.pkl.db").exists()


def test_failed_reimport_preserves_existing_database(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    result = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    original_size = result.db_path.stat().st_size
    assert Context(result.db_path).discover_devices()

    with pytest.raises(ImportExecutionError, match=r"backend (failed|reported failure)"):
        service.import_snapshot(
            ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, device=999, set_focus=False)
        )

    assert result.db_path.exists()
    assert result.db_path.stat().st_size == original_size
    assert Context(result.db_path).discover_devices()


def test_import_replaces_destination_errors_are_wrapped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()

    def fail_replace(*args: object) -> None:
        raise OSError("cannot replace")

    monkeypatch.setattr("pt_snap_cli.core.importing.snapshot_import_backend.os.replace", fail_replace)

    with pytest.raises(ImportExecutionError, match="cannot replace"):
        service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False))


def test_snapshot_import_backend_lazy_loads_exact_runtime_module() -> None:
    sys.modules.pop("pt_snap_cli.core.importing.snapshot_import_backend", None)
    runtime_module = "pt_snap_cli.snapshot.tools.adaptors.snapshot2db"
    sys.modules.pop(runtime_module, None)

    importlib.import_module("pt_snap_cli.core.importing.snapshot_import_backend")

    assert runtime_module not in sys.modules


def test_import_raises_on_missing_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()

    def raise_missing_tool(*args: object, **kwargs: object) -> Path:
        raise ImportToolMissingError(
            "Snapshot import backend is unavailable. Reinstall pt-snap-cli; the package may be incomplete."
        )

    monkeypatch.setattr(service._backend, "dump_to_db", raise_missing_tool)

    with pytest.raises(ImportToolMissingError, match="Snapshot import backend"):
        service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path))


def test_import_raises_on_upstream_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A backend that raises ImportExecutionError is propagated as-is."""
    import_service_cls = _import_service_type()
    service = import_service_cls()

    def fail_dump_to_db(
        snapshot_file: Path,
        dump_dir: Path,
        device: int | None,
        finalize_temp_db=None,
        post_publish=None,
    ) -> Path:
        raise ImportExecutionError("Snapshot import backend failed: runtime failed")

    monkeypatch.setattr(service._backend, "dump_to_db", fail_dump_to_db)

    with pytest.raises(ImportExecutionError):
        service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path))


def test_import_skip_focus(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()

    result = service.import_snapshot(
        ImportOptions(
            snapshot_file=EMPTY_CACHE_SNAPSHOT,
            output_dir=tmp_path,
            set_focus=False,
        )
    )

    assert result.db_path.exists()
    assert not (tmp_path / ".pt-snap").exists()
    assert result.focus_state is None


def test_import_output_path_uses_full_filename(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    snapshot_file = tmp_path / "snapshot.pickle"
    snapshot_file.write_bytes(pickle.dumps({}))

    result = service.import_snapshot(ImportOptions(snapshot_file=snapshot_file, output_dir=tmp_path, set_focus=False))

    assert result.db_path.name == "snapshot.pickle.db"


@pytest.mark.parametrize("character", ["?", "#", "%", " "])
def test_import_supports_sqlite_uri_characters_in_filename(character: str, tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    # A literal ? is not a Windows filename. Its legal percent-encoded spelling
    # still tests that SQLite URI handling does not decode a path twice.
    if character == "?" and sys.platform == "win32":
        character = "%3F"
    snapshot_file = tmp_path / f"snapshot{character}.pickle"
    snapshot_file.write_bytes(EMPTY_CACHE_SNAPSHOT.read_bytes())

    result = service.import_snapshot(ImportOptions(snapshot_file=snapshot_file, output_dir=tmp_path, set_focus=False))

    assert result.db_path.name == f"snapshot{character}.pickle.db"
    assert service._metadata_service.inspect(result.db_path).status == "available"


def test_repeated_import_reuses_database_without_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    first = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )

    def fail_if_called(*args: object, **kwargs: object) -> Path:
        raise AssertionError("backend must not run on cache hit")

    monkeypatch.setattr(service._backend, "dump_to_db", fail_if_called)
    second = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )

    assert second.db_path == first.db_path
    assert second.reused is True
    assert second.cache_miss_reason is None
    assert second.metadata == first.metadata


def test_force_rebuilds_compatible_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False))
    original_dump = service._backend.dump_to_db
    calls = 0

    def counting_dump(*args: object, **kwargs: object) -> Path:
        nonlocal calls
        calls += 1
        return original_dump(*args, **kwargs)

    monkeypatch.setattr(service._backend, "dump_to_db", counting_dump)
    result = service.import_snapshot(
        ImportOptions(
            snapshot_file=EMPTY_CACHE_SNAPSHOT,
            output_dir=tmp_path,
            set_focus=False,
            force=True,
        )
    )

    assert calls == 1
    assert result.reused is False
    assert result.cache_miss_reason == "forced"


def test_force_first_import_reports_database_missing(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    result = import_service_cls().import_snapshot(
        ImportOptions(
            snapshot_file=EMPTY_CACHE_SNAPSHOT,
            output_dir=tmp_path,
            set_focus=False,
            force=True,
        )
    )

    assert result.reused is False
    assert result.cache_miss_reason == "database_missing"


def test_malformed_metadata_rebuilds_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sqlite3

    import_service_cls = _import_service_type()
    service = import_service_cls()
    first = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    with closing(sqlite3.connect(first.db_path)) as conn, conn:
        conn.execute("UPDATE pt_snap_metadata SET source_sha256 = 'invalid'")

    original_dump = service._backend.dump_to_db
    calls = 0

    def counting_dump(*args: object, **kwargs: object) -> Path:
        nonlocal calls
        calls += 1
        return original_dump(*args, **kwargs)

    monkeypatch.setattr(service._backend, "dump_to_db", counting_dump)
    result = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )

    assert calls == 1
    assert result.reused is False
    assert result.cache_miss_reason == "metadata_invalid"
    assert service._metadata_service.inspect(result.db_path).status == "available"


def test_legacy_database_rebuilds_once_then_reuses(tmp_path: Path) -> None:
    import sqlite3

    import_service_cls = _import_service_type()
    service = import_service_cls()
    legacy_db = tmp_path / f"{EMPTY_CACHE_SNAPSHOT.name}.db"
    with closing(sqlite3.connect(legacy_db)) as conn, conn:
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE block_0 (id INTEGER PRIMARY KEY)")

    rebuilt = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    reused = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )

    assert rebuilt.reused is False
    assert rebuilt.cache_miss_reason == "metadata_missing"
    assert reused.reused is True


def test_metadata_write_failure_preserves_existing_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from pt_snap_cli.core.common.errors import ImportMetadataError

    import_service_cls = _import_service_type()
    service = import_service_cls()
    first = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    original_metadata = service._metadata_service.inspect(first.db_path).metadata

    def fail_write(*args: object, **kwargs: object) -> None:
        raise ImportMetadataError("metadata write failed")

    monkeypatch.setattr(service._metadata_service, "write", fail_write)
    with pytest.raises(ImportExecutionError, match="metadata write failed"):
        service.import_snapshot(
            ImportOptions(
                snapshot_file=EMPTY_CACHE_SNAPSHOT,
                output_dir=tmp_path,
                set_focus=False,
                force=True,
            )
        )

    assert service._metadata_service.inspect(first.db_path).metadata == original_metadata


def test_initial_hash_failure_preserves_existing_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from pt_snap_cli.core.common.errors import ImportMetadataError

    import_service_cls = _import_service_type()
    service = import_service_cls()
    first = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    original_metadata = service._metadata_service.inspect(first.db_path).metadata
    monkeypatch.setattr(
        service._metadata_service,
        "calculate_sha256",
        lambda path: (_ for _ in ()).throw(ImportMetadataError("hash failed")),
    )

    with pytest.raises(ImportExecutionError, match="hash failed"):
        service.import_snapshot(
            ImportOptions(
                snapshot_file=EMPTY_CACHE_SNAPSHOT,
                output_dir=tmp_path,
                set_focus=False,
                force=True,
            )
        )

    assert service._metadata_service.inspect(first.db_path).metadata == original_metadata


def test_import_format_change_rebuilds_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import pt_snap_cli.core.importing.import_metadata as metadata_module

    import_service_cls = _import_service_type()
    service = import_service_cls()
    service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False))
    monkeypatch.setattr(
        metadata_module,
        "IMPORT_FORMAT_VERSION",
        metadata_module.IMPORT_FORMAT_VERSION + 1,
    )

    result = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )

    assert result.reused is False
    assert result.cache_miss_reason == "import_format_changed"


def test_device_change_rebuilds_database(tmp_path: Path) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    service.import_snapshot(
        ImportOptions(
            snapshot_file=MULTI_DEVICE_SNAPSHOT,
            output_dir=tmp_path,
            device=0,
            set_focus=False,
        )
    )

    result = service.import_snapshot(
        ImportOptions(
            snapshot_file=MULTI_DEVICE_SNAPSHOT,
            output_dir=tmp_path,
            device=1,
            set_focus=False,
        )
    )

    assert result.reused is False
    assert result.cache_miss_reason == "device_changed"
    assert result.metadata.requested_device == 1


def test_source_change_during_import_preserves_existing_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pt_snap_cli.core.common.errors import SourceChangedError

    import_service_cls = _import_service_type()
    service = import_service_cls()
    first = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    original_size = first.db_path.stat().st_size
    hashes = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(service._metadata_service, "calculate_sha256", lambda path: next(hashes))

    with pytest.raises(SourceChangedError, match="source changed"):
        service.import_snapshot(
            ImportOptions(
                snapshot_file=EMPTY_CACHE_SNAPSHOT,
                output_dir=tmp_path,
                set_focus=False,
                force=True,
            )
        )

    assert first.db_path.stat().st_size == original_size
    assert sorted(path.name for path in tmp_path.iterdir()) == [first.db_path.name]


def test_focus_failure_after_publish_restores_existing_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    first = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    original_database = first.db_path.read_bytes()
    focus_file = tmp_path / ".pt-snap" / "focus.json"
    focus_file.parent.mkdir()
    focus_file.write_text('{"db_path": "previous.db"}')
    original_focus = focus_file.read_bytes()

    def fail_focus_write(*args: object, **kwargs: object) -> Path:
        raise OSError("focus write failed")

    from pt_snap_cli.core.analysis.focus_service import FocusService

    focus_service = FocusService()
    monkeypatch.setattr(focus_service._config, "write_project_focus", fail_focus_write)
    service._focus_service = focus_service

    with pytest.raises(ImportExecutionError, match="focus write failed"):
        service.import_snapshot(
            ImportOptions(
                snapshot_file=EMPTY_CACHE_SNAPSHOT,
                output_dir=tmp_path,
                force=True,
            )
        )

    assert first.db_path.read_bytes() == original_database
    assert focus_file.read_bytes() == original_focus
    assert sorted(path.name for path in tmp_path.iterdir()) == [".pt-snap", first.db_path.name]


def test_focus_failure_after_first_publish_removes_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pt_snap_cli.core.analysis.focus_service import FocusService

    import_service_cls = _import_service_type()
    focus_service = FocusService()
    monkeypatch.setattr(
        focus_service._config,
        "write_project_focus",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("focus write failed")),
    )
    service = import_service_cls(focus_service=focus_service)
    destination = tmp_path / f"{EMPTY_CACHE_SNAPSHOT.name}.db"

    with pytest.raises(ImportExecutionError, match="focus write failed"):
        service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path))

    assert not destination.exists()
    assert not (tmp_path / ".pt-snap" / "focus.json").exists()


def test_focus_transaction_falls_back_when_hard_links_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import_service_cls = _import_service_type()
    service = import_service_cls()
    service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False))
    monkeypatch.setattr(
        "pt_snap_cli.core.importing.snapshot_import_backend.os.link",
        lambda *args: (_ for _ in ()).throw(OSError("hard links unavailable")),
    )

    result = service.import_snapshot(ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, force=True))

    assert result.db_path.exists()
    assert result.focus_state is not None
    assert not list(tmp_path.glob("*.rollback"))


def test_invalid_focus_device_is_normalized_as_import_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from pt_snap_cli.core.analysis.focus_service import FocusService

    focus_service = FocusService()
    monkeypatch.setattr(
        focus_service,
        "set_project_focus",
        lambda *args, **kwargs: (_ for _ in ()).throw(InvalidDeviceError("Device 99 not found")),
    )
    service = _import_service_type()(focus_service=focus_service)
    options = ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, device=99)

    with pytest.raises(ImportExecutionError, match="Device 99 not found"):
        service._set_focus_if_requested(tmp_path / "snapshot.db", options)


def test_rollback_backup_writes_through_secure_mkstemp_fd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Backup uses the secure mkstemp fd so a symlink race cannot redirect the write."""
    import os
    import tempfile

    import pt_snap_cli.core.importing.snapshot_import_backend as backend_module

    import_service_cls = _import_service_type()
    service = import_service_cls()
    first = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    original_database = first.db_path.read_bytes()

    victim = tmp_path / "victim.txt"
    victim.write_text("safe")

    real_mkstemp = tempfile.mkstemp
    attempts = []

    def racing_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        if kwargs.get("suffix") != ".rollback":
            return fd, name
        # Target the rollback backup, not unrelated snapshot staging files.
        # Windows denies unlinking its open fd, preventing this race outright.
        try:
            try:
                os.unlink(name)
            except PermissionError:
                if os.name != "nt":
                    raise
                attempts.append("blocked-open-file")
            else:
                os.symlink(victim, name)
                attempts.append("redirected-path")
            return fd, name
        except BaseException:
            os.close(fd)  # The failing fixture never transferred ownership.
            raise

    monkeypatch.setattr(backend_module.tempfile, "mkstemp", racing_mkstemp)

    def fail_focus_write(*args, **kwargs):
        raise OSError("focus write failed")

    from pt_snap_cli.core.analysis.focus_service import FocusService

    focus_service = FocusService()
    monkeypatch.setattr(focus_service._config, "write_project_focus", fail_focus_write)
    service._focus_service = focus_service

    with pytest.raises(ImportExecutionError, match="focus write failed"):
        service.import_snapshot(
            ImportOptions(
                snapshot_file=EMPTY_CACHE_SNAPSHOT,
                output_dir=tmp_path,
                force=True,
            )
        )

    assert attempts == ["blocked-open-file" if os.name == "nt" else "redirected-path"]
    # Victim must remain untouched; the secure fd prevented a symlink redirect.
    assert victim.read_text() == "safe"
    # The destination database must be restored from the safe rollback copy.
    assert first.db_path.read_bytes() == original_database


def test_set_focus_no_args_returns_current_focus_without_revalidation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """set_focus() with no arguments is a no-op that returns the current focus."""
    import_service_cls = _import_service_type()
    service = import_service_cls()
    first = service.import_snapshot(
        ImportOptions(snapshot_file=EMPTY_CACHE_SNAPSHOT, output_dir=tmp_path, set_focus=False)
    )
    analyzer = SnapshotAnalyzer(db_path=str(first.db_path))

    # Removing the database after construction must not cause set_focus() to fail.
    first.db_path.unlink()

    state = analyzer.set_focus()
    assert state.db_path == str(first.db_path)
