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
import os

from unittest.mock import patch
from msprof_analyze.advisor.analyzer.schedule.dispatch.timeline_op_dispatch_analyzer import OpDispatchAnalyzer
from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.display.html.render import HTMLRender
from test.ut.advisor.advisor_backend.tools.tool import recover_env


class TestOperatorDispatchAnalyzer(unittest.TestCase):
    @classmethod
    def tearDownClass(cls) -> None:
        recover_env()

    @patch("msprof_analyze.prof_common.constant.Constant.MAX_OP_COMPILE_NUM", 5)
    def test_ops_dispatch_analyzer(self):
        kwargs = {"analysis_mode": "all"}
        data_root_dir = os.path.dirname(os.path.realpath(__file__))
        op_dispatch_analyzer = OpDispatchAnalyzer(data_root_dir, **kwargs)

        results = op_dispatch_analyzer.optimize(**kwargs)
        self.assertTrue(results.page_dict)
        self.assertIsNotNone(results.sheet_recorder.sheet_data.get("算子下发"))

    @patch("msprof_analyze.prof_common.constant.Constant.MAX_OP_COMPILE_NUM", 5)
    def test_ops_dispatch_make_render(self):
        kwargs = {"analysis_mode": "timeline"}
        data_root_dir = os.path.dirname(os.path.realpath(__file__))
        op_dispatch = OpDispatchAnalyzer(data_root_dir, **kwargs)
        event_dataset = op_dispatch.get_first_data_by_key(op_dispatch.dataset_list, ScheduleAnalysisDataset.get_key())

        op_dispatch.get_op_compile_info(event_dataset)
        html_render = HTMLRender()
        op_dispatch.make_render(html_render)
        self.assertTrue(len(html_render.render_list) >= 1)


if __name__ == '__main__':
    tester = TestOperatorDispatchAnalyzer()
    tester.test_ops_dispatch_analyzer()
    tester.test_ops_dispatch_make_render()
