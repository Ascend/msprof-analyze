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

"""Optional-browser fixtures and visible per-test execution accounting.

Import Playwright only during fixture setup: absent optional dependencies must
never remove browser regression identities from pytest's collection.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


def _unavailable(reason):
    message = f"Browser regressions NOT EXECUTED: {reason}"
    if os.environ.get("PT_SNAP_REQUIRE_BROWSER") == "1":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@pytest.fixture(scope="session")
def playwright_api():
    try:
        return importlib.import_module("playwright.sync_api")
    except ModuleNotFoundError as exc:
        # A broken installation (for example missing greenlet) is not optional.
        if exc.name not in {"playwright", "playwright.sync_api"}:
            raise
        _unavailable("Playwright is not installed; install the .[dev] extra")


@pytest.fixture(scope="module")
def chromium_browser(playwright_api):
    with playwright_api.sync_playwright() as runtime:
        executable = os.environ.get("PT_SNAP_TEST_CHROMIUM")
        binary = executable or runtime.chromium.executable_path
        if not Path(binary).is_file():
            _unavailable(
                "Chromium executable is missing; run python -m playwright install chromium "
                "or set PT_SNAP_TEST_CHROMIUM to an existing executable"
            )
        options = {"headless": True}
        if executable:
            options["executable_path"] = executable
        try:
            browser = runtime.chromium.launch(**options)
        except playwright_api.Error as exc:
            # Only the explicit preflight above can skip. Crashes, permission
            # errors, bad shared libraries and other launch failures always fail.
            pytest.fail(f"Cannot launch Chromium for frame navigation tests: {exc}")
        try:
            yield browser
        finally:
            browser.close()


def browser_expect(locator):
    """Assertions run only after browser setup has succeeded."""
    return importlib.import_module("playwright.sync_api").expect(locator)


class BrowserSummary:
    def __init__(self):
        self.nodes = set()
        self.outcomes = {}
        self.skip_reasons = set()

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(self, items):
        self.nodes = {item.nodeid for item in items if item.get_closest_marker("browser")}
        yield

    def pytest_runtest_logreport(self, report):
        if report.nodeid not in self.nodes:
            return
        if report.failed:
            self.outcomes[report.nodeid] = "failed"
        elif self.outcomes.get(report.nodeid) != "failed":
            if report.skipped:
                self.outcomes[report.nodeid] = "skipped"
                reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else report.longrepr
                self.skip_reasons.add(str(reason))
            elif report.when == "call":
                self.outcomes[report.nodeid] = "passed"

    def pytest_sessionfinish(self, session):
        if os.environ.get("PT_SNAP_REQUIRE_BROWSER") != "1" or session.config.option.collectonly:
            return
        incomplete = not self.nodes or len(self.outcomes) < len(self.nodes)
        if (incomplete or "skipped" in self.outcomes.values()) and session.exitstatus in {
            pytest.ExitCode.OK,
            pytest.ExitCode.NO_TESTS_COLLECTED,
        }:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter):
        if not self.nodes and os.environ.get("PT_SNAP_REQUIRE_BROWSER") != "1":
            return
        counts = {outcome: list(self.outcomes.values()).count(outcome) for outcome in ("passed", "skipped", "failed")}
        mode = "required" if os.environ.get("PT_SNAP_REQUIRE_BROWSER") == "1" else "optional"
        terminalreporter.section(f"Browser regression execution ({mode})")
        terminalreporter.write_line(
            f"collected={len(self.nodes)} passed={counts['passed']} skipped={counts['skipped']} "
            f"failed={counts['failed']} not_run={len(self.nodes) - len(self.outcomes)}"
        )
        if not self.nodes or len(self.outcomes) < len(self.nodes):
            terminalreporter.write_line(
                "Browser regressions NOT EXECUTED: collection/deselection or early termination is not browser execution."
            )
        if counts["skipped"]:
            terminalreporter.write_line(
                "Browser regressions NOT EXECUTED for skipped cases; this is not a browser pass."
            )
            for reason in sorted(self.skip_reasons):
                terminalreporter.write_line(reason)


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: real Chromium interaction regressions (required in Linux browser CI)")
    config.pluginmanager.register(BrowserSummary(), "browser-execution-summary")
