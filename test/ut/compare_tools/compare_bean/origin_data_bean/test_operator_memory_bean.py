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

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.operator_memory_bean \
    import OperatorMemoryBean


class TestOperatorMemoryBean(unittest.TestCase):
    bean1 = OperatorMemoryBean({"Name": "cann::add", "Size(KB)": 512, "Allocation Time(us)": 1, "Release Time(us)": 5})
    bean2 = OperatorMemoryBean({"Name": "aten::add", "Size(KB)": 512})

    @staticmethod
    def _get_property_str(bean: OperatorMemoryBean):
        return f"{bean.name}-{bean.size}-{bean.allocation_time}-{bean.release_time}"

    def test_property(self):
        self.assertEqual(self._get_property_str(self.bean1), "cann::add-512.0-1-5")
        self.assertEqual(self._get_property_str(self.bean2), "aten::add-512.0-0-0")

    def test_is_cann_op(self):
        self.assertTrue(self.bean1.is_cann_op())
        self.assertFalse(self.bean2.is_cann_op())
