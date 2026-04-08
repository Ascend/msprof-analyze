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
from unittest.mock import patch

from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant, PerfColor
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.op_perf import OpPerf
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.op_perf import VecOpPerf
from msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.op_perf import CubeOpPerf


class TestOpPerf(unittest.TestCase):
    @staticmethod
    def build_op_perf_row() -> dict:
        return {
            "Model Name": "msprof_model",
            "Model ID": 1,
            "Task ID": 2,
            "Stream ID": 3,
            "Infer ID": 4,
            "Name": "op",
            "Type": "Dummy",
            "Accelerator Core": "AIV",
            "Start Time(us)": 100,
            "Duration(us)": 50,
            "Wait Time(us)": 0,
            "Block Num": 1,
            "Mix Block Num": 1,
            "HF32 Eligible": False,
            "Input Shapes": '"2,3;4,5"',  # two shapes
            "Input Data Types": '"float32;int32"',  # two dtypes
            "Input Formats": "",
            "Output Shapes": '"2,3"',  # single shape
            "Output Data Types": '"float32"',  # single dtype
            "Output Formats": "",
            "Context ID": 0,
            "aicore_time(us)": 0,
            "aic_total_cycles": 0,
            "aic_mac_time(us)": 0,
            "aic_mac_ratio": 0.0,
            "aic_scalar_time(us)": 0,
            "aic_scalar_ratio": 0.0,
            "aic_mte1_time(us)": 0,
            "aic_mte1_ratio": 0.0,
            "aic_mte2_time(us)": 0,
            "aic_mte2_ratio": 0.0,
            "aic_fixpipe_time(us)": 0,
            "aic_fixpipe_ratio": 0.0,
            "aic_icache_miss_rate": 0.0,
            "aiv_time(us)": 0,
            "aiv_total_cycles": 0,
            "aiv_vec_time(us)": 0,
            "aiv_vec_ratio": 0.0,
            "aiv_scalar_time(us)": 0,
            "aiv_scalar_ratio": 0.0,
            "aiv_mte2_time(us)": 0,
            "aiv_mte2_ratio": 0.0,
            "aiv_mte3_time(us)": 0,
            "aiv_mte3_ratio": 0.0,
            "aiv_icache_miss_rate": 0.0,
            "cube_utilization( %)": 0.0,
        }

    def test_get_size_shape_lt_dtypes_pads_and_counts(self):
        op = OpPerf(self.build_op_perf_row())
        # Use one shape, two dtypes -> pads one (1,)
        size = op.get_size('"2,3"', '"float32;int32"')
        # elements: (2*3)=6 with float32, and (1) with int32
        expected = 6 * Constant.DTYPE_SIZE_MAP["float32"] + 1 * Constant.DTYPE_SIZE_MAP["int32"]
        self.assertEqual(size, expected)

    def test_get_size_shapes_gt_dtypes_returns_zero(self):
        op = OpPerf(self.build_op_perf_row())
        with patch("msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.op_perf.logger") as mock_logger:
            size = op.get_size('"2,3;4,5"', '"float32"')
            self.assertEqual(size, 0)
            mock_logger.error.assert_called()

    def test_get_calc_size_missing_tensors_returns_zero(self):
        row = self.build_op_perf_row()
        row["Input Shapes"] = ""
        row["Output Shapes"] = ""
        op = OpPerf(row)
        with patch("msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.op_perf.logger") as mock_logger:
            self.assertEqual(op.get_calc_size(), 0)
            mock_logger.error.assert_called()

    def test_get_calc_size_computes(self):
        op = OpPerf(self.build_op_perf_row())
        calc_mb = op.get_calc_size()
        # compute expected using get_size sums divided by 1024^2
        input_size = op.get_size(op.input_shapes, op.input_data_types)
        output_size = op.get_size(op.output_shapes, op.output_data_types)
        expected = (input_size + output_size) / (Constant.BYTE_UNIT_TRANS * Constant.BYTE_UNIT_TRANS)
        self.assertAlmostEqual(calc_mb, expected, places=6)

    def test_get_throughput_no_duration_returns_zero(self):
        row = self.build_op_perf_row()
        row["Duration(us)"] = 0
        # need Constant.TITLE.SIZE in row for throughput formula, but with 0 duration returns 0 early
        row[Constant.TITLE.SIZE] = 0
        op = OpPerf(row)
        with patch("msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.op_perf.logger") as mock_logger:
            self.assertEqual(op.get_throughput(), 0)
            mock_logger.error.assert_called()

    def test_vec_perf_color_logic(self):
        # WHITE when throughput==0
        row = self.build_op_perf_row()
        row[Constant.TITLE.THROUGHPUT] = 0
        row["Duration(us)"] = 100000  # >20 us
        vec = VecOpPerf(row)
        self.assertEqual(vec.get_perf_color(), PerfColor.WHITE)

        # RED when throughput < tp/2 and duration > 20
        row = self.build_op_perf_row()
        row[Constant.TITLE.THROUGHPUT] = Constant.TP_THRESHOLD / 3
        row["Duration(us)"] = 100000
        vec = VecOpPerf(row)
        self.assertEqual(vec.get_perf_color(), PerfColor.RED)

        # YELLOW when tp/2 <= throughput < tp
        row = self.build_op_perf_row()
        row[Constant.TITLE.THROUGHPUT] = (Constant.TP_THRESHOLD * 3) / 4
        row["Duration(us)"] = 100000
        vec = VecOpPerf(row)
        self.assertEqual(vec.get_perf_color(), PerfColor.YELLOW)

        # GREEN otherwise
        row = self.build_op_perf_row()
        row[Constant.TITLE.THROUGHPUT] = Constant.TP_THRESHOLD * 1.5
        row["Duration(us)"] = 100000
        vec = VecOpPerf(row)
        self.assertEqual(vec.get_perf_color(), PerfColor.GREEN)

    def test_cube_perf_color_logic(self):
        row = self.build_op_perf_row()
        row["aic_mac_ratio"] = 0.0
        cube = CubeOpPerf(row)
        with patch("msprof_analyze.advisor.advisor_backend.compute_advice.npu_fused.op_perf.logger") as mock_logger:
            self.assertEqual(cube.get_perf_color(), PerfColor.WHITE)
            mock_logger.warning.assert_called()

        # RED when < 0.6
        row = self.build_op_perf_row()
        row["aic_mac_ratio"] = 0.5
        cube = CubeOpPerf(row)
        self.assertEqual(cube.get_perf_color(), PerfColor.RED)

        # YELLOW when [0.6, 0.8)
        row = self.build_op_perf_row()
        row["aic_mac_ratio"] = 0.6
        cube = CubeOpPerf(row)
        self.assertEqual(cube.get_perf_color(), PerfColor.YELLOW)

        # GREEN when >= 0.8
        row = self.build_op_perf_row()
        row["aic_mac_ratio"] = 0.85
        cube = CubeOpPerf(row)
        self.assertEqual(cube.get_perf_color(), PerfColor.GREEN)


if __name__ == "__main__":
    unittest.main()

