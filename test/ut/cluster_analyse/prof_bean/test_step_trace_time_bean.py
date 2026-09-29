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

from msprof_analyze.cluster_analyse.prof_bean.step_trace_time_bean import StepTraceTimeBean


class TestStepTraceTimeBean(unittest.TestCase):

    def test(self):
        data = {"Step": 0, "Attr1": 1, "Attr2": 2}
        bean = StepTraceTimeBean(data)
        self.assertEqual(bean.row, [1.0, 2.0])
        self.assertEqual(bean.step, 0)
        self.assertEqual(bean.all_headers, ['Step', 'Type', 'Index', 'Attr1', 'Attr2'])
