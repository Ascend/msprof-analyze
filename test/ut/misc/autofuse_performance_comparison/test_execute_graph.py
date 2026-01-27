# Copyright (c) 2026, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import mock
import unittest
import sys
from unittest.mock import patch, MagicMock

mock_torch = mock.Mock()
mock_torch_npu = mock.Mock()
sys.modules["torch"] = mock_torch
sys.modules["torch_npu"] = mock_torch_npu
from misc.autofuse_performance_comparison.autofuse_core.execute_graph import Autofuse


class TestExecuteGraph(unittest.TestCase):
    def setUp(self):
        self.mock_params = MagicMock()
        self.mock_params.whole_graph = "/path/to/graph"
        self.mock_params.subgraph_dir = "/path/to/subgraph"
        self.mock_params.dump_path = "/path/to/dump"
        self.mock_params.output_path = "/path/to/output"

    @patch('misc.autofuse_performance_comparison.autofuse_core.execute_graph.importlib')
    def test_execute_graph_should_raise_error_when_module_not_found(self, mock_importlib):
        mock_importlib.import_module.side_effect = ModuleNotFoundError("ExecuteGraph_C not found")
        with self.assertRaises(ModuleNotFoundError):
            Autofuse(self.mock_params).run()

    @patch('misc.autofuse_performance_comparison.autofuse_core.execute_graph.FileManager.read_json_file')
    def test_get_ops_should_return_ops_when_json_file_exists(self, mock_read_json):
        mock_data = {
            "graph": [
                {
                    "op": [
                        {"name": "op1"},
                        {"name": "op2"}
                    ]
                },
                {
                    "op": [
                        {"name": "op1"},
                        {"name": "op2"},
                        {"name": "op3"}
                    ]
                }
            ]
        }
        mock_read_json.return_value = mock_data
        result = Autofuse.get_ops("test.json")
        expected_result = [{"name": "op1"}, {"name": "op2"}, {"name": "op3"}]
        self.assertEqual(result, expected_result)
        mock_read_json.assert_called_once_with("test.json")

    @patch('misc.autofuse_performance_comparison.autofuse_core.execute_graph.FileManager.read_json_file')
    def test_get_ops_should_return_raise_error_when_key_not_exists(self, mock_read_json):
        mock_data = {
            "model": [
                {
                    "op": [
                        {"name": "op1"},
                        {"name": "op2"}
                    ]
                },
                {
                    "op": [
                        {"name": "op1"},
                        {"name": "op2"},
                        {"name": "op3"}
                    ]
                }
            ]
        }
        mock_read_json.return_value = mock_data
        with self.assertRaises(KeyError):
            result = Autofuse.get_ops("test.json")

    @patch('misc.autofuse_performance_comparison.autofuse_core.execute_graph.importlib')
    def test_extract_value_should_record_input_shape_and_dtype(self, mock_importlib):
        mock_importlib.import_module.return_value = MagicMock()
        op = {
            "name": "autofuse_pointwise_0_Abs_Add",
            "input_desc": [
                {
                    "shape": {
                        "dim": [48]
                    },
                    "dtype": "DT_FLOAT16"
                }
            ]
        }
        test_obj = Autofuse(self.mock_params)
        test_obj.extract_value(op)
        expected_result = {
            "autofuse_pointwise_0_Abs_Add": {
                "inputs_shape": [[48]],
                "inputs_dtype": [1],
                "inputs_data_path": [],
                "outputs_data_path": []
            }
        }
        self.assertEqual(test_obj.fused_ops, expected_result)

    @patch('misc.autofuse_performance_comparison.autofuse_core.execute_graph.importlib')
    def test_extract_value_should_be_empty_when_key_not_exists(self, mock_importlib):
        mock_importlib.import_module.return_value = MagicMock()
        op = {
            "name": "autofuse_pointwise_0_Abs_Add",
            "InputDesc": [
                {
                    "shape": {
                        "dim": [48]
                    },
                    "dtype": "DT_FLOAT16"
                }
            ]
        }
        test_obj = Autofuse(self.mock_params)
        test_obj.extract_value(op)
        expected_result = {
            "autofuse_pointwise_0_Abs_Add": {
                "inputs_shape": [],
                "inputs_dtype": [],
                "inputs_data_path": [],
                "outputs_data_path": []
            }
        }
        self.assertEqual(test_obj.fused_ops, expected_result)

if __name__ == '__main__':
    unittest.main()