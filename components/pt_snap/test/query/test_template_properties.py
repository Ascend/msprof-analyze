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

"""Generated YAML contracts at their existing validation/rejection boundaries.

The registry promises warning-and-skip for malformed files. The lower-level
QueryConfig loader does not currently normalize arbitrary structural YAML into
one domain error; these tests do not claim that stronger, unsupported contract.
"""

from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from pt_snap_cli.query import registry
from pt_snap_cli.query.config import QueryConfig

PROPERTY_SETTINGS = settings(max_examples=35, derandomize=True, database=None, deadline=None, print_blob=True)
IDENTIFIERS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=16)
VALUES = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(-100, 100), st.text(max_size=16)),
    lambda children: st.one_of(st.lists(children, max_size=4), st.dictionaries(IDENTIFIERS, children, max_size=4)),
    max_leaves=8,
)


def _load_template(body: dict[str, object]):
    return QueryConfig.load_yaml_from_string(yaml.safe_dump({"queries": {"generated": body}})).queries["generated"]


@PROPERTY_SETTINGS
@given(
    column=IDENTIFIERS,
    choices=st.lists(st.integers(-1000, 1000), min_size=1, max_size=8, unique=True),
    version=st.integers(1, 100),
    sentinel=st.integers(-1000, 1000),
    units=st.sampled_from(["bytes", "gib", "percent", "event_id", "count", "address", "flag", "text"]),
)
def test_generated_yaml_preserves_schema_and_validates_declared_choices(
    column: str, choices: list[int], version: int, sentinel: int, units: str
) -> None:
    schema = [{"column": column, "type": "int", "units": units, "sentinel": sentinel}]
    template = _load_template(
        {
            "query": "SELECT {{ selected }} AS value",
            "semantics_version": version,
            "output_schema": schema,
            "parameters": {
                "selected": {"type": "int", "choices": choices, "default": choices[0]},
                "required_text": {"type": "str", "required": True},
            },
        }
    )
    assert template.name == "generated"
    assert template.output_schema == schema
    assert template.semantics_version == version
    assert template.parameters["selected"].choices == choices
    for choice in choices:
        assert template.validate_params({"selected": str(choice), "required_text": column}) == {
            "selected": choice,
            "required_text": column,
        }
    assert template.validate_params({"required_text": column})["selected"] == choices[0]
    with pytest.raises(ValueError, match="Required parameter 'required_text' is missing"):
        template.validate_params({})
    with pytest.raises(ValueError, match="'selected' must be one of"):
        template.validate_params({"selected": max(choices) + 1, "required_text": column})


@PROPERTY_SETTINGS
@given(unknown=IDENTIFIERS, value=VALUES)
def test_generated_unknown_schema_fields_and_query_parameters_are_rejected(unknown: str, value: object) -> None:
    key = f"unknown_{unknown}"
    with pytest.raises(ValueError, match="unsupported keys") as error:
        _load_template({"query": "SELECT 1", "output_schema": [{"column": "id", "type": "int", key: value}]})
    assert key in str(error.value)
    template = _load_template({"query": "SELECT 1", "parameters": {"limit": {"type": "int", "default": -1}}})
    with pytest.raises(ValueError, match=r"Unknown parameter\(s\)") as error:
        template.validate_params({key: value})
    assert key in str(error.value)


@pytest.mark.parametrize("missing", ["column", "type"])
@PROPERTY_SETTINGS
@given(column=IDENTIFIERS)
def test_generated_output_columns_require_both_declared_fields(missing: str, column: str) -> None:
    schema = {"column": column, "type": "int"}
    del schema[missing]
    with pytest.raises(ValueError, match="must declare a non-empty"):
        _load_template({"query": "SELECT 1", "output_schema": [schema]})


@pytest.mark.parametrize("field", ["units", "metric_semantics", "scope"])
@PROPERTY_SETTINGS
@given(value=VALUES)
def test_generated_invalid_enum_metadata_is_rejected(field: str, value: object) -> None:
    # A prefix constructs an invalid enum without filtering or discarding cases.
    malformed = f"unsupported:{value!r}" if isinstance(value, str) else value
    with pytest.raises(ValueError, match=f"{field} must be one of"):
        _load_template(
            {
                "query": "SELECT 1",
                "output_schema": [{"column": "id", "type": "int", field: malformed}],
            }
        )


@PROPERTY_SETTINGS
@given(
    value=st.one_of(
        st.booleans(),
        st.integers(-1000, 0),
        st.text(max_size=20),
        st.lists(st.integers(-1000, 1000), max_size=4),
    )
)
def test_generated_invalid_semantics_versions_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="semantics_version.*positive integer"):
        _load_template({"query": "SELECT 1", "semantics_version": value})


@pytest.mark.parametrize(
    "defect", ["root_sequence", "queries_sequence", "scalar_entry", "parameters_sequence", "syntax"]
)
@PROPERTY_SETTINGS
@given(payload=IDENTIFIERS)
def test_generated_malformed_yaml_is_skipped_without_losing_valid_neighbors(defect: str, payload: str) -> None:
    malformed = {
        "root_sequence": yaml.safe_dump([payload]),
        "queries_sequence": yaml.safe_dump({"queries": [payload]}),
        "scalar_entry": yaml.safe_dump({"queries": {"invalid": payload}}),
        "parameters_sequence": yaml.safe_dump({"queries": {"invalid": {"parameters": [payload]}}}),
        "syntax": f"queries: [{payload}",
    }[defect]
    with TemporaryDirectory() as directory, pytest.MonkeyPatch.context() as monkeypatch:
        root = Path(directory)
        # A detached registry snapshot keeps generated registrations local to
        # this example and restores both normal entries and lazy factories.
        monkeypatch.setattr(registry, "_registry", copy.deepcopy(registry._registry))
        invalid_name = f"property_invalid_{payload}"
        valid_name = f"property_valid_{payload}"
        registry._registry.unregister(invalid_name)
        registry._registry.unregister(valid_name)
        malformed = malformed.replace("invalid:", f"{invalid_name}:")
        bad = root / "a_bad.yaml"
        bad.write_text(malformed, encoding="utf-8")
        (root / "z_good.yaml").write_text(
            yaml.safe_dump({"queries": {valid_name: {"query": "SELECT 1 AS id"}}}),
            encoding="utf-8",
        )
        with pytest.warns(UserWarning, match="Failed to load query template") as warnings:
            registry._load_yaml_templates(root)
        assert len(warnings) == 1
        assert str(bad) in str(warnings[0].message)
        assert registry.get_query(invalid_name) is None
        valid = registry.get_query(valid_name)
        assert valid is not None
        assert valid.query == "SELECT 1 AS id"
