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

from __future__ import annotations

import hashlib
import re
from pathlib import Path

FIXTURE_DIR = Path("test/fixtures/snapshots")
MANIFEST = FIXTURE_DIR / "SHA256SUMS"
PICKLE_SUFFIXES = {".pkl", ".pickle"}
LFS_POINTER = re.compile(
    rb"version https://git-lfs.github.com/spec/v1\r?\n"
    rb"oid sha256:(?P<digest>[0-9a-f]{64})\r?\n"
    rb"size (?P<size>\d+)(?:\r?\n)?\Z"
)
EXPECTED_SIZES = {
    "snapshot_1768383987920985470.pkl": 573970,
    "snapshot_expandable.pkl": 581140,
    "snapshot_import_131k_sanitized.pickle": 43140853,
    "snapshot_import_628k_sanitized.pickle": 175057085,
    "snapshot_with_empty_cache_expandable.pkl": 614145,
    "snapshot_with_empty_cache.pkl": 617060,
    "snapshot_with_multi_devices.pkl": 1355829,
}


class FixtureProvenanceError(RuntimeError):
    pass


def load_manifest(manifest: Path = MANIFEST) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in manifest.read_text().splitlines():
        digest, filename = line.split("  ", 1)
        if filename in entries:
            raise FixtureProvenanceError(f"Duplicate fixture manifest entry: {filename}")
        entries[filename] = digest
    return entries


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fixture:
        for chunk in iter(lambda: fixture.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_names(names: list[str]) -> str:
    return ", ".join(names) if names else "<none>"


def _describe_set_mismatch(fixture_dir: Path, unexpected: list[str], missing: list[str]) -> str:
    # Only file names are reported; the guard never reads pickle content.
    return (
        f"Executable fixture set does not match the reviewed manifest in {fixture_dir}.\n"
        f"  unexpected (not in SHA256SUMS): {_format_names(unexpected)}\n"
        f"  missing (in SHA256SUMS but absent): {_format_names(missing)}\n"
        f"Move unreviewed pickles out of {fixture_dir}/ (for example into .tmp/), or complete "
        "the input review and update SHA256SUMS before running the suite."
    )


def verify_snapshot_fixtures(
    fixture_dir: Path = FIXTURE_DIR,
    manifest: Path = MANIFEST,
    expected_sizes: dict[str, int] = EXPECTED_SIZES,
) -> None:
    expected = load_manifest(manifest)
    fixtures = {path.name: path for path in fixture_dir.iterdir() if path.suffix.lower() in PICKLE_SUFFIXES}
    unexpected = sorted(set(fixtures) - set(expected))
    missing = sorted(set(expected) - set(fixtures))
    if unexpected or missing:
        raise FixtureProvenanceError(_describe_set_mismatch(fixture_dir, unexpected, missing))
    if set(expected) != set(expected_sizes):
        raise FixtureProvenanceError(
            "SHA256SUMS and the reviewed size table disagree; update both together.\n"
            f"  only in SHA256SUMS: {_format_names(sorted(set(expected) - set(expected_sizes)))}\n"
            f"  only in size table: {_format_names(sorted(set(expected_sizes) - set(expected)))}"
        )

    for filename, path in fixtures.items():
        pointer = LFS_POINTER.fullmatch(path.read_bytes()) if path.stat().st_size < 1024 else None
        actual_digest = pointer.group("digest").decode() if pointer else _sha256(path)
        actual_size = int(pointer.group("size")) if pointer else path.stat().st_size
        if actual_digest != expected[filename]:
            raise FixtureProvenanceError(f"Fixture checksum mismatch: {filename}")
        if actual_size != expected_sizes[filename]:
            raise FixtureProvenanceError(f"Fixture size mismatch: {filename}")
