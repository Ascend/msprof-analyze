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

"""Tests for result mapper."""

import pytest

from pt_snap_cli.query.mapper import (
    ResultMapper,
    map_result,
    map_results,
    register_model_factory,
    register_type_converter,
)


class TestResultMapper:
    def test_map_no_schema(self):
        mapper = ResultMapper()
        row = {"id": 1, "name": "test", "value": 3.14}

        result = mapper.map(row)
        assert result == row

    def test_map_with_schema(self):
        mapper = ResultMapper()
        row = {"id": "1", "size": "1024", "address": 4096}
        schema = [
            {"column": "id", "type": "int"},
            {"column": "size", "type": "int"},
            {"column": "address", "type": "hex"},
        ]

        result = mapper.map(row, schema)
        assert result["id"] == 1
        assert result["size"] == 1024
        assert result["address"] == "0x1000"

    def test_map_missing_column(self):
        mapper = ResultMapper()
        row = {"id": 1}
        schema = [
            {"column": "id", "type": "int"},
            {"column": "missing", "type": "str"},
        ]

        result = mapper.map(row, schema)
        assert result["id"] == 1
        assert result["missing"] is None

    def test_map_all(self):
        mapper = ResultMapper()
        rows = [
            {"id": "1", "value": "10"},
            {"id": "2", "value": "20"},
        ]
        schema = [
            {"column": "id", "type": "int"},
            {"column": "value", "type": "int"},
        ]

        results = mapper.map_all(rows, schema)
        assert results[0]["id"] == 1
        assert results[0]["value"] == 10
        assert results[1]["id"] == 2
        assert results[1]["value"] == 20

    def test_register_type_converter(self):
        mapper = ResultMapper()
        mapper.register_type_converter("custom", lambda x: f"custom_{x}")

        row = {"value": "test"}
        schema = [{"column": "value", "type": "custom"}]

        result = mapper.map(row, schema)
        assert result["value"] == "custom_test"

    def test_map_to_model(self):
        mapper = ResultMapper()

        class MockModel:
            def __init__(self, data):
                self.id = data["id"]
                self.name = data["name"]

        mapper.register_model_factory("MockModel", lambda d: MockModel(d))

        row = {"id": 1, "name": "test"}
        model = mapper.map_to_model(row, "MockModel")

        assert isinstance(model, MockModel)
        assert model.id == 1
        assert model.name == "test"

    def test_map_to_model_not_registered(self):
        mapper = ResultMapper()

        with pytest.raises(KeyError, match="Model factory not registered"):
            mapper.map_to_model({}, "NonExistent")

    def test_map_all_to_model(self):
        mapper = ResultMapper()

        class MockModel:
            def __init__(self, data):
                self.id = data["id"]

        mapper.register_model_factory("MockModel", lambda d: MockModel(d))

        rows = [{"id": 1}, {"id": 2}]
        models = mapper.map_all_to_model(rows, "MockModel")

        assert len(models) == 2
        assert all(isinstance(m, MockModel) for m in models)

    def test_map_to_model_not_registered_raises_keyerror(self):
        mapper = ResultMapper()
        with pytest.raises(KeyError) as exc_info:
            mapper.map_to_model({"id": 1}, "MissingModel")
        assert "MissingModel" in str(exc_info.value)

    def test_map_all_to_model_propagates_keyerror(self):
        mapper = ResultMapper()
        with pytest.raises(KeyError):
            mapper.map_all_to_model([{"id": 1}], "MissingModel")

    def test_map_bool_string_values(self):
        mapper = ResultMapper()
        row = {"flag_true": "true", "flag_false": "false", "flag_1": "1", "flag_0": "0"}
        schema = [
            {"column": "flag_true", "type": "bool"},
            {"column": "flag_false", "type": "bool"},
            {"column": "flag_1", "type": "bool"},
            {"column": "flag_0", "type": "bool"},
        ]

        result = mapper.map(row, schema)
        assert result["flag_true"] is True
        assert result["flag_false"] is False
        assert result["flag_1"] is True
        assert result["flag_0"] is False

    def test_map_conversion_error_keeps_original_value(self):
        mapper = ResultMapper()
        row = {"value": "not_an_int"}
        schema = [{"column": "value", "type": "int"}]

        result = mapper.map(row, schema)
        assert result["value"] == "not_an_int"


class TestModuleFunctions:
    def test_map_result(self):
        row = {"id": "42"}
        schema = [{"column": "id", "type": "int"}]

        result = map_result(row, schema)
        assert result["id"] == 42

    def test_map_results(self):
        rows = [{"id": "1"}, {"id": "2"}]
        schema = [{"column": "id", "type": "int"}]

        results = map_results(rows, schema)
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2

    def test_register_type_converter(self):
        from pt_snap_cli.query.mapper import _default_mapper

        register_type_converter("test_type", str.upper)

        row = {"value": "hello"}
        schema = [{"column": "value", "type": "test_type"}]

        result = _default_mapper.map(row, schema)
        assert result["value"] == "HELLO"

    def test_register_model_factory(self):
        from pt_snap_cli.query.mapper import _default_mapper

        class TestModel:
            def __init__(self, data):
                self.value = data["value"]

        register_model_factory("TestModel", lambda d: TestModel(d))

        model = _default_mapper.map_to_model({"value": "test"}, "TestModel")

        assert isinstance(model, TestModel)
        assert model.value == "test"
