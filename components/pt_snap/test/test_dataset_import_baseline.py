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

"""Structural benchmark contracts, never speed assertions or fixture execution."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.dataset_import_baseline import rss_kib, source_identity


@pytest.mark.parametrize("platform,raw,expected", [("darwin", 1048576, 1024), ("linux", 1024, 1024)])
def test_isolated_self_rss_units(platform, raw, expected):
    assert rss_kib(raw, platform) == expected


def test_source_gate_checks_exact_hash_and_size_without_pickle_load(tmp_path):
    source = tmp_path / "not-an-executable-fixture.txt"
    source.write_bytes(b"hash only")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert source_identity(source, digest)["bytes"] == 9
    with pytest.raises(ValueError, match="exact reviewed"):
        source_identity(source, "0" * 64)
    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="canonical"):
        source_identity(link, digest)


def test_existing_parent_refused_before_import_and_preserved(tmp_path):
    source = tmp_path / "hash-only.txt"
    source.write_bytes(b"not pickle; must not load")
    script = Path(__file__).resolve().parents[1] / "benchmarks/dataset_import_baseline.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source",
            str(source),
            "--sha256",
            hashlib.sha256(source.read_bytes()).hexdigest(),
            "--device",
            "0",
            "--capacity",
            "2",
            "--output",
            str(tmp_path),
            "--trusted-pickle",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "FileExistsError" in result.stderr
    assert source.read_bytes() == b"not pickle; must not load"
    assert sorted(p.name for p in tmp_path.iterdir()) == [source.name]


def test_oversized_source_rejected_before_open(tmp_path, monkeypatch):
    source = tmp_path / "large.pkl"
    source.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    monkeypatch.setattr(Path, "open", lambda *_a, **_k: pytest.fail("oversized source opened"))
    with pytest.raises(ValueError, match="small source"):
        source_identity(source, "0" * 64)


@pytest.mark.parametrize("flags", [["--mode", "single-db"], ["--mode", "single-db", "--phase", "cold"]])
def test_hidden_flags_require_pair_and_owner_before_pickle(tmp_path, flags):
    source = tmp_path / "inert.txt"
    source.write_bytes(b"not pickle")
    script = Path(__file__).resolve().parents[1] / "benchmarks/dataset_import_baseline.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source",
            str(source),
            "--sha256",
            hashlib.sha256(source.read_bytes()).hexdigest(),
            "--device",
            "0",
            "--capacity",
            "2",
            "--output",
            str(tmp_path / "missing"),
            "--trusted-pickle",
            *flags,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "supplied together" in result.stderr
    assert not (tmp_path / "missing").exists()


def test_reuse_miss_refuses_rebuild_and_preserves_existing_actual_bytes(tmp_path):
    from benchmarks.dataset_import_baseline import cache_hashes

    source = tmp_path / "inert.pkl"
    source.write_bytes(b"not pickle")
    output = tmp_path / "single-db"
    output.mkdir()
    old = output / "inert.pkl.db"
    old.write_bytes(b"old invalid destination must not be replaced")
    before = old.read_bytes()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    envelope = tmp_path / "run-envelope.json"
    envelope.write_text(
        json.dumps(
            {
                "source": source_identity(source, digest),
                "device": 0,
                "capacity": 2,
                "cacheHashes": {"single-db": cache_hashes(output)},
            }
        )
    )
    script = Path(__file__).resolve().parents[1] / "benchmarks/dataset_import_baseline.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source",
            str(source),
            "--sha256",
            digest,
            "--device",
            "0",
            "--capacity",
            "2",
            "--output",
            str(output),
            "--trusted-pickle",
            "--mode",
            "single-db",
            "--phase",
            "reuse",
            "--envelope",
            str(envelope),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "refuse deserialization" in result.stderr
    assert old.read_bytes() == before and sorted(p.name for p in output.iterdir()) == [old.name]

    # Deliberately no timing/RSS/speedup threshold: these are observations.


def test_peak_rss_is_explicitly_unavailable_without_posix_resource(monkeypatch):
    from benchmarks import dataset_import_baseline as baseline

    monkeypatch.setattr(baseline, "resource", None)
    assert baseline.process_peak_rss() is None


def test_peak_rss_uses_current_process_only(monkeypatch):
    from types import SimpleNamespace

    from benchmarks import dataset_import_baseline as baseline

    calls = []

    def getrusage(who):
        calls.append(who)
        return SimpleNamespace(ru_maxrss=1234)

    monkeypatch.setattr(baseline, "resource", SimpleNamespace(RUSAGE_SELF=0, getrusage=getrusage))
    assert baseline.process_peak_rss() == 1234
    assert calls == [0]
