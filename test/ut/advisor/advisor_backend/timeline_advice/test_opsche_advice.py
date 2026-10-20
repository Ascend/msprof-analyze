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
import os
import unittest

from msprof_analyze.advisor.advisor_backend.interface import Interface


class TestOpScheAdvice(unittest.TestCase):
    interface = None

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        TestOpScheAdvice.interface = Interface(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                            "trace_view.json"))

    def test_run(self):
        dataset = TestOpScheAdvice.interface.get_data('timeline', 'op_schedule')
        case_advice = dataset.get('advice')
        case_bottleneck = dataset.get('bottleneck')
        case_data = dataset.get('data')
        self.assertEqual(201, len(case_advice))
        self.assertEqual(54, len(case_bottleneck))
        self.assertEqual(2, len(case_data))
        self.assertEqual(274, len(case_data[0]))
        self.assertEqual(274, len(case_data[1]))
