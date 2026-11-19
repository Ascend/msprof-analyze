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

import hashlib
from pathlib import Path

import pytest

from test._fixture_provenance import (
    FixtureProvenanceError,
    verify_snapshot_fixtures,
)


def test_executable_snapshot_fixtures_match_reviewed_manifest() -> None:
    verify_snapshot_fixtures()



def _write_fixture(directory: Path, name: str, payload: bytes) -> tuple[str, int]:
    """Write a stand-in fixture and return its (sha256, size).

    The payload is arbitrary bytes, never a real pickle, so these tests keep the
    guard's no-deserialization property.
    """
    path = directory / name
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _write_manifest(directory: Path, entries: dict[str, str]) -> Path:
    manifest = directory / "SHA256SUMS"
    manifest.write_text("".join(f"{digest}  {name}\n" for name, digest in entries.items()))
    return manifest


def test_unexpected_local_pickle_is_named_with_guidance(tmp_path: Path) -> None:
    """Regression for issue #118: the failure must say which file is unreviewed."""
    digest, size = _write_fixture(tmp_path, "reviewed.pkl", b"reviewed")
    _write_fixture(tmp_path, "memory0.pickle", b"local capture")
    _write_fixture(tmp_path, "notes.txt", b"not a pickle, ignored")
    manifest = _write_manifest(tmp_path, {"reviewed.pkl": digest})

    with pytest.raises(FixtureProvenanceError) as exc_info:
        verify_snapshot_fixtures(tmp_path, manifest, {"reviewed.pkl": size})

    message = str(exc_info.value)
    assert f"does not match the reviewed manifest in {tmp_path}" in message
    assert "unexpected (not in SHA256SUMS): memory0.pickle" in message
    assert "missing (in SHA256SUMS but absent): <none>" in message
    assert "Move unreviewed pickles out of" in message
    assert "notes.txt" not in message


def test_missing_reviewed_pickle_is_named(tmp_path: Path) -> None:
    digest, size = _write_fixture(tmp_path, "present.pkl", b"present")
    manifest = _write_manifest(tmp_path, {"present.pkl": digest, "absent.pkl": "0" * 64})

    with pytest.raises(FixtureProvenanceError) as exc_info:
        verify_snapshot_fixtures(tmp_path, manifest, {"present.pkl": size, "absent.pkl": 1})

    message = str(exc_info.value)
    assert "unexpected (not in SHA256SUMS): <none>" in message
    assert "missing (in SHA256SUMS but absent): absent.pkl" in message


def test_unexpected_names_are_sorted_and_complete(tmp_path: Path) -> None:
    digest, size = _write_fixture(tmp_path, "reviewed.pkl", b"reviewed")
    _write_fixture(tmp_path, "zeta.pickle", b"z")
    _write_fixture(tmp_path, "alpha.PKL", b"a")
    manifest = _write_manifest(tmp_path, {"reviewed.pkl": digest})

    with pytest.raises(FixtureProvenanceError, match=r"not in SHA256SUMS\): alpha\.PKL, zeta\.pickle"):
        verify_snapshot_fixtures(tmp_path, manifest, {"reviewed.pkl": size})


def test_manifest_and_size_table_disagreement_is_reported(tmp_path: Path) -> None:
    digest, _ = _write_fixture(tmp_path, "reviewed.pkl", b"reviewed")
    manifest = _write_manifest(tmp_path, {"reviewed.pkl": digest})

    with pytest.raises(FixtureProvenanceError) as exc_info:
        verify_snapshot_fixtures(tmp_path, manifest, {})

    message = str(exc_info.value)
    assert "SHA256SUMS and the reviewed size table disagree" in message
    assert "only in SHA256SUMS: reviewed.pkl" in message
    assert "only in size table: <none>" in message


def test_checksum_and_size_mismatches_still_fail(tmp_path: Path) -> None:
    digest, size = _write_fixture(tmp_path, "reviewed.pkl", b"reviewed")

    wrong_digest = _write_manifest(tmp_path, {"reviewed.pkl": "f" * 64})
    with pytest.raises(FixtureProvenanceError, match="Fixture checksum mismatch: reviewed.pkl"):
        verify_snapshot_fixtures(tmp_path, wrong_digest, {"reviewed.pkl": size})

    right_digest = _write_manifest(tmp_path, {"reviewed.pkl": digest})
    with pytest.raises(FixtureProvenanceError, match="Fixture size mismatch: reviewed.pkl"):
        verify_snapshot_fixtures(tmp_path, right_digest, {"reviewed.pkl": size + 1})

    verify_snapshot_fixtures(tmp_path, right_digest, {"reviewed.pkl": size})


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"], ids=["lf", "crlf"])
def test_lfs_pointer_line_endings_preserve_digest_and_size_checks(tmp_path: Path, newline: bytes) -> None:
    digest = hashlib.sha256(b"reviewed object").hexdigest()
    name = "reviewed.pkl"
    pointer = newline.join([
        b"version https://git-lfs.github.com/spec/v1",
        f"oid sha256:{digest}".encode("ascii"),
        b"size 15",
        b"",
    ])
    (tmp_path / name).write_bytes(pointer)
    manifest = _write_manifest(tmp_path, {name: digest})
    verify_snapshot_fixtures(tmp_path, manifest, {name: 15})
    with pytest.raises(FixtureProvenanceError, match="Fixture size mismatch"):
        verify_snapshot_fixtures(tmp_path, manifest, {name: 16})
    wrong_manifest = _write_manifest(tmp_path, {name: "f" * 64})
    with pytest.raises(FixtureProvenanceError, match="Fixture checksum mismatch"):
        verify_snapshot_fixtures(tmp_path, wrong_manifest, {name: 15})
