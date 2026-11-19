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

"""Tests for configuration management."""

import json
import os
from pathlib import Path

import pytest

from pt_snap_cli.config import (
    DB_PATH_KEY,
    DEVICE_ID_KEY,
    ENV_DB_PATH,
    Config,
    FocusResolutionError,
)


class TestConfig:
    """Test configuration management."""

    def test_config_init_empty(self, tmp_path: Path) -> None:
        """Test config initialization with no config file."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()
            assert not config.config_file.exists()
            assert config.current_db_path is None
            assert config.current_device_id is None
            assert config.show() == {}
        finally:
            Path.home = original_home

    def test_config_set_db_path(self, tmp_path: Path) -> None:
        """Test setting database path."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()
            db_path = tmp_path / "test.db"
            db_path.touch()

            config.current_db_path = db_path

            assert config.config_file.exists()
            assert config.current_db_path == db_path.resolve()

            # Verify persisted to file
            config_data = json.loads(config.config_file.read_text())
            assert config_data[DB_PATH_KEY] == str(db_path.resolve())
        finally:
            Path.home = original_home

    def test_config_clear_db_path(self, tmp_path: Path) -> None:
        """Test clearing database path."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()
            db_path = tmp_path / "test.db"
            db_path.touch()

            config.current_db_path = db_path
            config.clear_current_db_path()

            assert config.current_db_path is None
            config_data = json.loads(config.config_file.read_text())
            assert DB_PATH_KEY not in config_data
        finally:
            Path.home = original_home

    def test_config_set_device_id(self, tmp_path: Path) -> None:
        """Test setting device ID in global config."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()
            config.current_device_id = 2

            assert config.current_device_id == 2

            # Verify persisted
            config2 = Config()
            assert config2.current_device_id == 2

            config_data = json.loads(config.config_file.read_text())
            assert config_data[DEVICE_ID_KEY] == 2
        finally:
            Path.home = original_home

    def test_config_clear_device_id(self, tmp_path: Path) -> None:
        """Test clearing device ID from global config."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()
            config.current_device_id = 1
            config.current_device_id = None

            assert config.current_device_id is None
            config_data = json.loads(config.config_file.read_text())
            assert DEVICE_ID_KEY not in config_data
        finally:
            Path.home = original_home

    def test_config_get_set(self, tmp_path: Path) -> None:
        """Test generic get/set methods."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()

            config.set("test_key", "test_value")
            assert config.get("test_key") == "test_value"
            assert config.get("nonexistent", "default") == "default"
        finally:
            Path.home = original_home

    def test_config_clear_all(self, tmp_path: Path) -> None:
        """Test clearing all configuration."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()
            config.set("key1", "value1")
            config.set("key2", "value2")

            config.clear()

            assert config.show() == {}
            assert config.current_db_path is None
            assert config.current_device_id is None
        finally:
            Path.home = original_home

    def test_config_validate_db_path_exists(self, tmp_path: Path) -> None:
        """Test validate_db_path when file exists."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()
            db_path = tmp_path / "test.db"
            db_path.touch()
            config.current_db_path = db_path

            assert config.validate_db_path() is True
            assert config.current_db_path is not None
        finally:
            Path.home = original_home

    def test_config_validate_db_path_not_exists(self, tmp_path: Path) -> None:
        """Test validate_db_path when file doesn't exist."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config = Config()
            db_path = tmp_path / "test.db"
            config.current_db_path = db_path

            assert config.validate_db_path() is False
            assert config.current_db_path is None
        finally:
            Path.home = original_home

    def test_config_load_from_file(self, tmp_path: Path) -> None:
        """Test loading config from existing file."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config_dir = tmp_path / ".config" / "pt-snap-cli"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "config.json"

            db_path = tmp_path / "existing.db"
            db_path.touch()
            config_file.write_text(json.dumps({DB_PATH_KEY: str(db_path), "other_key": "other_value"}))

            config = Config()
            assert config.current_db_path == db_path.resolve()
            assert config.get("other_key") == "other_value"
        finally:
            Path.home = original_home

    def test_config_load_invalid_json(self, tmp_path: Path) -> None:
        """Test loading config from invalid JSON file."""
        original_home = Path.home
        Path.home = lambda: tmp_path
        try:
            config_dir = tmp_path / ".config" / "pt-snap-cli"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "config.json"
            config_file.write_text("invalid json {")

            config = Config()
            assert config.show() == {}
        finally:
            Path.home = original_home


class TestDbFocusResolver:
    """Test database focus resolution."""

    @pytest.fixture(autouse=True)
    def mock_home_and_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Keep resolver tests isolated from the real user environment."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv(ENV_DB_PATH, raising=False)

    def test_write_and_resolve_project_focus(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test writing and resolving project focus."""
        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / "test.db"
        db_path.touch()
        config = Config()

        focus_file = config.write_project_focus(db_path)
        resolved = config.resolve_focus()

        assert focus_file == tmp_path / ".pt-snap" / "focus.json"
        assert resolved.db_path == db_path.resolve()
        assert resolved.source == "project"
        assert resolved.focus_file == focus_file
        assert resolved.device_id is None

    def test_write_and_resolve_with_device_id(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test writing and resolving focus with device_id."""
        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / "test.db"
        db_path.touch()
        config = Config()

        focus_file = config.write_project_focus(db_path, device_id=1)
        resolved = config.resolve_focus()

        assert focus_file == tmp_path / ".pt-snap" / "focus.json"
        assert resolved.db_path == db_path.resolve()
        assert resolved.device_id == 1
        assert resolved.source == "project"

    def test_resolve_project_focus_from_child_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test resolving project focus by walking up parent directories."""
        project = tmp_path / "project"
        child = project / "nested" / "child"
        child.mkdir(parents=True)
        db_path = tmp_path / "test.db"
        db_path.touch()
        config = Config()
        config.write_project_focus(db_path, base_dir=project)
        monkeypatch.chdir(child)

        resolved = config.resolve_focus()

        assert resolved.db_path == db_path.resolve()
        assert resolved.source == "project"

    def test_resolve_priority_explicit_env_project_global(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test database focus priority order."""
        monkeypatch.chdir(tmp_path)
        explicit_db = tmp_path / "explicit.db"
        env_db = tmp_path / "env.db"
        project_db = tmp_path / "project.db"
        global_db = tmp_path / "global.db"
        for db_path in (explicit_db, env_db, project_db, global_db):
            db_path.touch()

        config = Config()
        config.current_db_path = global_db
        config.write_project_focus(project_db)
        monkeypatch.setenv(ENV_DB_PATH, str(env_db))

        explicit = config.resolve_focus(explicit_db)
        env = config.resolve_focus()
        monkeypatch.delenv(ENV_DB_PATH)
        project = config.resolve_focus()
        (tmp_path / ".pt-snap" / "focus.json").unlink()
        global_focus = config.resolve_focus()

        assert explicit.db_path == explicit_db
        assert explicit.source == "explicit"
        assert env.db_path == env_db
        assert env.source == "env"
        assert project.db_path == project_db.resolve()
        assert project.source == "project"
        assert global_focus.db_path == global_db.resolve()
        assert global_focus.source == "global"

    def test_project_focus_is_cwd_scoped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test different working directories can use different focuses."""
        project_a = tmp_path / "project-a"
        project_b = tmp_path / "project-b"
        project_a.mkdir()
        project_b.mkdir()
        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        db_a.touch()
        db_b.touch()
        config = Config()
        config.write_project_focus(db_a, base_dir=project_a)
        config.write_project_focus(db_b, base_dir=project_b)

        monkeypatch.chdir(project_a)
        resolved_a = config.resolve_focus()
        monkeypatch.chdir(project_b)
        resolved_b = config.resolve_focus()

        assert resolved_a.db_path == db_a.resolve()
        assert resolved_b.db_path == db_b.resolve()

    def test_invalid_project_focus_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test invalid project focus JSON fails clearly."""
        monkeypatch.chdir(tmp_path)
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text("not-json")

        with pytest.raises(FocusResolutionError, match="Invalid project focus file"):
            Config().resolve_focus()

    def test_project_focus_missing_db_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test project focus without db_path fails clearly."""
        monkeypatch.chdir(tmp_path)
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        (focus_dir / "focus.json").write_text(json.dumps({"other": "value"}))

        with pytest.raises(FocusResolutionError, match="db_path"):
            Config().resolve_focus()

    def test_backward_compat_old_current_db_path_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that old 'current_db_path' key is still readable."""
        monkeypatch.chdir(tmp_path)
        focus_dir = tmp_path / ".pt-snap"
        focus_dir.mkdir()
        old_db = tmp_path / "old.db"
        old_db.touch()
        (focus_dir / "focus.json").write_text(json.dumps({"current_db_path": str(old_db)}))

        resolved = Config().resolve_focus()
        assert resolved.db_path == old_db.resolve()
        assert resolved.source == "project"

    def test_global_device_id_in_resolve(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test global device_id is included in resolved focus."""
        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / "test.db"
        db_path.touch()
        config = Config()
        config.current_db_path = db_path
        config.current_device_id = 3

        resolved = config.resolve_focus()
        assert resolved.db_path == db_path.resolve()
        assert resolved.device_id == 3
        assert resolved.source == "global"

    def test_explicit_device_id_with_explicit_db(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test passing explicit device_id along with explicit db_path."""
        monkeypatch.chdir(tmp_path)
        db_path = tmp_path / "test.db"
        db_path.touch()

        resolved = Config().resolve_focus(db_path, explicit_device_id=2)
        assert resolved.db_path == db_path
        assert resolved.device_id == 2
        assert resolved.source == "explicit"

    def test_failed_project_focus_replace_preserves_existing_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = Config()
        first_db = tmp_path / "first.db"
        second_db = tmp_path / "second.db"
        focus_file = config.write_project_focus(first_db, base_dir=tmp_path, device_id=1)
        original = focus_file.read_bytes()

        monkeypatch.setattr(os, "replace", lambda *args: (_ for _ in ()).throw(OSError("full")))

        with pytest.raises(OSError, match="full"):
            config.write_project_focus(second_db, base_dir=tmp_path, device_id=2)

        assert focus_file.read_bytes() == original
        assert list(focus_file.parent.glob(".focus.json.*.tmp")) == []

    def test_failed_global_config_replace_preserves_file_and_memory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = Config()
        config.set("status", "before")
        original = config.config_file.read_bytes()

        monkeypatch.setattr(os, "replace", lambda *args: (_ for _ in ()).throw(OSError("full")))

        with pytest.raises(OSError, match="full"):
            config.set("status", "after")

        assert config.show() == {"status": "before"}
        assert config.config_file.read_bytes() == original
        assert list(config.config_dir.glob(".config.json.*.tmp")) == []

    def test_atomic_project_focus_write_preserves_existing_mode(self, tmp_path: Path) -> None:
        config = Config()
        focus_file = config.write_project_focus(tmp_path / "first.db", base_dir=tmp_path)
        focus_file.chmod(0o640)
        # Windows chmod preserves only the read-only flag, not POSIX group bits.
        expected_mode = focus_file.stat().st_mode & 0o777

        config.write_project_focus(tmp_path / "second.db", base_dir=tmp_path)

        assert focus_file.stat().st_mode & 0o777 == expected_mode

    def test_atomic_write_new_file_uses_private_mode(self, monkeypatch, tmp_path: Path) -> None:
        config = Config()
        config_path = config.write_project_focus(tmp_path / "first.db", base_dir=tmp_path)
        config_path.unlink()

        monkeypatch.setattr(os, "umask", lambda mode: (_ for _ in ()).throw(AssertionError("umask touched")))

        config.write_project_focus(tmp_path / "second.db", base_dir=tmp_path)

        if os.name == "nt":
            # chmod(0o600) is a writable file on Windows; ACL privacy is not a
            # POSIX mode-bit contract. Keep the atomic-write assertion active.
            assert config_path.stat().st_mode & 0o200
        else:
            assert config_path.stat().st_mode & 0o777 == 0o600
        assert json.loads(config_path.read_text())[DB_PATH_KEY] == str((tmp_path / "second.db").resolve())
