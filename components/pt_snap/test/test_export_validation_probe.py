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

"""RSS instrumentation must not count an earlier producer's pre-exec peak."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROBE = Path(__file__).resolve().parents[1] / "benchmarks/export_validation_memory.py"


@pytest.fixture
def probe():
    spec = importlib.util.spec_from_file_location("export_validation_probe", PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_current_address_space_rss_normalizes_kib(probe):
    assert probe._parse_linux_rss("Name:\tpython\nVmHWM:\t24000 kB\nVmRSS:\t20000 kB\n") == {
        "VmHWM": 24_000 * 1024,
        "VmRSS": 20_000 * 1024,
    }


@pytest.mark.parametrize(
    "status",
    [
        "VmRSS: 1 kB",
        "VmHWM: 1 kB",
        "VmHWM: 1 MB\nVmRSS: 1 kB",
        "VmHWM: -1 kB\nVmRSS: 1 kB",
        "VmHWM: 1 kB\nVmHWM: 2 kB\nVmRSS: 1 kB",
    ],
)
def test_missing_or_unsupported_rss_capability_fails_explicitly(probe, status):
    with pytest.raises(RuntimeError, match="RSS|/proc"):
        probe._parse_linux_rss(status)


def test_rss_probe_reports_unsupported_platform_without_silent_skip(probe, monkeypatch):
    monkeypatch.setattr(probe.sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="requires Linux /proc"):
        probe._linux_rss_snapshot()


def test_inherited_ru_maxrss_does_not_fail_current_process_memory_bound(probe, tmp_path, monkeypatch):
    mib = 1024 * 1024
    (tmp_path / "probe.json").write_text(json.dumps({"events": 1_000_000, "capacity": 500_000, "slices": []}))
    monkeypatch.setitem(
        sys.modules,
        "resource",
        SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda _: SimpleNamespace(ru_maxrss=1024 * 1024)),
    )
    snapshots = iter(
        [
            {"VmRSS": 20 * mib, "VmHWM": 22 * mib},
            {"VmRSS": 21 * mib, "VmHWM": 25 * mib},
        ]
    )
    monkeypatch.setattr(probe, "_linux_rss_snapshot", lambda: next(snapshots))
    calls = []
    monkeypatch.setattr(probe, "_validate_shards", calls.append)
    evidence = probe.measure(tmp_path, "rss")
    assert len(calls) == 1
    assert evidence["rss_current_before_bytes"] == 20 * mib
    assert evidence["rss_current_after_bytes"] == 21 * mib
    assert evidence["rss_high_water_before_bytes"] == 22 * mib
    assert evidence["rss_high_water_after_bytes"] == 25 * mib < 128 * mib
    assert evidence["rss_high_water_increase_bytes"] == 3 * mib < 32 * mib
    assert evidence["ru_maxrss_before_bytes"] == evidence["ru_maxrss_after_bytes"] == 1024 * mib
    assert evidence["tracemalloc_enabled"] is False
