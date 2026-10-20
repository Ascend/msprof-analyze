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

from msprof_analyze.advisor.advisor_backend.prof_bean_advisor.cluster_step_trace_time_bean \
    import ClusterStepTraceTimeBean


class TestClusterStepTraceTimeBean(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.normal_data = {
            "Step": "0", "Type": "MockType", "Index": 9, "Computing": 123.6,
            "Communication(Not Overlapped)": 12.3, "Free": 45.6
        }
        cls.abnormal_data = {
            "Step": "0", "Type": "MockType", "Index": "idx0", "Computing": "MockCommpute",
            "Communication(Not Overlapped)": "MockCommunication", "Free": "MockFree"
        }

    def test_property_normal(self):
        bean_inst = ClusterStepTraceTimeBean(self.normal_data)
        self.assertEqual(self.normal_data.get("Step"), bean_inst.step)
        self.assertEqual(self.normal_data.get("Type"), bean_inst.type)
        self.assertEqual(self.normal_data.get("Index"), bean_inst.index)
        self.assertEqual(self.normal_data.get("Computing"), bean_inst.compute)
        self.assertEqual(self.normal_data.get("Communication(Not Overlapped)"), bean_inst.communication)
        self.assertEqual(self.normal_data.get("Free"), bean_inst.free)

    def test_property_abnormal(self):
        bean_inst = ClusterStepTraceTimeBean(self.abnormal_data)
        with self.assertRaises(ValueError):
            _ = bean_inst.index
        with self.assertRaises(ValueError):
            _ = bean_inst.compute
        with self.assertRaises(ValueError):
            _ = bean_inst.communication
        with self.assertRaises(ValueError):
            _ = bean_inst.free
