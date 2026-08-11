# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
import unittest
from unittest.mock import MagicMock, patch

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.hccl_op_bean import \
    HcclOpBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.kernel_bean import \
    KernelBean
from msprof_analyze.compare_tools.compare_backend.profiling_parser.overall_metrics_parser import \
    OverallMetricsParser, Event
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.framework_api_bean import \
    FrameworkApiBean

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.hccl_task_bean import \
    HcclTaskBean


class TestOverallMetricsParser(unittest.TestCase):
    def setUp(self):
        self.mock_npu_parser = MagicMock()
        self.mock_npu_parser.step_range = None
        self.mock_npu_parser.cursor = MagicMock()
        self.setup_mock_data()
        self.parser = OverallMetricsParser(self.mock_npu_parser)

    def tearDown(self):
        self.mock_npu_parser = None
        self.parser = None

    def setup_mock_data(self):
        mock_op1 = MagicMock(spec=FrameworkApiBean)
        mock_op1.is_cpu_cube_op.return_value = True
        mock_op1.start_time = 1000
        mock_op1.end_time = 2000
        mock_op1.dur = 1000
        mock_op1.cann_connection_id = "conn1"

        mock_op2 = MagicMock(spec=FrameworkApiBean)
        mock_op2.is_cpu_cube_op.return_value = False
        mock_op2.start_time = 1500
        mock_op2.end_time = 2500
        mock_op2.dur = 1000

        self.mock_npu_parser.result_data.torch_op_data = [mock_op1, mock_op2]

        mock_kernel1 = MagicMock(spec=KernelBean)
        mock_kernel1.start_time = 1000
        mock_kernel1.end_time = 2000
        mock_kernel1.dur = 1000
        mock_kernel1.connection_id = "conn1"
        mock_kernel1.is_page_attention.return_value = False
        mock_kernel1.is_sdma.return_value = False
        mock_kernel1.is_mc2.return_value = False

        self.mock_npu_parser.compute_op_data = [mock_kernel1]

        mock_comm_op = MagicMock(spec=HcclOpBean)
        mock_comm_op.start_time = 1500
        mock_comm_op.end_time = 2500
        mock_comm_op.dur = 1000
        mock_comm_op.group_name = "group1"
        mock_comm_op.is_lccl.return_value = False

        self.mock_npu_parser.comm_op_data = [mock_comm_op]

        mock_task = MagicMock()
        mock_task.task_id = "task1"
        mock_task.group_name = "group1"
        mock_task.plane_id = 1
        mock_task.name = "Notify_Wait"
        mock_task.start_time = 1500
        mock_task.end_time = 2500
        mock_task.dur = 1000

        self.mock_npu_parser.comm_task_data = [mock_task]

        self.mock_npu_parser.cursor.fetch_all_data.return_value = [
            {"totalReserved": 1024 ** 3},  # 1GB
            {"globalTaskId": "task1", "pmuName": "pmu1", "value": 100},
            {"task_type": "SDMA_SQE", "Duration": 1000000, "streamId": 1}
        ]

    def test_initialization(self):
        self.assertEqual(len(self.parser.cpu_cube_op), 1)
        self.assertEqual(self.parser.cpu_cube_op[0].start_time, 1000)
        self.assertEqual(len(self.parser.connect_map), 2)
        self.assertIn("conn1", self.parser.connect_map)

    def test_merge_intervals(self):
        intervals = [
            [1, 3],
            [2, 6],
            [8, 10],
            [15, 18],
            [16, 17]
        ]

        merged = self.parser.merge_intervals(intervals)

        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0], [1, 6])
        self.assertEqual(merged[1], [8, 10])
        self.assertEqual(merged[2], [15, 18])

    def test_merge_intervals_second_call_does_not_mutate_first_call_result(self):
        compute_intervals = [[1, 2], [5, 6]]
        merged_compute_intervals = self.parser.merge_intervals(compute_intervals)

        self.parser.merge_intervals(compute_intervals + [[5, 10]])

        self.assertEqual(merged_compute_intervals, [[1, 2], [5, 6]])

    def test_calculate_lccl_time(self):
        mock_lccl_op = MagicMock(spec=HcclOpBean)
        mock_lccl_op.is_lccl.return_value = True
        mock_lccl_op.dur = 500
        self.mock_npu_parser.comm_op_data.append(mock_lccl_op)
        self.parser.calculate_lccl_time()
        self.mock_npu_parser.result_data.overall_metrics.update_lccl_info.assert_called_with(500)

    def test_calculate_sdma_time(self):
        self.mock_npu_parser.cursor.fetch_all_data.return_value = [
            {"task_type": "SDMA_SQE", "Duration": 1000000, "streamId": 1},
            {"task_type": "EVENT_WAIT_SQE", "Duration": 500000, "streamId": 1}
        ]
        self.parser.calculate_sdma_time()
        self.mock_npu_parser.result_data.overall_metrics.update_sdma_stream_info.assert_called()

    def test_calculate_overlap_analysis_time(self):
        self.mock_npu_parser.compute_op_data = [
            MagicMock(start_time=1000, end_time=2000, dur=1000),
            MagicMock(start_time=1500, end_time=2500, dur=1000)
        ]
        self.mock_npu_parser.comm_op_data = [
            MagicMock(start_time=1800, end_time=2800, dur=1000)
        ]

        # Patch DBManager so calculate_ascend_task_e2e_time executes and uses merged bounds
        with (patch("msprof_analyze.compare_tools.compare_backend.profiling_parser.overall_metrics_parser.DBManager")
              as mock_db):
            mock_db.judge_table_exists.return_value = True
            # Two queries (first start, last end) return empty -> fall back to merged_op bounds
            mock_db.fetch_all_data.side_effect = [[], []]

            self.parser.calculate_overlap_analysis_time()

        metrics = self.mock_npu_parser.result_data.overall_metrics
        metrics.update_compute_time.assert_called()
        metrics.update_comm_not_overlap.assert_called()
        metrics.set_e2e_time.assert_called_with(1800.0) # merged overall bounds: [1000, 2800] -> duration 1800 us
        self.assertEqual(len(self.parser.not_overlapped_comm), 2)

    def test_calculate_communication_wait_time(self):
        mock_task1 = MagicMock(spec=HcclTaskBean)
        mock_task1.name = "RDMASend"
        mock_task1.group_name = "group1"
        mock_task1.plane_id = 1
        mock_task1.start_time = 1000
        mock_task1.end_time = 2000
        mock_task1.dur = 1000

        mock_task2 = MagicMock(spec=HcclTaskBean)
        mock_task2.name = "Notify_Wait"
        mock_task2.group_name = "group1"
        mock_task2.plane_id = 1
        mock_task2.start_time = 2000
        mock_task2.end_time = 3000
        mock_task2.dur = 1000

        self.mock_npu_parser.comm_task_data = [mock_task1, mock_task2]
        self.parser.not_overlapped_comm = [Event(1500, 2500)]
        self.parser.calculate_communication_wait_time()
        self.mock_npu_parser.result_data.overall_metrics.update_communication_group_time.assert_called()

    def test_calculate_uncovered_communication_overlap_time(self):
        mock_comm1 = MagicMock()
        mock_comm1.group_name = "group1"
        mock_comm1.start_time = 1000
        mock_comm1.end_time = 2000

        mock_comm2 = MagicMock()
        mock_comm2.group_name = "group2"
        mock_comm2.start_time = 1500
        mock_comm2.end_time = 2500

        self.mock_npu_parser.comm_op_data = [mock_comm1, mock_comm2]
        self.parser.not_overlapped_comm = [Event(1200, 2200)]
        self.parser.calculate_uncovered_communication_overlap_time()
        self.mock_npu_parser.result_data.overall_metrics.update_communication_overlap_time.assert_called()

    def test_update_overall_metrics(self):
        with patch.object(self.parser, 'calculate_memory_usage_peak') as mock_mem, \
                patch.object(self.parser, 'calculate_computing_time') as mock_comp, \
                patch.object(self.parser, 'calculate_lccl_time') as mock_lccl, \
                patch.object(self.parser, 'calculate_sdma_time') as mock_sdma, \
                patch.object(self.parser, 'calculate_overlap_analysis_time') as mock_overlap, \
                patch.object(self.parser, 'calculate_communication_wait_time') as mock_comm_wait, \
                patch.object(self.parser, 'calculate_uncovered_communication_overlap_time') as mock_uncovered:
            self.parser.update_overall_metrics()

            mock_mem.assert_called_once()
            mock_comp.assert_called_once()
            mock_lccl.assert_called_once()
            mock_sdma.assert_called_once()
            mock_overlap.assert_called_once()
            mock_comm_wait.assert_called_once()
            mock_uncovered.assert_called_once()

            metrics = self.mock_npu_parser.result_data.overall_metrics
            metrics.calculate_schedule_time.assert_called_once()
            metrics.trans_time_to_s.assert_called_once()
            metrics.calculate_other_time.assert_called_once()

    def test_c_core_sqe_list_without_step_range(self):
        """Test c_core_sqe_list property without step_range"""
        # Setup no step_range
        self.mock_npu_parser.step_range = None
        self.parser._c_core_sqe_list = None

        # Mock database response
        mock_data = [
            {"Duration": 1000000, "startNs": 1000, "endNs": 2000}
        ]

        # Verify database query was called without step_range
        expected_sql = """
        SELECT
            round(TASK.endNs - TASK.startNs) AS "Duration",
            TASK.startNs AS "startNs",
            TASK.endNs AS "endNs"
        FROM
            TASK LEFT JOIN STRING_IDS ON TASK.taskType == STRING_IDS.id
        WHERE STRING_IDS.value == 'C_CORE_SQE'
        ORDER BY TASK.startNs
        """

        with patch("msprof_analyze.compare_tools.compare_backend.profiling_parser.overall_metrics_parser."
                   "DBManager") as mock_db_manager:
            mock_db_manager.fetch_all_data.return_value = mock_data
            result = self.parser.c_core_sqe_list
            mock_db_manager.fetch_all_data.assert_called_with(self.mock_npu_parser.cursor, expected_sql)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]._data["Duration"], 1000000)

    def test_categorize_computing_performance_data_page_attention(self):
        """Test categorize_computing_performance_data for page attention kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = True
        mock_kernel.dur = 500

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_page_attention_info.assert_called_with(500)

    def test_categorize_computing_performance_data_sdma(self):
        """Test categorize_computing_performance_data for SDMA kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = True
        mock_kernel.dur = 300

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_sdma_tensor_move_info.assert_called_with(300)

    def test_categorize_computing_performance_data_mc2(self):
        """Test categorize_computing_performance_data for MC2 kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = True
        mock_kernel.name = "mc2_kernel"
        mock_kernel.dur = 400
        mock_kernel.mc2_computing_time.return_value = 200

        with patch.object(self.parser, 'calculate_mc2_communication_time', return_value=200) as mock_comm_time:
            self.parser.categorize_computing_performance_data(mock_kernel)

            mock_comm_time.assert_called_with(mock_kernel)
            mock_kernel.mc2_computing_time.assert_called_with(self.parser.pmu_data)
            self.mock_npu_parser.result_data.overall_metrics.update_mc2_info.assert_called_with(
                "mc2_kernel", 400, 200, 200)

    def test_categorize_computing_performance_data_flash_attention_fwd(self):
        """Test categorize_computing_performance_data for Flash Attention forward kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "unknown_conn"
        mock_kernel.is_flash_attention.return_value = True
        mock_kernel.is_fa_bwd.return_value = False
        mock_kernel.dur = 600

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_fa_fwd_cube_info.assert_called_with(600)

    def test_categorize_computing_performance_data_flash_attention_bwd(self):
        """Test categorize_computing_performance_data for Flash Attention backward kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "unknown_conn"
        mock_kernel.is_flash_attention.return_value = True
        mock_kernel.is_fa_bwd.return_value = True
        mock_kernel.dur = 700

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_fa_bwd_cube_info.assert_called_with(700)

    def test_categorize_computing_performance_data_conv_fwd(self):
        """Test categorize_computing_performance_data for Convolution forward kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "unknown_conn"
        mock_kernel.is_flash_attention.return_value = False
        mock_kernel.is_conv.return_value = True
        mock_kernel.is_conv_bwd.return_value = False
        mock_kernel.dur = 800

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_conv_fwd_cube_info.assert_called_with(800)

    def test_categorize_computing_performance_data_conv_bwd(self):
        """Test categorize_computing_performance_data for Convolution backward kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "unknown_conn"
        mock_kernel.is_flash_attention.return_value = False
        mock_kernel.is_conv.return_value = True
        mock_kernel.is_conv_bwd.return_value = True
        mock_kernel.dur = 900

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_conv_bwd_cube_info.assert_called_with(900)

    def test_categorize_computing_performance_data_matmul(self):
        """Test categorize_computing_performance_data for MatMul kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "unknown_conn"
        mock_kernel.is_flash_attention.return_value = False
        mock_kernel.is_conv.return_value = False
        mock_kernel.is_matmul.return_value = True
        mock_kernel.dur = 1000

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_matmul_cube_info.assert_called_with(1000)

    def test_categorize_computing_performance_data_cube_kernel(self):
        """Test categorize_computing_performance_data for cube kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "unknown_conn"
        mock_kernel.is_flash_attention.return_value = False
        mock_kernel.is_conv.return_value = False
        mock_kernel.is_matmul.return_value = False
        mock_kernel.is_cube_kernel_cat.return_value = True
        mock_kernel.dur = 1100

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_other_cube_info.assert_called_with(1100)

    def test_categorize_computing_performance_data_trans(self):
        """Test categorize_computing_performance_data for trans kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "unknown_conn"
        mock_kernel.is_flash_attention.return_value = False
        mock_kernel.is_conv.return_value = False
        mock_kernel.is_matmul.return_value = False
        mock_kernel.is_cube_kernel_cat.return_value = False
        mock_kernel.is_trans.return_value = True
        mock_kernel.dur = 1200

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_vector_trans_info.assert_called_with(1200)

    def test_categorize_computing_performance_data_vector_notrans(self):
        """Test categorize_computing_performance_data for vector non-trans kernel"""
        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "unknown_conn"
        mock_kernel.is_flash_attention.return_value = False
        mock_kernel.is_conv.return_value = False
        mock_kernel.is_matmul.return_value = False
        mock_kernel.is_cube_kernel_cat.return_value = False
        mock_kernel.is_trans.return_value = False
        mock_kernel.dur = 1300

        self.parser.categorize_computing_performance_data(mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_vector_notrans_info.assert_called_with(1300)

    def test_categorize_computing_performance_data_with_connection(self):
        """Test categorize_computing_performance_data with valid connection"""
        # Setup connection map
        self.parser.connect_map["conn1"] = 1000

        # Setup CPU cube op that matches the flow
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.start_time = 1000
        mock_cpu_op.end_time = 2000
        self.parser.cpu_cube_op = [mock_cpu_op]

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "conn1"
        mock_kernel.dur = 1400

        with patch.object(self.parser, 'categorize_cube_performance_data') as mock_categorize:
            self.parser.categorize_computing_performance_data(mock_kernel)
            mock_categorize.assert_called_with(mock_cpu_op, mock_kernel)

    def test_categorize_computing_performance_data_with_connection_no_match(self):
        """Test categorize_computing_performance_data with connection but no matching CPU op"""
        # Setup connection map
        self.parser.connect_map["conn1"] = 1000

        # Setup CPU cube op that doesn't match the flow
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.start_time = 2000  # After flow start time
        mock_cpu_op.end_time = 3000
        self.parser.cpu_cube_op = [mock_cpu_op]

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_page_attention.return_value = False
        mock_kernel.is_sdma.return_value = False
        mock_kernel.is_mc2.return_value = False
        mock_kernel.connection_id = "conn1"
        mock_kernel.is_flash_attention.return_value = False
        mock_kernel.is_conv.return_value = False
        mock_kernel.is_conv.return_value = False
        mock_kernel.is_matmul.return_value = False
        mock_kernel.is_cube_kernel_cat.return_value = False
        mock_kernel.is_trans.return_value = False
        mock_kernel.dur = 1500

        with patch.object(self.parser, 'categorize_cube_performance_data') as mock_categorize:
            self.parser.categorize_computing_performance_data(mock_kernel)
            mock_categorize.assert_not_called()

    def test_categorize_cube_performance_data_fa_fwd_cube(self):
        """Test categorize_cube_performance_data for FA forward cube"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = True
        mock_cpu_op.is_bwd_for_cpu_op.return_value = False

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = True
        mock_kernel.dur = 1600

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_fa_fwd_cube_info.assert_called_with(1600)

    def test_categorize_cube_performance_data_fa_fwd_vector(self):
        """Test categorize_cube_performance_data for FA forward vector"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = True
        mock_cpu_op.is_bwd_for_cpu_op.return_value = False

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = False
        mock_kernel.dur = 1700

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_fa_fwd_vector_info.assert_called_with(1700)

    def test_categorize_cube_performance_data_fa_bwd_cube(self):
        """Test categorize_cube_performance_data for FA backward cube"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = True
        mock_cpu_op.is_bwd_for_cpu_op.return_value = True

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = True
        mock_kernel.dur = 1800

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_fa_bwd_cube_info.assert_called_with(1800)

    def test_categorize_cube_performance_data_fa_bwd_vector(self):
        """Test categorize_cube_performance_data for FA backward vector"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = True
        mock_cpu_op.is_bwd_for_cpu_op.return_value = True

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = False
        mock_kernel.dur = 1900

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_fa_bwd_vector_info.assert_called_with(1900)

    def test_categorize_cube_performance_data_conv_fwd_cube(self):
        """Test categorize_cube_performance_data for Conv forward cube"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = False
        mock_cpu_op.is_conv_for_cpu_op.return_value = True
        mock_cpu_op.is_bwd_for_cpu_op.return_value = False

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = True
        mock_kernel.dur = 2000

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_conv_fwd_cube_info.assert_called_with(2000)

    def test_categorize_cube_performance_data_conv_fwd_vector(self):
        """Test categorize_cube_performance_data for Conv forward vector"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = False
        mock_cpu_op.is_conv_for_cpu_op.return_value = True
        mock_cpu_op.is_bwd_for_cpu_op.return_value = False

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = False
        mock_kernel.dur = 2100

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_conv_fwd_vector_info.assert_called_with(2100)

    def test_categorize_cube_performance_data_conv_bwd_cube(self):
        """Test categorize_cube_performance_data for Conv backward cube"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = False
        mock_cpu_op.is_conv_for_cpu_op.return_value = True
        mock_cpu_op.is_bwd_for_cpu_op.return_value = True

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = True
        mock_kernel.dur = 2200

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_conv_bwd_cube_info.assert_called_with(2200)

    def test_categorize_cube_performance_data_conv_bwd_vector(self):
        """Test categorize_cube_performance_data for Conv backward vector"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = False
        mock_cpu_op.is_conv_for_cpu_op.return_value = True

        self.mock_npu_parser.is_backward.return_value = True

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = False
        mock_kernel.dur = 2300

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_conv_bwd_vector_info.assert_called_with(2300)

    def test_categorize_cube_performance_data_matmul_cube(self):
        """Test categorize_cube_performance_data for MatMul cube"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = False
        mock_cpu_op.is_conv_for_cpu_op.return_value = False
        mock_cpu_op.is_matmul_for_cpu_op.return_value = True

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = True
        mock_kernel.dur = 2400

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_matmul_cube_info.assert_called_with(2400)

    def test_categorize_cube_performance_data_matmul_vector(self):
        """Test categorize_cube_performance_data for MatMul vector"""
        mock_cpu_op = MagicMock(spec=FrameworkApiBean)
        mock_cpu_op.is_fa_for_cpu_op.return_value = False
        mock_cpu_op.is_conv_for_cpu_op.return_value = False
        mock_cpu_op.is_matmul_for_cpu_op.return_value = True

        mock_kernel = MagicMock(spec=KernelBean)
        mock_kernel.is_cube_kernel_cat.return_value = False
        mock_kernel.dur = 2500

        self.parser.categorize_cube_performance_data(mock_cpu_op, mock_kernel)

        self.mock_npu_parser.result_data.overall_metrics.update_matmul_vector_info.assert_called_with(2500)

    def test_calculate_mc2_communication_time(self):
        """Test calculate_mc2_communication_time method"""
        # Setup C_CORE_SQE data
        mock_sqe1 = MagicMock()
        mock_sqe1.end_time = 1000
        mock_sqe2 = MagicMock()
        mock_sqe2.end_time = 2000
        mock_sqe3 = MagicMock()
        mock_sqe3.end_time = 3000

        self.parser._c_core_sqe_list = [mock_sqe1, mock_sqe2, mock_sqe3]
        self.parser._c_core_sqe_index = 0

        # Setup kernel
        mock_kernel = MagicMock()
        mock_kernel.start_time = 500
        mock_kernel.end_time = 3500

        result = self.parser.calculate_mc2_communication_time(mock_kernel)

        # Communication time should be (2000 - 1000)
        self.assertEqual(result, 1000.0)
        self.assertEqual(self.parser._c_core_sqe_index, 3)

    def test_calculate_ascend_task_e2e_time(self):
        """Test calculate_ascend_task_e2e_time computes E2E using TASK bounds when available"""
        # Prepare DB responses: earliest start at 1,500,000 ns (1500 us), latest end at 9,000,000 ns (9000 us)
        first_task_rows = [{"startNs": 1500000}]
        last_task_rows = [{"endNs": 9000000}]

        with (patch("msprof_analyze.compare_tools.compare_backend.profiling_parser.overall_metrics_parser.DBManager")
              as mock_db):
            # Table exists
            mock_db.judge_table_exists.return_value = True
            # fetch_all_data called twice: first for first task, then for last task
            mock_db.fetch_all_data.side_effect = [first_task_rows, last_task_rows]

            # Call with merged op bounds [2000us, 8000us]
            self.parser.calculate_ascend_task_e2e_time(merged_op_earliest_start=2000, merged_op_latest_end=8000)

            # Expect E2E = 9000 - 1500 = 7500 us
            self.mock_npu_parser.result_data.overall_metrics.set_e2e_time.assert_called_with(7500.0)
