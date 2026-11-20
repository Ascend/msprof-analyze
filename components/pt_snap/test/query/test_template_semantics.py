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

"""Packaged query template semantic metadata."""

from __future__ import annotations

import json

from pt_snap_cli.query.config import OUTPUT_SCHEMA_METRIC_SEMANTICS
from pt_snap_cli.query.registry import (
    QueryRegistry,
    _load_all_templates,
    get_query,
    get_template_info,
    list_queries,
)


def setup_function() -> None:
    QueryRegistry.reset()
    _load_all_templates()


_ANNOTATED = (
    "leak_detection",
    "memory_peak",
    "allocator_gap",
    "active_memory_callstack_at_event",
    "preexisting_live",
    "freed_block_lifetime",
)


def _column(template_name: str, column: str) -> dict[str, object]:
    template = get_query(template_name)
    assert template is not None
    match = next(item for item in template.output_schema if item["column"] == column)
    return match


def test_packaged_metric_semantics_match_published_vocabulary() -> None:
    used: set[str] = set()
    for name in list_queries():
        template = get_query(name)
        assert template is not None
        for column in template.output_schema:
            value = column.get("metric_semantics")
            if value is not None:
                used.add(value)
    assert used == OUTPUT_SCHEMA_METRIC_SEMANTICS


def test_legacy_templates_remain_loadable_without_semantics() -> None:
    info = get_template_info("allocation")
    assert info is not None
    assert info["semantics_version"] is None
    assert info["interpretation_limits"] == []
    assert info["output_schema"][0] == {"column": "id", "type": "int"}


def test_annotated_templates_share_a_json_serializable_contract() -> None:
    for name in _ANNOTATED:
        template = get_query(name)
        assert template is not None
        assert template.semantics_version == (
            2 if name in ("active_memory_callstack_at_event", "memory_peak", "allocator_gap") else 1
        )
        assert template.interpretation_limits
        info = get_template_info(name)
        assert info is not None
        json.dumps(info)
        if template.query_variants:
            assert template.sql_for_layout("v1") != template.sql_for_layout("v2")
            assert template.output_schema


def test_leak_detection_metadata_marks_candidates_and_event_ids() -> None:
    template = get_query("leak_detection")
    assert template is not None
    joined = " ".join(template.interpretation_limits)
    assert "not a confirmed leak" in joined
    alloc = _column("leak_detection", "allocEventId")
    assert alloc["units"] == "event_id"
    assert alloc["sentinel"] == -1
    assert alloc["metric_semantics"] == "ordering_marker"
    address = _column("leak_detection", "address")
    assert "not allocation identity" in " ".join(address["interpretation_limits"])


def test_memory_peak_metadata_forbids_cross_event_subtraction() -> None:
    template = get_query("memory_peak")
    assert template is not None
    joined = " ".join(template.interpretation_limits)
    assert "do not subtract" in joined.lower()
    assert _column("memory_peak", "peak_allocated")["metric_semantics"] == "instantaneous_occupancy"
    assert _column("memory_peak", "peak_active")["metric_semantics"] == "instantaneous_occupancy"
    assert _column("memory_peak", "peak_active_event_id")["units"] == "event_id"


def test_allocator_gap_metadata_is_same_event_not_fragmentation() -> None:
    template = get_query("allocator_gap")
    assert template is not None
    joined = " ".join(template.interpretation_limits)
    assert "not itself fragmentation" in joined
    gap = _column("allocator_gap", "reserved_active_gap_at_active_peak")
    assert gap["metric_semantics"] == "same_event_gap"
    assert gap["units"] == "bytes"


def test_callstack_percent_metadata_matches_truncated_byte_denominator() -> None:
    percent = _column("active_memory_callstack_at_event", "percent_of_active_blocks")
    assert percent["units"] == "percent"
    assert percent["metric_semantics"] == "share_of_included_rows"
    assert percent["scope"] == "mixed"
    denominator = percent["denominator"]
    assert "top_n truncation of dynamic" in denominator
    assert "max_rows" in denominator
    assert "not all active memory" in denominator
    limits = " ".join(percent["interpretation_limits"])
    assert "not a share of block count" in limits
    category = _column("active_memory_callstack_at_event", "category")
    assert category["scope"] == "mixed"
    assert "Per-row scope" in " ".join(category["interpretation_limits"])


def test_missing_callstack_contract_covers_normalization_and_group_boundaries() -> None:
    column = _column("active_memory_callstack_at_event", "callstack")
    limits = " ".join(column["interpretation_limits"])
    for term in (
        "[missing callstack]",
        "empty strings",
        "NULL text or IDs",
        "missing joined allocation events or callstack records",
        "merge before top_n",
        "callstackId in v2",
        "Whitespace-only",
        "not unique group identities",
    ):
        assert term in limits
