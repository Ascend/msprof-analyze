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

"""Independent readers overlap real query stages without sharing analyzers."""

import multiprocessing
import queue
import threading

import pytest

from test.core.dataset_lifecycle_fixtures import build
from test.dataset_concurrency_support import (
    ISOLATED_ENV,
    WAIT_SECONDS,
    lifecycle_stage,
    process_reader,
    query_worker,
    read_query,
)
from test.test_dataset_focus import hashes


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ISOLATED_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("readers", [2, 4])
@pytest.mark.parametrize("route", ["attach", "scratch"])
@pytest.mark.parametrize("kind", ["threads", "processes"])
def test_simultaneous_readers_return_complete_identical_results(tmp_path, kind, route, readers):
    _, root, _, _, blocks = build(tmp_path, 7)
    before = hashes(root)
    scratch_parent = tmp_path / "scratch"
    scratch_parent.mkdir()
    with lifecycle_stage(route, scratch_parent, lambda evidence: None):
        expected = read_query(root, route)
    assert expected["returned"] == expected["total"] == len(blocks)
    assert expected["total_is_exact"] and not expected["has_more"]
    assert {row["id"] for row in expected["rows"]} == {block["id"] for block in blocks}

    context = multiprocessing.get_context("spawn") if kind == "processes" else threading
    ready = context.Barrier(readers + 1)
    release = context.Event()
    output = context.Queue() if kind == "processes" else queue.Queue()
    workers = []

    def reached(evidence):
        output.put(("stage", evidence))
        ready.wait(WAIT_SECONDS)
        if not release.wait(WAIT_SECONDS):
            raise TimeoutError("Parent did not release the query-stage barrier")

    try:
        with lifecycle_stage(route, scratch_parent, reached):
            for _ in range(readers):
                worker = (
                    context.Process(
                        target=process_reader,
                        args=(root, route, scratch_parent, ready, release, output),
                    )
                    if kind == "processes"
                    else threading.Thread(target=query_worker, args=(root, route, output))
                )
                workers.append(worker)
                worker.start()
            # Every reader has completed a real SQL operation and holds its own
            # connection open. No scheduling speed or arbitrary sleep is evidence.
            ready.wait(WAIT_SECONDS)
            stages = [output.get(timeout=WAIT_SECONDS) for _ in range(readers)]
            assert all(kind == "stage" for kind, _ in stages), stages
            identities = {(item["pid"], item["thread"]) for _, item in stages}
            assert len(identities) == readers
            if route == "scratch":
                paths = {item["database"] for _, item in stages}
                assert len(paths) == readers
                assert all(item["inserted_rows"] > 0 for _, item in stages)
                assert len(list(scratch_parent.glob("*/derived.db"))) == readers
            else:
                assert not list(scratch_parent.iterdir())
            assert hashes(root) == before
            release.set()
            results = [output.get(timeout=WAIT_SECONDS) for _ in range(readers)]
            assert all(kind == "result" for kind, _ in results), results
            assert all(result == expected for _, result in results)
    finally:
        release.set()
        ready.abort()
        for worker in workers:
            worker.join(WAIT_SECONDS)
            if kind == "processes" and worker.is_alive():
                worker.terminate()
                worker.join(WAIT_SECONDS)
            assert not worker.is_alive()
            if kind == "processes":
                assert worker.exitcode == 0
                worker.close()
        if kind == "processes":
            output.close()
            output.join_thread()
    # Only after all product contexts have exited do we check cleanup. The test
    # does not remove scratch directories to manufacture this observation.
    assert not list(scratch_parent.iterdir())
    assert hashes(root) == before
