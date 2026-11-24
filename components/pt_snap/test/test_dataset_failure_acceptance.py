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

"""Real subprocess adapter parity for bounded failures, without partial output."""

import json

import pytest

from pt_snap_cli.api import QueryLimits, SnapshotAnalyzer
from pt_snap_cli.core.common.errors import QueryExecutionError, QueryTimeoutError
from test.dataset_failure_support import (
    ENV_NAMES,
    fault_hooks,
    lifecycle_dataset,
    run_cli,
)
from test.test_dataset_focus import hashes


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("kind", ["rows", "bytes", "timeout", "attach", "scratch_space", "scratch_io"])
def test_real_cli_text_json_and_api_preserve_typed_failure_and_cleanup(tmp_path, kind):
    root = lifecycle_dataset(tmp_path / "dataset", 40)
    before = hashes(root)
    limits = QueryLimits(
        max_work_rows=1 if kind == "rows" else 100_000,
        max_work_bytes=1 if kind == "bytes" else 64 * 1024**2,
        max_scratch_db_bytes=(4096 if kind == "scratch_space" else 0 if kind == "attach" else 512 * 1024**2),
    )
    expected_type = QueryTimeoutError if kind == "timeout" else QueryExecutionError
    api_evidence = {}
    with fault_hooks(kind, api_evidence), SnapshotAnalyzer(root) as analyzer:
        with pytest.raises(expected_type) as caught:
            analyzer.execute_query("block", {"limit": 5}, timeout_s=30.0, query_limits=limits)
    assert type(caught.value) is expected_type
    message = str(caught.value)
    assert message.count("Query execution failed:") <= 1
    assert not message.startswith("Query execution failed:")
    assert {
        "rows": "work budget exceeded",
        "bytes": "work budget exceeded",
        "timeout": "timed out after 30.0 seconds",
        "attach": "not authorized",
        "scratch_space": "scratch space exhausted",
        "scratch_io": "scratch storage failed",
    }[kind] in message
    observations = [api_evidence]
    for json_mode in (False, True):
        evidence = tmp_path / f"evidence-{json_mode}.json"
        args = [
            "query",
            str(root),
            "--template-use",
            "block",
            "--params",
            '{"limit":5}',
            "--timeout",
            "30",
            "--max-work-rows",
            str(limits.max_work_rows),
            "--max-work-bytes",
            str(limits.max_work_bytes),
            "--max-scratch-db-bytes",
            str(limits.max_scratch_db_bytes),
        ]
        result = run_cli(tmp_path, args + (["--json"] if json_mode else []), fault=kind, evidence=evidence)
        assert result.returncode == 1, (result.stdout, result.stderr)
        assert "Traceback" not in result.stdout + result.stderr
        if json_mode:
            assert result.stdout == ""
            payload = json.loads(result.stderr)
            assert payload["error"]["message"] == message
            assert payload["error"]["code"] == ("QUERY_TIMEOUT" if kind == "timeout" else "QUERY_FAILED")
            assert not {"rows", "total", "returned", "scope"} & payload.keys()
        else:
            assert result.stderr == ""
            assert result.stdout == f"Error executing query: {message}\n"
        observations.append(json.loads(evidence.read_text()))
        assert hashes(root) == before
    for evidence in observations:
        assert all(evidence["connections_closed"])
        assert all(evidence["scratch_removed"])
        if kind == "attach":
            assert evidence["events"] == ["attach_attempt_1", "attach_attempt_2"]
            assert evidence["connections_closed"] == [True]
        if kind.startswith("scratch") or kind == "timeout":
            assert evidence["scratch_removed"] == [True]
            assert "scratch_created" in evidence["events"]
        if kind == "timeout":
            assert "reduction_insert_completed" in evidence["events"]
    # Faults do not poison admission/cache state or prevent an ordinary retry.
    with SnapshotAnalyzer(root) as analyzer:
        result = analyzer.execute_query("block", {"limit": 5}, exact_total=True)
    assert result["total"] == 41 and result["returned"] == 5
    assert hashes(root) == before
    assert not any(root.rglob("*-journal"))
    assert not any(root.rglob("*-wal"))
    assert not any(root.rglob("*-shm"))
