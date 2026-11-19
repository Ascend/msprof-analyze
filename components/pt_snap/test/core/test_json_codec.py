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

from dataclasses import dataclass
from pathlib import Path

import pytest

from pt_snap_cli.core.common.json_codec import (
    JSON_SCHEMA_VERSION,
    json_error,
    json_success,
    to_jsonable,
)
from pt_snap_cli.core.common.models import FocusState, ImportMetadata, ImportResult


def test_to_jsonable_converts_paths_and_nested_models(tmp_path: Path) -> None:
    db_path = tmp_path / "sample.db"
    focus = FocusState(
        db_path=db_path,
        device_id=1,
        available_devices=[0, 1],
        source="project",
        focus_file=tmp_path / ".pt-snap" / "focus.json",
        callstack_layout="v2",
        callstack_layout_error=None,
    )
    result = ImportResult(
        db_path=db_path,
        device_id=1,
        focus_state=focus,
        reused=False,
        metadata=ImportMetadata(
            metadata_schema_version=1,
            import_format_version=2,
            source_sha256="abc",
            source_size=12,
            source_name="sample.pkl",
            requested_device=1,
            importer_name="pt-snap",
            importer_version="0.0",
            completed_at="2026-01-01T00:00:00Z",
        ),
        cache_miss_reason=None,
    )

    payload = to_jsonable(result)
    assert isinstance(payload, dict)

    assert payload["db_path"] == str(db_path)
    assert payload["reused"] is False
    assert payload["cache_miss_reason"] is None
    assert payload["device_id"] == 1
    assert payload["focus_state"]["focus_file"] == str(tmp_path / ".pt-snap" / "focus.json")
    assert payload["metadata"]["source_size"] == 12


def test_json_success_and_error_envelopes_keep_native_types() -> None:
    success = json_success(total=2, returned=2, empty=None, flag=True, items=(1, 2))
    assert success["schema_version"] == JSON_SCHEMA_VERSION
    assert success["ok"] is True
    assert success["total"] == 2
    assert success["empty"] is None
    assert success["flag"] is True
    assert success["items"] == [1, 2]

    failure = json_error("TEMPLATE_NOT_FOUND", "missing", "list templates")
    assert failure["ok"] is False
    assert failure["error"]["code"] == "TEMPLATE_NOT_FOUND"
    assert failure["error"]["hint"] == "list templates"


def test_to_jsonable_decodes_bytes_and_memoryview() -> None:
    assert to_jsonable(b"blob") == "blob"
    assert to_jsonable(bytearray(b"abc")) == "abc"
    assert to_jsonable(memoryview(b"xyz")) == "xyz"
    assert "\ufffd" in to_jsonable(b"\xff")


def test_json_success_rejects_reserved_envelope_keys() -> None:
    with pytest.raises(TypeError, match="reserved fields"):
        json_success(ok=False)
    with pytest.raises(TypeError, match="reserved fields"):
        json_success(schema_version=99)


def test_to_jsonable_rejects_unknown_types() -> None:
    @dataclass
    class Holder:
        value: object

    with pytest.raises(TypeError, match="Cannot serialize"):
        to_jsonable(Holder(value=object()))
