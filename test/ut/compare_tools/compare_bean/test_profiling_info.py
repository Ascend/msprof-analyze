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

from msprof_analyze.compare_tools.compare_backend.compare_bean.profiling_info import ProfilingInfo


class TestProfilingInfo(unittest.TestCase):
    def test_calculate_schedule_time(self):
        info = ProfilingInfo("NPU")
        info.e2e_time = 10
        info.compute_time = 5
        info.communication_not_overlapped = 3
        info.calculate_schedule_time()
        self.assertEqual(info.scheduling_time, 2)

    def test_update_fa_fwd_info(self):
        info = ProfilingInfo("NPU")
        info.fa_time_fwd_cube = 5
        info.fa_time_fwd_vector = 5
        info.fa_num_fwd_cube = 1
        info.fa_num_fwd_vector = 1
        self.assertEqual(info.fa_time_fwd, 0.01)
        self.assertEqual(info.fa_num_fwd, 2)

    def test_update_fa_bwd_info(self):
        info = ProfilingInfo("NPU")
        info.fa_time_bwd_cube = 5
        info.fa_time_bwd_vector = 5
        info.fa_num_bwd_cube = 1
        info.fa_num_bwd_vector = 1
        self.assertEqual(info.fa_time_bwd, 0.01)
        self.assertEqual(info.fa_num_bwd, 2)

    def test_update_sdma_info(self):
        info = ProfilingInfo("NPU")
        info.sdma_time_tensor_move = 5
        info.sdma_time_stream = 5
        info.sdma_num_tensor_move = 5
        info.sdma_num_stream = 5
        self.assertEqual(info.sdma_time, 0.01)
        self.assertEqual(info.sdma_num, 10)

    def test_update_cube_info(self):
        info = ProfilingInfo("NPU")
        info.matmul_time_cube = 1
        info.matmul_time_vector = 1
        info.other_cube_time = 1
        info.matmul_num_cube = 5
        info.matmul_num_vector = 5
        info.other_cube_num = 5
        self.assertEqual(info.cube_time, 0.003)
        self.assertEqual(info.cube_num, 15)

    def test_update_vec_info(self):
        info = ProfilingInfo("NPU")
        info.vector_time_trans = 1
        info.vector_time_notrans = 1
        info.vector_num_trans = 2
        info.vector_num_notrans = 2
        self.assertEqual(info.vec_time, 0.002)
        self.assertEqual(info.vec_num, 4)

    def test_set_compute_time(self):
        info = ProfilingInfo("NPU")
        info.update_compute_time(1)
        info.set_compute_time(5)
        self.assertEqual(info.compute_time, 5)

    def test_update_compute_time(self):
        info = ProfilingInfo("NPU")
        info.update_compute_time(5)
        info.update_compute_time(5)
        self.assertEqual(info.compute_time, 10)

    def test_set_e2e_time(self):
        info = ProfilingInfo("NPU")
        info.set_e2e_time(5)
        self.assertEqual(info.e2e_time, 5)

    def test_set_comm_not_overlap(self):
        info = ProfilingInfo("NPU")
        info.update_comm_not_overlap(10)
        info.set_comm_not_overlap(5)
        self.assertEqual(info.communication_not_overlapped, 5)

    def test_update_comm_not_overlap(self):
        info = ProfilingInfo("NPU")
        info.update_comm_not_overlap(5)
        info.update_comm_not_overlap(5)
        self.assertEqual(info.communication_not_overlapped, 10)

    def test_set_memory_used(self):
        info = ProfilingInfo("NPU")
        info.set_memory_used(10)
        self.assertEqual(info.memory_used, 10)

    def test_is_not_minimal_profiling(self):
        info = ProfilingInfo("GPU")
        info.minimal_profiling = False
        self.assertFalse(info.is_not_minimal_profiling())
        info = ProfilingInfo("NPU")
        info.minimal_profiling = True
        self.assertFalse(info.is_not_minimal_profiling())
        info.minimal_profiling = False
        self.assertTrue(info.is_not_minimal_profiling())
