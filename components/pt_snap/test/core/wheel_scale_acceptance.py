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

"""Clean-wheel subprocess harness and an original, inspectable scale workload.

Only the fixture generator runs in the checkout. Product imports in probes,
queries, and reports run with the installed venv interpreter and isolated CWD.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import subprocess
import time
import venv
from pathlib import Path

PROBE = """
import importlib.metadata as metadata
import json, platform, site, sqlite3, sys
from dataclasses import asdict
from pathlib import Path
import pt_snap_cli, typer, yaml, jinja2
from pt_snap_cli.core.common.query_limits import QueryLimits
print(json.dumps({
    "python": sys.version, "executable": sys.executable,
    "prefix": sys.prefix, "base_prefix": sys.base_prefix,
    "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
    "user_site_enabled": site.ENABLE_USER_SITE, "sys_path": sys.path,
    "modules": {m.__name__: str(Path(m.__file__).resolve())
                for m in (pt_snap_cli, typer, yaml, jinja2)},
    "versions": {name: metadata.version(name)
                 for name in ("msprof-analyze", "typer", "pyyaml", "jinja2")},
    "entry_point": next(e.value for e in metadata.distribution("msprof-analyze").entry_points
                        if e.group == "console_scripts" and e.name == "msprof-analyze"),
    "query_limits": asdict(QueryLimits.resolve()),
}))
"""

API_QUERIES = """
import json, sys
from dataclasses import asdict
from pt_snap_cli.api import SnapshotAnalyzer
from pt_snap_cli.core.common.error_codes import classify_error
from pt_snap_cli.core.analysis.report_service import ReportService
root, cases_file, event = sys.argv[1], sys.argv[2], int(sys.argv[3])
results, errors = {}, {}
with SnapshotAnalyzer(root) as analyzer:
    catalog = analyzer.list_capabilities()
    with open(cases_file) as stream:
        cases = json.load(stream)
    for case in cases:
        try:
            results[case["name"]] = analyzer.execute_query(
                case["template"], case["params"], exact_total=True)
        except Exception as exc:
            errors[case["name"]] = {"type": type(exc).__name__,
                "code": classify_error(exc)[0], "message": str(exc)}
service = ReportService()
try:
    peak = asdict(service.peak_memory_report(root, limit=-1))
    try:
        tree = {"event_id": event, **asdict(service.memory_tree_report(event, root))}
    except Exception as exc:
        tree = {"type": type(exc).__name__, "code": classify_error(exc)[0],
                "message": str(exc)}
finally:
    service.close()
print(json.dumps({"catalog": catalog, "queries": results, "errors": errors,
                  "peak_report": peak, "tree_report": tree}))
"""


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WheelRuntime:
    """True installed console entry point, with failure-safe command evidence."""

    def __init__(self, root, wheel, evidence_dir, wheelhouse=None):
        self.root = root
        self.home = root / "home"
        self.cwd = root / "project"
        self.venv = root / "venv"
        self.evidence_dir = evidence_dir
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.home.mkdir()
        self.cwd.mkdir()
        self.commands = []
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(self.venv)
        bin_dir = self.venv / ("Scripts" if os.name == "nt" else "bin")
        self.python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        self.cli = bin_dir / ("msprof-analyze.exe" if os.name == "nt" else "msprof-analyze")
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PYTHON", "PT_SNAP_"))
            and key not in {"CODEX_HOME", "CLAUDE_CONFIG_DIR", "VIRTUAL_ENV"}
        }
        self.env.update(
            HOME=str(self.home),
            USERPROFILE=str(self.home),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            XDG_CACHE_HOME=str(self.home / ".cache"),
            VIRTUAL_ENV=str(self.venv),
            PATH=f"{bin_dir}{os.pathsep}{self.env.get('PATH', '')}",
            PWD=str(self.cwd),
            PYTHONNOUSERSITE="1",
            PYTHONUTF8="1",
            PIP_DISABLE_PIP_VERSION_CHECK="1",
            NO_COLOR="1",
        )
        install = [str(self.python), "-m", "pip", "install"]
        if wheelhouse is not None:
            install += ["--no-index", "--find-links", str(wheelhouse)]
        self.run("install", [*install, str(wheel)])
        assert self.cli.is_file()
        self.identity = self.python_json("identity", PROBE)
        assert self.identity["prefix"] != self.identity["base_prefix"]
        assert Path(self.identity["prefix"]) == self.venv
        assert Path(self.identity["executable"]) == self.python
        assert self.identity["user_site_enabled"] is False
        for module in self.identity["modules"].values():
            assert Path(module).is_relative_to(self.venv), module
        source_root = Path(__file__).resolve().parents[2]
        assert all(not Path(path).resolve().is_relative_to(source_root) for path in self.identity["sys_path"])
        assert self.identity["entry_point"] == "msprof_analyze.cli.pt_snap_cli:main"
        assert self.identity["query_limits"] == {
            "max_work_rows": 100_000,
            "max_work_bytes": 64 * 1024 * 1024,
            "max_scratch_db_bytes": 512 * 1024 * 1024,
        }
        self.wheel_hash = sha256(wheel)

    def run(self, label, command, *, expected=0):
        started = time.perf_counter()
        result = subprocess.run(
            command,
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.commands.append(
            {
                "label": label,
                "command": [str(item) for item in command],
                "cwd": str(self.cwd),
                "home": str(self.home),
                "returncode": result.returncode,
                "seconds": time.perf_counter() - started,
            }
        )
        (self.evidence_dir / f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
        (self.evidence_dir / f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
        (self.evidence_dir / "commands.json").write_text(json.dumps(self.commands, indent=2), encoding="utf-8")
        assert result.returncode == expected, f"{command}\nexit={result.returncode}\n{result.stdout}\n{result.stderr}"
        return result

    def cli_json(self, label, *arguments, expected=0):
        result = self.run(label, [str(self.cli), "pt-snap", *map(str, arguments)], expected=expected)
        if expected == 0:
            assert not result.stderr, result.stderr
            return json.loads(result.stdout)
        assert not result.stdout, result.stdout
        return json.loads(result.stderr)

    def python_json(self, label, script, *arguments):
        result = self.run(label, [str(self.python), "-I", "-c", script, *map(str, arguments)])
        assert not result.stderr, result.stderr
        return json.loads(result.stdout)


def write_scale_source(path, count):
    """Replay-valid allocator trace: static occupancy, survivors, repeated reuse.

    Three retained allocations precede 16-byte alloc/request/complete cycles.
    count % 3 == 1 leaves the last cycle live. At the default 500000 boundary,
    alloc 499998 requests free at 499999 and completes in shard two at 500000.
    The final segment is contiguous, including the trailing inactive space.
    No external or committed pickle is loaded to construct this test-owned file.
    """
    assert count >= 10 and count % 3 == 1
    retained = [(4160, 64), (4224, 32), (4256, 16)]

    def trace(action, address, size, name):
        return {
            "action": action,
            "addr": address,
            "size": size,
            "stream": 0,
            "frames": [
                {"filename": "scale.py", "line": 10, "name": name},
                {"filename": "train.py", "line": 20, "name": "step"},
            ],
        }

    events = [trace("alloc", addr, size, f"retain_{size}") for addr, size in retained]
    cycle = [trace(action, 4096, 16, action) for action in ("alloc", "free_requested", "free_completed")]
    events.extend(dict(cycle[index % 3]) for index in range(3, count))
    sizes = [16, 32, 16, 64, 32, 16, 4096 - 176]
    blocks, address = [], 4096
    for index, size in enumerate(sizes):
        blocks.append(
            {
                "address": address,
                "size": size,
                "requested_size": size if index < 6 else 0,
                "state": "active_allocated" if index < 6 else "inactive",
                "frames": [],
            }
        )
        address += size
    data = {
        "segments": [
            {
                "address": 4096,
                "total_size": 4096,
                "stream": 0,
                "segment_type": "small",
                "allocated_size": 176,
                "active_size": 176,
                "device": 0,
                "is_expandable": False,
                "frames": [],
                "blocks": blocks,
            }
        ],
        "device_traces": [events],
    }
    with path.open("wb") as stream:
        pickle.dump(data, stream, protocol=4)
    return path


def query_cases(boundary):
    """Catalog coverage plus cross-shard identity and real pagination cases."""
    return [
        {"name": name, "template": template, "params": params}
        for name, template, params in [
            ("memory_peak", "memory_peak", {}),
            ("allocator_gap", "allocator_gap", {}),
            (
                "event",
                "event",
                {"min_id": 0, "limit": 5, "offset": boundary - 2, "order_dir": "ASC"},
            ),
            (
                "allocation",
                "allocation",
                {"min_id": 0, "limit": 5, "offset": boundary - 2, "order_dir": "ASC"},
            ),
            ("block", "block", {"limit": 5, "offset": 2, "order_by": "id", "order_dir": "ASC"}),
            ("crossing_block", "block", {"id": boundary - 2}),
            ("leak_detection", "leak_detection", {"limit": 5}),
            ("freed_block_lifetime", "freed_block_lifetime", {}),
            ("callstack_analysis", "callstack_analysis", {"min_count": 1}),
            ("preexisting_live", "preexisting_live", {"event_id": boundary - 1}),
            (
                "active_before",
                "active_blocks_at_event",
                {"event_id": boundary - 1, "order_by": "id", "order_dir": "ASC"},
            ),
            (
                "active_after",
                "active_blocks_at_event",
                {"event_id": boundary, "order_by": "id", "order_dir": "ASC"},
            ),
            (
                "active_static_offset",
                "active_blocks_at_event",
                {
                    "event_id": boundary - 1,
                    "include_static": True,
                    "order_by": "id",
                    "order_dir": "ASC",
                    "offset": 1,
                    "limit": 3,
                },
            ),
            (
                "active_dynamic_offset",
                "active_blocks_at_event",
                {
                    "event_id": boundary - 1,
                    "include_static": False,
                    "order_by": "id",
                    "order_dir": "ASC",
                    "offset": 1,
                    "limit": 2,
                },
            ),
            (
                "active_groups",
                "active_memory_callstack_at_event",
                {"event_id": boundary - 1, "top_n": -1},
            ),
            ("event_frames", "event_frames", {"event_id": boundary - 1}),
            (
                "active_memory_frame_tree_at_event",
                "active_memory_frame_tree_at_event",
                {"event_id": boundary - 1},
            ),
        ]
    ]
