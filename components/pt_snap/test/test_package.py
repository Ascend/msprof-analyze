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

"""Tests for package initialization and published metadata."""

from __future__ import annotations

from collections.abc import Iterable
from importlib.machinery import PathFinder
from importlib.metadata import distribution, requires, version
from pathlib import Path, PurePosixPath

import pytest

import pt_snap_cli
from pt_snap_cli import __version__

ROOT = Path(__file__).resolve().parents[1]
REMOVED_PACKAGES = ("mcp", "vendor")


def _assert_removed_package(package_root: Path, name: str) -> None:
    """Allow empty namespace/cache residue, not restored code or package assets.

    Inspect without importing the removed module: a broken or side-effectful
    resurrected module must fail this guard without executing its contents.
    Legacy adjacent .pyc files remain importable and must not be ignored.
    """
    removed_root = package_root / name
    candidates = list(removed_root.rglob("*")) + list(package_root.glob(f"{name}.*"))
    if removed_root.is_file():
        candidates.append(removed_root)
    remaining = [
        path.relative_to(package_root).as_posix()
        for path in candidates
        if path.is_file()
        and not (path.parent.name == "__pycache__" and path.suffix in {".pyc", ".pyo"} and "." in path.stem)
    ]
    assert not remaining, f"Removed package content remains: {sorted(remaining)}"

    PathFinder.invalidate_caches()
    spec = PathFinder.find_spec(f"pt_snap_cli.{name}", [str(package_root)])
    assert spec is None or spec.loader is None, f"Removed package is importable: {spec}"


def _removed_distribution_entries(files: Iterable[str]) -> list[str]:
    """A shipped removed package is a regression, even if it contains only cache."""
    removed = []
    for file in files:
        parts = PurePosixPath(file).parts
        if len(parts) >= 2 and parts[0] == "pt_snap_cli":
            if any(parts[1] == name or parts[1].startswith(f"{name}.") for name in REMOVED_PACKAGES):
                removed.append(file)
    return sorted(removed)


def _runtime_requirement_names() -> set[str]:
    names: set[str] = set()
    for req in requires("msprof-analyze") or []:
        name_part, _, marker = req.partition(";")
        if "extra" in marker:
            continue
        name = name_part.split("[", 1)[0]
        for sep in (">", "<", "=", "!"):
            name = name.split(sep, 1)[0]
        names.add(name.strip().lower())
    return names


class TestPackage:
    """Test package initialization."""

    def test_version(self) -> None:
        """Test version is defined."""
        assert __version__ == version("msprof-analyze")

    def test_version_format(self) -> None:
        """Test version string is not the fallback value."""
        assert __version__ != "0.0.0-dev"

    def test_console_scripts_are_cli_only(self) -> None:
        names = {ep.name for ep in distribution("msprof-analyze").entry_points if ep.group == "console_scripts"}
        assert names == {"msprof-analyze", "pt-snap"}

    def test_runtime_dependencies_exclude_mcp_stack(self) -> None:
        names = _runtime_requirement_names()
        assert names.isdisjoint({"mcp", "starlette", "uvicorn"})

    @pytest.mark.parametrize("name", REMOVED_PACKAGES)
    def test_removed_packages_have_no_code_or_assets(self, name: str) -> None:
        # Check both the selected import location and this checkout. An editable
        # install's RECORD does not enumerate the source tree.
        package_roots = {Path(path).resolve() for path in pt_snap_cli.__path__}
        package_roots.add(ROOT / "src" / "pt_snap_cli")
        for package_root in package_roots:
            _assert_removed_package(package_root, name)

    def test_distribution_does_not_ship_removed_packages(self) -> None:
        files = distribution("msprof-analyze").files
        assert files is not None, "Installed distribution must have a file manifest"
        assert not _removed_distribution_entries(str(file) for file in files)


@pytest.mark.parametrize("name", REMOVED_PACKAGES)
@pytest.mark.parametrize("layout", ["absent", "empty", "pycache-only"])
def test_removed_package_guard_accepts_clean_and_cache_only_trees(tmp_path, name, layout):
    package_root = tmp_path / "pt_snap_cli"
    package_root.mkdir()
    removed_root = package_root / name
    if layout != "absent":
        removed_root.mkdir()
    if layout == "pycache-only":
        # The nested name is deliberately arbitrary: removal covers every child
        # of these namespaces, not a blacklist of historical vendor identities.
        for relative in (
            "__pycache__/__init__.cpython-313.pyc",
            "retired_package/__pycache__/reader.cpython-313.pyc",
            "retired_package/__pycache__/reader.cpython-310.opt-1.pyc",
        ):
            cache = removed_root / relative
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b"stale cache must not be imported or deleted")

    before = {path: path.read_bytes() for path in package_root.rglob("*") if path.is_file()}
    spec = PathFinder.find_spec(f"pt_snap_cli.{name}", [str(package_root)])
    if layout == "absent":
        assert spec is None
    else:
        assert spec is not None and spec.loader is None
        assert spec.submodule_search_locations is not None
    _assert_removed_package(package_root, name)
    assert {path: path.read_bytes() for path in package_root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("name", REMOVED_PACKAGES)
@pytest.mark.parametrize(
    "relative",
    [
        "__init__.py",
        "server.py",
        "retired_package/reader.py",
        "__init__.pyc",
        "retired_package/schema.json",
        "__pycache__/hidden.py",
        "__pycache__/importable.pyc",
    ],
)
def test_removed_package_guard_rejects_restored_code_and_assets(tmp_path, name, relative):
    package_root = tmp_path / "pt_snap_cli"
    restored = package_root / name / relative
    restored.parent.mkdir(parents=True)
    payload = b"raise RuntimeError('must never execute removed package code')\n"
    restored.write_bytes(payload)

    with pytest.raises(AssertionError, match="Removed package content remains"):
        _assert_removed_package(package_root, name)
    assert restored.read_bytes() == payload


@pytest.mark.parametrize("name", REMOVED_PACKAGES)
@pytest.mark.parametrize("suffix", [".py", ".pyc", ".so", ".pyd"])
def test_removed_package_guard_rejects_flat_module_replacements(tmp_path, name, suffix):
    restored = tmp_path / f"{name}{suffix}"
    restored.write_bytes(b"removed module")
    with pytest.raises(AssertionError, match="Removed package content remains"):
        _assert_removed_package(tmp_path, name)


@pytest.mark.parametrize("name", REMOVED_PACKAGES)
@pytest.mark.parametrize(
    "entry",
    [
        "{name}/__init__.py",
        "{name}/retired_package/reader.py",
        "{name}.py",
        "{name}/__pycache__/old.pyc",
    ],
)
def test_distribution_guard_rejects_rediscovered_removed_content(name, entry):
    path = "pt_snap_cli/" + entry.format(name=name)
    assert _removed_distribution_entries(["pt_snap_cli/cli.py", path]) == [path]


def test_distribution_guard_allows_unrelated_modules_and_metadata():
    assert (
        _removed_distribution_entries(
            [
                "pt_snap_cli/cli.py",
                "pt_snap_cli/mcp_tools.py",
                "pt_snap_cli/vendor_tools/reader.py",
                "pt_snap_cli-1.0.dist-info/METADATA",
                "pt_snap_cli-1.0.dist-info/licenses/LICENSE",
            ]
        )
        == []
    )
