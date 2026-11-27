# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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

import pandas as pd

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mbu.mbu_calculator import MBUCalculator
from msprof_analyze.prof_common.constant import Constant


class TestMBUCalculator(unittest.TestCase):
    NAMESPACE = "msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mbu.mbu_calculator."

    @staticmethod
    def _calc(peak=None):
        return MBUCalculator({Constant.PROFILER_DB_PATH: "dummy"}, peak)

    def _patch_export(self, df):
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = df
        return patch(self.NAMESPACE + "KernelBytesExport", return_value=mock_export)

    def test_init_peak_validation(self):
        self.assertIsNone(self._calc(None).peak_bandwidth)
        self.assertEqual(self._calc(1000).peak_bandwidth, 1000 * 1e9)
        for peak in (0, -1, float("nan"), float("inf"), "not_a_number", 1e308):
            with self.subTest(peak=peak), self.assertRaisesRegex(ValueError, "chip_peak_bandwidth"):
                self._calc(peak)

    def test_init_string_peak_then_converted(self):
        # CLI 等外部输入可能传入字符串形式的峰值带宽，应正常转换而非类型比较异常
        self.assertEqual(self._calc("1600").peak_bandwidth, 1600 * 1e9)

    def test_run_when_no_kernel_data_then_empty(self):
        calc = self._calc(1000)
        with self._patch_export(pd.DataFrame()):
            self.assertTrue(calc.run().empty)

    def test_run_when_no_target_op_then_empty(self):
        calc = self._calc(1000)
        df = pd.DataFrame(
            [
                {
                    "type": "Cast",
                    "kernel_name": "c",
                    "kernel_ts": 1,
                    "kernel_end": 2,
                    "task_duration": 1,
                    "input_shapes": "2,3",
                    "input_types": "FLOAT16",
                    "output_shapes": "2,3",
                    "output_types": "FLOAT16",
                }
            ]
        )
        with self._patch_export(df):
            self.assertTrue(calc.run().empty)

    def test_run_with_peak_then_compute_mbu(self):
        calc = self._calc(1000)  # 1000 GB/s = 1e12 Byte/s
        df = pd.DataFrame(
            [
                {
                    "type": "MatMulV2",
                    "kernel_name": "mm",
                    "kernel_ts": 10,
                    "kernel_end": 20,
                    "task_duration": 10,
                    "input_shapes": "2,3;3,4",
                    "input_types": "FLOAT16;FLOAT16",
                    "output_shapes": "2,4",
                    "output_types": "FLOAT16",
                }
            ]
        )
        with self._patch_export(df):
            res = calc.run()
        self.assertEqual(1, len(res))
        row = res.iloc[0]
        # access_bytes = (2*3 + 3*4)*2 + 2*4*2 = 36 + 16 = 52
        self.assertEqual(52, row["access_bytes"])
        self.assertEqual("MatMulV2", row["op_type"])
        self.assertAlmostEqual(row["achieved_bandwidth"], 52 / (10 * 1e-9))
        self.assertAlmostEqual(row["mbu"], (52 / (10 * 1e-9)) / 1e12)

    def test_run_without_peak_then_mbu_nan(self):
        calc = self._calc(None)
        df = pd.DataFrame(
            [
                {
                    "type": "FlashAttentionScore",
                    "kernel_name": "fa",
                    "kernel_ts": 10,
                    "kernel_end": 30,
                    "task_duration": 20,
                    "input_shapes": "1,8,128,64",
                    "input_types": "FLOAT16",
                    "output_shapes": "1,8,128,64",
                    "output_types": "FLOAT16",
                }
            ]
        )
        with self._patch_export(df):
            res = calc.run()
        self.assertEqual(1, len(res))
        row = res.iloc[0]
        self.assertTrue(pd.isna(row["mbu"]))
        self.assertGreater(row["achieved_bandwidth"], 0)

    def test_run_filters_zero_duration_and_zero_bytes(self):
        calc = self._calc(1000)
        df = pd.DataFrame(
            [
                {
                    "type": "MatMulV2",
                    "kernel_name": "a",
                    "kernel_ts": 1,
                    "kernel_end": 2,
                    "task_duration": 0,
                    "input_shapes": "2,3",
                    "input_types": "FLOAT16",
                    "output_shapes": "2,3",
                    "output_types": "FLOAT16",
                },
                {
                    "type": "MatMulV2",
                    "kernel_name": "b",
                    "kernel_ts": 3,
                    "kernel_end": 4,
                    "task_duration": 5,
                    "input_shapes": "",
                    "input_types": "",
                    "output_shapes": "",
                    "output_types": "",
                },
            ]
        )
        with self._patch_export(df):
            self.assertTrue(calc.run().empty)

    def test_query_kernel_bytes_strips_quotes(self):
        calc = self._calc(1000)
        df = pd.DataFrame(
            [
                {
                    "type": "MatMulV2",
                    "input_shapes": '"2,3"',
                    "output_shapes": "'2,3'",
                    "input_types": '"FLOAT;FLOAT"',
                    "output_types": "'FLOAT'",
                }
            ]
        )
        with self._patch_export(df):
            out = calc._query_kernel_bytes()
        self.assertEqual(out.iloc[0]["input_shapes"], "2,3")
        self.assertEqual(out.iloc[0]["output_shapes"], "2,3")
        # dtype 列同样剥离引号，避免带引号 dtype 查表失败导致按 FP16 回退、字节计算偏差
        self.assertEqual(out.iloc[0]["input_types"], "FLOAT;FLOAT")
        self.assertEqual(out.iloc[0]["output_types"], "FLOAT")

    def test_run_with_quoted_fp32_dtype_then_bytes_use_4(self):
        # 带引号的 FLOAT dtype 应按 4 字节计算而非回退 FP16(2 字节)
        calc = self._calc(1000)
        df = pd.DataFrame(
            [
                {
                    "type": "MatMulV2",
                    "kernel_name": "mm",
                    "kernel_ts": 10,
                    "kernel_end": 20,
                    "task_duration": 10,
                    "input_shapes": '"2,3"',
                    "input_types": '"FLOAT"',
                    "output_shapes": '"2,3"',
                    "output_types": '"FLOAT"',
                }
            ]
        )
        with self._patch_export(df):
            res = calc.run()
        # (2*3)*4 + (2*3)*4 = 48
        self.assertEqual(48, res.iloc[0]["access_bytes"])

    def test_run_missing_columns_then_no_keyerror(self):
        # kernel_name 是可选展示列，缺失时补空值；计算依赖列则必须存在。
        calc = self._calc(1000)
        df = pd.DataFrame(
            [
                {
                    "type": "MatMulV2",
                    "kernel_ts": 10,
                    "kernel_end": 20,
                    "task_duration": 10,
                    "input_shapes": "2,3",
                    "input_types": "FLOAT16",
                    "output_shapes": "",
                    "output_types": "",
                }
            ]
        )
        with self._patch_export(df):
            res = calc.run()
        self.assertEqual(1, len(res))
        self.assertEqual(list(res.columns), MBUCalculator.OUTPUT_COLUMNS)
        self.assertTrue(pd.isna(res.iloc[0]["kernel_name"]))
        self.assertEqual(12, res.iloc[0]["access_bytes"])

    def test_query_kernel_bytes_passes_analysis_class(self):
        # analysis_class 应透传给数据导出类
        calc = MBUCalculator({Constant.PROFILER_DB_PATH: "dummy"}, 1000, "operator_mbu")
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = pd.DataFrame()
        with patch(self.NAMESPACE + "KernelBytesExport", return_value=mock_export) as mock_cls:
            calc._query_kernel_bytes()
        mock_cls.assert_called_once_with("dummy", "operator_mbu", None)

    @staticmethod
    def _kernel_row():
        return {
            "globalTaskId": 1,
            "kernel_name": "mm",
            "type": "MatMulV2",
            "kernel_ts": 10,
            "kernel_end": 20,
            "task_duration": 10,
            "input_shapes": "2,3",
            "input_types": "FLOAT16",
            "output_shapes": "2,3",
            "output_types": "FLOAT16",
        }

    def test_missing_required_columns_are_reported(self):
        for column in MBUCalculator.REQUIRED_COLUMNS:
            row = self._kernel_row()
            del row[column]
            with self.subTest(column=column), self._patch_export(pd.DataFrame([row])):
                with patch(self.NAMESPACE + "logger") as log:
                    self.assertTrue(self._calc().run().empty)
                self.assertIn(column, log.error.call_args.args[1])

    def test_duplicates_preserve_distinct_concurrent_tasks(self):
        row = self._kernel_row()
        rows = [row, row.copy(), dict(row, globalTaskId=2), dict(row, globalTaskId=3, kernel_name="other")]
        with self._patch_export(pd.DataFrame(rows)):
            result = self._calc().run()
        self.assertEqual(result["kernel_name"].tolist(), ["mm", "mm", "other"])
        self.assertEqual(result.index.tolist(), [0, 1, 2])
        self.assertTrue(result["mbu"].isna().all())

    def test_null_shapes_and_types_do_not_become_strings(self):
        row = dict(self._kernel_row(), input_shapes=None, input_types=None)
        with self._patch_export(pd.DataFrame([row])):
            result = self._calc().run()
        self.assertEqual(result.iloc[0]["input_shapes"], "")
        self.assertEqual(result.iloc[0]["access_bytes"], 12)

    def test_calculation_keeps_precision_before_export(self):
        with self._patch_export(pd.DataFrame([self._kernel_row()])):
            result = self._calc(777).run()
        self.assertAlmostEqual(result.iloc[0]["mbu"], 24 / (10 * 1e-9) / (777 * 1e9), places=12)

    def test_step_range_is_forwarded(self):
        step_range = {Constant.START_NS: 10, Constant.END_NS: 20}
        calc = MBUCalculator(
            {Constant.PROFILER_DB_PATH: "dummy", Constant.STEP_RANGE: step_range}, analysis_class="operator_mbu"
        )
        with self._patch_export(pd.DataFrame()) as mock_cls:
            calc.run()
        mock_cls.assert_called_once_with("dummy", "operator_mbu", step_range)


if __name__ == "__main__":
    unittest.main()
