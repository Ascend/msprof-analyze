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
from unittest.mock import MagicMock
from msprof_analyze.compare_tools.compare_backend.comparator.overall_performance_comparator \
                        import OverallPerformanceComparator
from msprof_analyze.prof_common.constant import Constant


class MockProfilingInfo:
    def __init__(self):
        self.profiling_type = ""
        self.hide_op_details = False
        self.cube_time = 0.0
        self.cube_num = 0
        self.vec_time = 0.0
        self.vec_num = 0
        self.conv_time_fwd = 0.0
        self.conv_num_fwd = 0
        self.conv_time_bwd = 0.0
        self.conv_num_bwd = 0
        self.fa_time_fwd = 0.0
        self.fa_num_fwd = 0
        self.fa_time_bwd = 0.0
        self.fa_num_bwd = 0
        self.pa_time = 0.0
        self.pa_num = 0
        self.lccl_time = 0.0
        self.lccl_num = 0
        self.other_time = 0.0
        self.compute_time = 0.0
        self.memory_used = 0.0
        self.wait_time = 0.0
        self.communication_not_overlapped = 0.0
        self.is_level0 = False
        self.rdma_bandwidth = 0.0
        self.sdma_bandwidth = 0.0
        self.sdma_time = 0.0
        self.sdma_num = 0
        self.scheduling_time = 0.0
        self.e2e_time = 0.0
        self._not_minimal_profiling = False

    def is_not_minimal_profiling(self):
        return self._not_minimal_profiling


class TestOverallPerformanceComparator(unittest.TestCase):
    def setUp(self):
        self.mock_bean = MagicMock()
        self.base_profiling_info = MockProfilingInfo()
        self.comp_profiling_info = MockProfilingInfo()
        self.base_profiling_info.profiling_type = "Base"
        self.comp_profiling_info.profiling_type = "Comparison"
        self.set_default_profiling_info_values()
        self.origin_data = {
            Constant.BASE_DATA: self.base_profiling_info,
            Constant.COMPARISON_DATA: self.comp_profiling_info
        }

    def set_default_profiling_info_values(self):
        self.base_profiling_info.hide_op_details = False
        self.comp_profiling_info.hide_op_details = False
        self.base_profiling_info.cube_time = 10.5
        self.base_profiling_info.cube_num = 100
        self.base_profiling_info.vec_time = 5.2
        self.base_profiling_info.vec_num = 50
        self.comp_profiling_info.cube_time = 9.8
        self.comp_profiling_info.cube_num = 95
        self.comp_profiling_info.vec_time = 4.9
        self.comp_profiling_info.vec_num = 48

        self.base_profiling_info.conv_time_fwd = 3.1
        self.base_profiling_info.conv_num_fwd = 20
        self.comp_profiling_info.conv_time_fwd = 2.9
        self.comp_profiling_info.conv_num_fwd = 18
        self.base_profiling_info.fa_time_fwd = 1.5
        self.base_profiling_info.fa_num_fwd = 10
        self.comp_profiling_info.fa_time_fwd = 1.3
        self.comp_profiling_info.fa_num_fwd = 8
        self.base_profiling_info.other_time = 2.0
        self.comp_profiling_info.other_time = 1.8
        self.base_profiling_info.compute_time = 25.0
        self.comp_profiling_info.compute_time = 22.0
        self.base_profiling_info.memory_used = 8.5
        self.comp_profiling_info.memory_used = 7.8
        self.base_profiling_info.wait_time = 1.2
        self.base_profiling_info.communication_not_overlapped = 1.5
        self.comp_profiling_info.wait_time = 1.0
        self.comp_profiling_info.communication_not_overlapped = 1.3
        self.comp_profiling_info.is_level0 = False

        self.base_profiling_info.rdma_bandwidth = 12.5
        self.comp_profiling_info.rdma_bandwidth = 13.2

        self.base_profiling_info.sdma_time = 0.8
        self.base_profiling_info.sdma_num = 15
        self.comp_profiling_info.sdma_time = 0.7
        self.comp_profiling_info.sdma_num = 14
        self.base_profiling_info.sdma_bandwidth = 5.5
        self.comp_profiling_info.sdma_bandwidth = 6.0

        self.base_profiling_info.scheduling_time = 0.5
        self.base_profiling_info.e2e_time = 30.0
        self.comp_profiling_info.scheduling_time = 0.4
        self.comp_profiling_info.e2e_time = 27.0

    def test_compare_normal_case(self):
        comparator = OverallPerformanceComparator(self.origin_data, self.mock_bean)
        comparator._compare()

        expected_headers = [
            '', 'Cube Time(Num)', 'Vector Time(Num)', 'Conv Time(Forward)(Num)',
            'Flash Attention Time(Forward)(Num)', 'Other Time', 'Computing Time',
            'Mem Usage', 'Uncovered Communication Time(Wait Time)', 'RDMA Bandwidth',
            'SDMA Bandwidth', 'SDMA Time(Num)', 'Free Time', 'E2E Time'
        ]
        self.assertEqual(comparator._headers, expected_headers)
        self.assertEqual(len(comparator._rows), 2)
        self.assertEqual(comparator._rows[0][0], 'Base')
        self.assertEqual(comparator._rows[1][0], 'Comparison')

    def test_compare_with_missing_optional_data(self):
        self.base_profiling_info.conv_time_fwd = 0.0
        self.comp_profiling_info.conv_time_fwd = 0.0
        self.base_profiling_info.fa_time_fwd = 0.0
        self.comp_profiling_info.fa_time_fwd = 0.0
        self.base_profiling_info.rdma_bandwidth = 0.0
        self.comp_profiling_info.rdma_bandwidth = 0.0

        comparator = OverallPerformanceComparator(self.origin_data, self.mock_bean)
        comparator._compare()
        self.assertNotIn('Conv Time(Forward)(Num)', comparator._headers)
        self.assertNotIn('Flash Attention Time(Forward)(Num)', comparator._headers)
        self.assertNotIn('RDMA Bandwidth', comparator._headers)

    def test_compare_with_backward_operations(self):
        self.base_profiling_info.conv_time_bwd = 2.5
        self.base_profiling_info.conv_num_bwd = 15
        self.comp_profiling_info.conv_time_bwd = 2.3
        self.comp_profiling_info.conv_num_bwd = 14

        self.base_profiling_info.fa_time_bwd = 1.2
        self.base_profiling_info.fa_num_bwd = 8
        self.comp_profiling_info.fa_time_bwd = 1.1
        self.comp_profiling_info.fa_num_bwd = 7

        comparator = OverallPerformanceComparator(self.origin_data, self.mock_bean)
        comparator._compare()
        self.assertIn('Conv Time(Backward)(Num)', comparator._headers)
        self.assertIn('Flash Attention Time(Backward)(Num)', comparator._headers)
