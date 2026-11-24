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

"""Collection and exit-code contracts without requiring a downloaded browser."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BROWSER_TEST = ROOT / "test/test_memory_tree_browser.py"


def _browser_nodes():
    return {
        node.name
        for node in ast.parse(BROWSER_TEST.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def _run_unavailable(tmp_path, mode, *, required=False, collect_only=False, extra_args=()):
    # Copy the actual regression module, not a stand-in with fewer tests. No
    # fixture bytes, browser downloads, or production behavior are exercised.
    (tmp_path / "test_browser_copy.py").write_text(BROWSER_TEST.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers = browser: browser regression\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        """
import importlib
import importlib.abc
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest_plugins = ("test._browser_support",)

original = importlib.import_module

def pytest_configure(config):
    binary = Path(__file__).parent / "fake-chromium"
    if MODE == "broken_browser":
        binary.touch()
    class BrowserError(Exception):
        pass
    def launch(**kwargs):
        raise BrowserError("synthetic browser launch failure")
    runtime = SimpleNamespace(chromium=SimpleNamespace(executable_path=str(binary), launch=launch))
    api = SimpleNamespace(sync_playwright=lambda: nullcontext(runtime), Error=BrowserError)
    def load(name, *args, **kwargs):
        if name != "playwright.sync_api":
            return original(name, *args, **kwargs)
        if MODE in {"missing_package", "broken_package"}:
            dependency = "playwright" if MODE == "missing_package" else "greenlet"
            raise ModuleNotFoundError("No module named " + dependency, name=dependency)
        return api
    importlib.import_module = load
    if MODE == "missing_package":
        class MissingPlaywright(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "playwright" or fullname.startswith("playwright."):
                    raise ModuleNotFoundError("No module named playwright", name="playwright")
        sys.meta_path.insert(0, MissingPlaywright())

def pytest_unconfigure(config):
    importlib.import_module = original
""".replace("MODE", repr(mode)),
        encoding="utf-8",
    )
    env = os.environ.copy()
    for key in (
        "PT_SNAP_REQUIRE_BROWSER",
        "PT_SNAP_TEST_CHROMIUM",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
    ):
        env.pop(key, None)
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if required:
        env["PT_SNAP_REQUIRE_BROWSER"] = "1"
    args = [sys.executable, "-m", "pytest", "test_browser_copy.py", "-v", "-rs", "--tb=short"]
    args.extend(extra_args)
    if collect_only:
        args.append("--collect-only")
    return subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_browser_collection_keeps_every_real_regression_without_playwright(tmp_path, required):
    result = _run_unavailable(tmp_path, "missing_package", required=required, collect_only=True)
    nodes = _browser_nodes()
    assert len(nodes) >= 12, "Existing browser regressions must not disappear"
    assert result.returncode == 0, result.stdout + result.stderr
    for node in nodes:
        assert node in result.stdout
    assert f"collected={len(nodes)} passed=0 skipped=0 failed=0 not_run={len(nodes)}" in result.stdout


@pytest.mark.parametrize("mode", ["missing_package", "missing_binary"])
@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_missing_browser_dependencies_are_visible_and_required_mode_fails(tmp_path, mode, required):
    result = _run_unavailable(tmp_path, mode, required=required)
    count = len(_browser_nodes())
    assert result.returncode == (1 if required else 0), result.stdout + result.stderr
    for node in _browser_nodes():
        assert node in result.stdout
    if required:
        assert f"collected={count} passed=0 skipped=0 failed={count} not_run=0" in result.stdout
    else:
        assert f"collected={count} passed=0 skipped={count} failed=0 not_run=0" in result.stdout
    assert "Browser regressions NOT EXECUTED" in result.stdout
    assert (
        "Playwright is not installed" if mode == "missing_package" else "Chromium executable is missing"
    ) in result.stdout


@pytest.mark.parametrize("mode", ["broken_package", "broken_browser"])
def test_broken_browser_installations_never_become_optional_skips(tmp_path, mode):
    result = _run_unavailable(tmp_path, mode)
    count = len(_browser_nodes())
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"collected={count} passed=0 skipped=0 failed={count} not_run=0" in result.stdout
    assert ("greenlet" if mode == "broken_package" else "synthetic browser launch failure") in result.stdout


def test_required_mode_rejects_deselected_browser_execution(tmp_path):
    result = _run_unavailable(
        tmp_path,
        "missing_package",
        required=True,
        extra_args=("-k", "nothing_matches_this_selector"),
    )
    count = len(_browser_nodes())
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"collected={count} passed=0 skipped=0 failed=0 not_run={count}" in result.stdout


def test_required_summary_fails_for_skips_and_incomplete_execution(monkeypatch):
    from types import SimpleNamespace

    from test._browser_support import BrowserSummary

    monkeypatch.setenv("PT_SNAP_REQUIRE_BROWSER", "1")
    for nodes, outcomes in ((set(), {}), ({"one"}, {}), ({"one"}, {"one": "skipped"})):
        summary = BrowserSummary()
        summary.nodes = nodes
        summary.outcomes = outcomes
        session = SimpleNamespace(
            config=SimpleNamespace(option=SimpleNamespace(collectonly=False)),
            exitstatus=pytest.ExitCode.OK,
        )
        summary.pytest_sessionfinish(session)
        assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
