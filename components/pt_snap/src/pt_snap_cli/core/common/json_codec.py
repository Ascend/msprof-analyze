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

"""Shared JSON serialization for CLI result models."""

from __future__ import annotations

import json
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Union

JSON_SCHEMA_VERSION = 1

JsonValue = Union[
    Union[Union[Union[Union[Union[None, bool], int], float], str], List["JsonValue"]],
    Dict[str, "JsonValue"],
]


def to_jsonable(value: object) -> JsonValue:
    """Convert service models into JSON-safe values.

    ``Path`` becomes a string, bytes-like values decode as UTF-8 with
    replacement, nested dataclasses and mappings are walked, sequences
    become lists, and ``None`` stays ``null``. Numbers and booleans keep
    their JSON types.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_jsonable(getattr(value, item.name)) for item in dataclass_fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_jsonable(item) for item in value]
    raise TypeError(f"Cannot serialize {type(value)!r} to JSON")


def dumps_json(value: object) -> str:
    """Serialize ``value`` as indented UTF-8 JSON."""
    return json.dumps(to_jsonable(value), indent=2, ensure_ascii=False)


def json_success(**fields: Any) -> Dict[str, JsonValue]:
    """Build a success envelope. Extra fields are serialized in place."""
    converted = to_jsonable(fields)
    if not isinstance(converted, dict):
        raise TypeError("json_success fields must serialize to an object")
    reserved = {"schema_version", "ok"} & converted.keys()
    if reserved:
        raise TypeError(f"json_success reserved fields cannot be overridden: {sorted(reserved)}")
    payload: Dict[str, JsonValue] = {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": True,
    }
    payload.update(converted)
    return payload


def json_error(code: str, message: str, hint: Union[str, None] = None) -> Dict[str, JsonValue]:
    """Build a structured error envelope for stderr."""
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "hint": hint,
        },
    }
