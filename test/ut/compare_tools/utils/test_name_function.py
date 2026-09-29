# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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
import unittest

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.utils.name_function import NameFunction
from msprof_analyze.compare_tools.compare_backend.utils.torch_op_node import TorchOpNode


class Args:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


args = {"op_name_map": {}, "use_input_shape": True}
args = Args(**args)
func = NameFunction(args)


class TestNameFunction(unittest.TestCase):
    node = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.node = TorchOpNode(event=TraceEventBean(
            {"pid": 0, "tid": 0, "args": {"Input Dims": [[1, 1], [1, 1]], "name": 0}, "ts": 0, "dur": 1, "ph": "M",
             "name": "process_name"}))

    def test_get_name(self):
        self.assertEqual(NameFunction.get_name(self.node), "process_name")

    def test_get_full_name(self):
        self.assertEqual(NameFunction.get_full_name(self.node), "process_name1,1;\r\n1,1")

    def test_get_name_function(self):
        self.assertEqual(func.get_name_func(), func.get_full_map_name)

    def test_get_map_name(self):
        self.assertEqual(func.get_map_name(self.node), "process_name")

    def test_get_full_map_name(self):
        self.assertEqual(func.get_full_map_name(self.node), "process_name1,1;\r\n1,1")
