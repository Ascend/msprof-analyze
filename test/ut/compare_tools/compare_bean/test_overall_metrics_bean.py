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
from msprof_analyze.compare_tools.compare_backend.compare_bean.overall_metrics_bean import OverallMetricsBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.profiling_info import ProfilingInfo
from msprof_analyze.prof_common.constant import Constant


class TestOverallMetricsBean(unittest.TestCase):

    def test_rows_should_calculate_successfully(self):
        base_info = ProfilingInfo("pytorch")
        base_info.update_mc2_info("allReduceMatMul", 10, 4, 4)
        base_info.update_communication_group_pg_name({"default_group": "group_name_0", "mp": "group_name_41"})
        base_info.update_communication_group_time({
            "default_group": {
                Constant.WAIT_TIME: 0.1,
                Constant.TRANSMIT_TIME: 0.2
            },
            "mp": {
                Constant.WAIT_TIME: 0.3,
                Constant.TRANSMIT_TIME: 0.4
            }
        })
        comparison_info = ProfilingInfo("pytorch")
        comparison_info.update_mc2_info("allReduceMatMulV2", 9, 5, 5)
        comparison_info.update_communication_group_pg_name({"default_group": "group_name_0", "dp_cp": "group_name_17"})
        comparison_info.update_communication_group_time({
            "default_group": {
                Constant.WAIT_TIME: 0.3,
                Constant.TRANSMIT_TIME: 0.4
            },
            "dp_cp": {
                Constant.WAIT_TIME: 0.5,
                Constant.TRANSMIT_TIME: 0.6
            }
        })
        bean = OverallMetricsBean(base_info, comparison_info)
        rows = bean.rows
        self.assertTrue(rows)
