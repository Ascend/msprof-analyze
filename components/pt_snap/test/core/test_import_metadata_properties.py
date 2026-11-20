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

"""Generated import-metadata validation, without deserializing pickle bytes.

Mappings are trusted test-owned values. SQLite fixtures deliberately omit type
coercion/constraints so malformed stored values reach the actual read validator.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pt_snap_cli.core.importing.import_metadata import (
    IMPORT_FORMAT_VERSION,
    METADATA_SCHEMA_VERSION,
    ImportMetadataService,
)
from pt_snap_cli.core.importing.import_metadata_contract import metadata_from_mapping

PROPERTY_SETTINGS = settings(max_examples=35, derandomize=True, database=None, deadline=None, print_blob=True)
INTEGER_FIELDS = (
    "metadata_schema_version",
    "import_format_version",
    "source_size",
    "requested_device",
)
STRING_FIELDS = (
    "source_sha256",
    "source_name",
    "importer_name",
    "importer_version",
    "completed_at",
)
FIELDS = INTEGER_FIELDS + STRING_FIELDS
TEXT = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_中文", min_size=1, max_size=24)


@st.composite
def _valid_metadata(draw: st.DrawFn) -> dict[str, object]:
    return {
        "metadata_schema_version": METADATA_SCHEMA_VERSION,
        "import_format_version": IMPORT_FORMAT_VERSION,
        "source_sha256": draw(st.binary(min_size=32, max_size=32)).hex(),
        "source_size": draw(st.integers(0, 2**63 - 1)),
        "source_name": draw(TEXT) + ".pkl",
        "requested_device": draw(st.one_of(st.none(), st.integers(0, 1024))),
        "importer_name": draw(TEXT),
        "importer_version": draw(TEXT),
        "completed_at": draw(
            st.datetimes(
                min_value=datetime(2000, 1, 1),
                max_value=datetime(2030, 12, 31),
                timezones=st.just(timezone.utc),
            )
        ).isoformat(),
    }


def _database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE dictionary (`table` TEXT, `column` TEXT, `key` TEXT, `value` TEXT)")
        conn.execute("CREATE TABLE trace_entry_0 (id INTEGER PRIMARY KEY)")


def _store_unvalidated(path: Path, values: dict[str, object]) -> None:
    # Field names are fixed test constants, never generated SQL identifiers.
    columns = ("id",) + tuple(field for field in FIELDS if field in values)
    quoted = ", ".join(f'"{field}"' for field in columns)
    placeholders = ", ".join("?" for _ in columns)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(f"CREATE TABLE pt_snap_metadata ({quoted})")
        conn.execute(
            f"INSERT INTO pt_snap_metadata VALUES ({placeholders})",
            [1] + [values[field] for field in columns[1:]],
        )


def _assert_invalid_read_is_nonmutating(values: dict[str, object]) -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "invalid.db"
        _database(path)
        _store_unvalidated(path, values)
        before = path.read_bytes()
        inspection = ImportMetadataService().inspect(path)
        assert inspection.status == "invalid"
        assert inspection.reason == "metadata_invalid"
        assert inspection.metadata is None
        assert path.read_bytes() == before


@PROPERTY_SETTINGS
@given(values=_valid_metadata())
def test_generated_valid_metadata_round_trips_mapping_and_sqlite(values: dict[str, object]) -> None:
    metadata = metadata_from_mapping(values)
    assert asdict(metadata) == values
    with TemporaryDirectory() as directory:
        path = Path(directory) / "valid.db"
        _database(path)
        service = ImportMetadataService()
        service.write(path, metadata)
        before = path.read_bytes()
        inspection = service.inspect(path)
        assert inspection.status == "available"
        assert inspection.reason is None
        assert inspection.metadata == metadata
        decision = service.evaluate_cache(path, metadata.source_sha256, metadata.requested_device)
        assert decision.reused is True
        assert decision.metadata == metadata
        assert decision.reason is None
        assert path.read_bytes() == before


@PROPERTY_SETTINGS
@given(values=_valid_metadata(), missing=st.sets(st.sampled_from(FIELDS), min_size=1))
def test_generated_missing_metadata_fields_have_controlled_inspection(
    values: dict[str, object], missing: set[str]
) -> None:
    incomplete = {field: value for field, value in values.items() if field not in missing}
    with pytest.raises(KeyError) as error:
        metadata_from_mapping(incomplete)
    assert error.value.args[0] in missing
    _assert_invalid_read_is_nonmutating(incomplete)


@pytest.mark.parametrize("field", INTEGER_FIELDS)
@PROPERTY_SETTINGS
@given(
    values=_valid_metadata(),
    wrong_type=st.one_of(
        st.booleans(),
        st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
        st.text(max_size=20),
        st.lists(st.integers(-10, 10), max_size=3),
    ),
)
def test_generated_integer_metadata_does_not_coerce_wrong_types(
    field: str, values: dict[str, object], wrong_type: object
) -> None:
    values[field] = wrong_type
    # This is the pure mapping contract: in particular bool is not int. SQLite
    # binds bool as an integer, so testing this only through SQL would hide it.
    with pytest.raises(TypeError, match="Expected integer metadata value"):
        metadata_from_mapping(values)


@pytest.mark.parametrize("field", INTEGER_FIELDS)
@PROPERTY_SETTINGS
@given(values=_valid_metadata(), magnitude=st.integers(1, 2**63 - 1))
def test_generated_negative_metadata_numbers_have_controlled_inspection(
    field: str, values: dict[str, object], magnitude: int
) -> None:
    values[field] = -magnitude
    with pytest.raises(ValueError):
        metadata_from_mapping(values)
    _assert_invalid_read_is_nonmutating(values)


@pytest.mark.parametrize("field", STRING_FIELDS)
@PROPERTY_SETTINGS
@given(values=_valid_metadata(), empty=st.sampled_from([None, ""]))
def test_generated_missing_string_values_have_controlled_inspection(
    field: str, values: dict[str, object], empty: object
) -> None:
    values[field] = empty
    with pytest.raises(TypeError, match="Expected non-empty metadata string"):
        metadata_from_mapping(values)
    _assert_invalid_read_is_nonmutating(values)


@PROPERTY_SETTINGS
@given(values=_valid_metadata(), suffix=st.text(alphabet="0123456789abcdef", min_size=0, max_size=70))
def test_generated_malformed_digest_has_controlled_inspection(values: dict[str, object], suffix: str) -> None:
    values["source_sha256"] = "g" + suffix
    with pytest.raises(ValueError, match="lowercase SHA-256 digest"):
        metadata_from_mapping(values)
    _assert_invalid_read_is_nonmutating(values)


@PROPERTY_SETTINGS
@given(values=_valid_metadata(), offset_hours=st.integers(1, 23))
def test_generated_non_utc_timestamp_has_controlled_inspection(values: dict[str, object], offset_hours: int) -> None:
    values["completed_at"] = f"2026-01-01T00:00:00+{offset_hours:02d}:00"
    with pytest.raises(ValueError, match="completed_at must use UTC"):
        metadata_from_mapping(values)
    _assert_invalid_read_is_nonmutating(values)
