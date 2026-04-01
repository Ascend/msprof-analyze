import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_calculator import MFUCalculator
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.operator_flops import OperatorType
from msprof_analyze.prof_common.constant import Constant


class TestMFUCalculator(unittest.TestCase):

    NAMESPACE = "msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_calculator."

    def create_mfu_calculator(self, data_map=None, chip_valid=True):
        """创建 MFUCalculator，mock 掉 ChipPeakFLOPSCalculator 避免文件访问。"""
        data_map = data_map or {"PROFILER_DB_PATH": "dummy", "PROFILING_PATH": "dummy"}
        patcher = patch(self.NAMESPACE + "ChipPeakFLOPSCalculator")
        self.addCleanup(patcher.stop)
        mock_chip_cls = patcher.start()
        mock_chip = MagicMock()
        mock_chip.is_valid.return_value = chip_valid
        mock_chip_cls.return_value = mock_chip
        calc = MFUCalculator(data_map)
        return calc, mock_chip

    def test_run_when_chip_info_invalid_then_return_empty_dataframe(self):
        data_map = {"PROFILER_DB_PATH": "dummy", "PROFILING_PATH": "dummy"}
        calc, _ = self.create_mfu_calculator(data_map, chip_valid=False)
        result = calc.run()
        self.assertTrue(result.empty)

    def test_run_when_kernel_shapes_query_failed_then_return_empty_dataframe(self):
        data_map = {"PROFILER_DB_PATH": "dummy", "PROFILING_PATH": "dummy"}
        calc, _ = self.create_mfu_calculator(data_map, chip_valid=True)
        with patch.object(calc, "_query_kernel_shapes", return_value=False):
            result = calc.run()
        self.assertTrue(result.empty)

    def test_process_common_operator_when_valid_input_then_return_mfu_dataframe(self):
        data_map = {"PROFILER_DB_PATH": "dummy", "PROFILING_PATH": "dummy"}
        calc, _ = self.create_mfu_calculator(data_map, chip_valid=True)

        calc.shapes_df = pd.DataFrame(
            [
                {
                    "type": "MatMulV2",
                    "kernel_name": "kernel_a",
                    "kernel_ts": 1,
                    "kernel_end": 11,
                    "task_duration": 10,
                    "input_shapes": "32768,2048;8192,2048",
                    "input_types": "DT_BF16;DT_BF16",
                    "output_shapes": "32768,8192"
                },
                {
                    "type": "OtherType",
                    "kernel_name": "kernel_b",
                    "kernel_ts": 2,
                    "kernel_end": 12,
                    "task_duration": 0,
                    "input_shapes": "32768,2048;8192,2048",
                    "input_types": "DT_BF16;DT_BF16",
                    "output_shapes": "32768,8192"
                },
            ]
        )

        fake_peak = 354 * 1e12

        with patch.object(calc, "_get_peak_performance", return_value=fake_peak):
            result = calc.process_common_operator(OperatorType.MATMUL)

        # 只保留 MatMulV2 对应的一行
        self.assertEqual(len(result), 1)
        self.assertListEqual(
            list(result.columns), ["kernel_name", "kernel_ts", "kernel_end", "mfu"]
        )
        # mfu = workload / (duration * 1e-9) / peak
        expected_workload = 2 * 32768 * 8192 * 2048
        expected_mfu = expected_workload / (10 * 1e-9) / fake_peak
        self.assertAlmostEqual(result["mfu"].iloc[0], expected_mfu)

    def test_process_operator_with_additional_args_mark_when_op_kernel_correlation_missing_then_return_empty(self):
        data_map = {"PROFILER_DB_PATH": "dummy", "PROFILING_PATH": "dummy"}
        calc, _ = self.create_mfu_calculator(data_map, chip_valid=True)
        calc.op_kernel_df = None

        with patch.object(calc, "_query_op_kernel_correlation", return_value=False) as mock_query:
            result = calc.process_operator_with_additional_args_mark(
                OperatorType.FLASH_ATTENTION, "flash_attn_args"
            )

        mock_query.assert_called_once()
        self.assertTrue(result.empty)

    def test_process_operator_with_additional_args_mark_when_operator_args_missing_then_return_empty_dataframe(self):
        data_map = {"PROFILER_DB_PATH": "dummy", "PROFILING_PATH": "dummy"}
        calc, _ = self.create_mfu_calculator(data_map, chip_valid=True)

        calc.op_kernel_df = pd.DataFrame(
            [
                {
                    "kernel_name": "kernel_a",
                    "kernel_ts": 1,
                    "kernel_end": 11,
                    "op_ts": 1,
                    "op_end": 11,
                }
            ]
        )
        calc.shapes_df = pd.DataFrame(
            [
                {
                    "type": "FlashAttentionScore",
                    "kernel_name": "kernel_a",
                    "kernel_ts": 1,
                    "kernel_end": 11,
                }
            ]
        )

        with patch.object(calc, "_query_operator_args", return_value=pd.DataFrame()) as mock_query:
            result = calc.process_operator_with_additional_args_mark(
                OperatorType.FLASH_ATTENTION, "flash_attn_args"
            )

        mock_query.assert_called_once()
        self.assertTrue(result.empty)

    def test_process_operator_with_additional_args_mark_when_valid_input_then_run_success(self):
        data_map = {"PROFILER_DB_PATH": "dummy", "PROFILING_PATH": "dummy"}
        calc, _ = self.create_mfu_calculator(data_map, chip_valid=True)

        calc.op_kernel_df = pd.DataFrame(
            [
                {
                    "kernel_name": "kernel_a",
                    "kernel_ts": 100,
                    "kernel_end": 200,
                    "op_ts": 110,
                    "op_end": 190,
                }
            ]
        )
        calc.shapes_df = pd.DataFrame(
            [
                {
                    "type": "FlashAttentionScore",
                    "kernel_name": "kernel_a",
                    "kernel_ts": 100,
                    "kernel_end": 200,
                }
            ]
        )

        op_args_df = pd.DataFrame([{"startNs": 105}])

        def _fake_calculate_mfu(df, operator_type):
            # 保留原数据并附加 mfu 列，验证 filter 字段是否正确
            self.assertEqual(operator_type, OperatorType.FLASH_ATTENTION)
            df = df.copy()
            df["mfu"] = 0.5
            return df

        with (patch.object(calc, "_query_operator_args", return_value=op_args_df),
              patch.object(calc, "_calculate_mfu", side_effect=_fake_calculate_mfu) as mock_calc_mfu):
            result = calc.process_operator_with_additional_args_mark(
                OperatorType.FLASH_ATTENTION, "flash_attn_args"
            )

        mock_calc_mfu.assert_called_once()
        self.assertEqual(len(result), 1)
        self.assertListEqual(list(result.columns), ["kernel_name", "kernel_ts", "kernel_end", "mfu"])
        self.assertEqual(result["kernel_name"].iloc[0], "kernel_a")
        self.assertEqual(result["mfu"].iloc[0], 0.5)

    def test__query_kernel_shapes_when_no_shapes_then_return_false(self):
        calc, _ = self.create_mfu_calculator()
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = pd.DataFrame()

        with patch(self.NAMESPACE + "KernelShapeExport", return_value=mock_export):
            ok = calc._query_kernel_shapes()

        self.assertFalse(ok)
        self.assertIsNone(calc.shapes_df)

    def test__query_kernel_shapes_when_valid_shapes_then_set_shapes_df_and_return_true(self):
        calc, _ = self.create_mfu_calculator()
        raw_df = pd.DataFrame(
            [
                {
                    "input_shapes": "'1,2'",
                    "output_shapes": '"3,4"',
                    "type": "MatMulV2",
                },
                {
                    "input_shapes": Constant.NA,
                    "output_shapes": Constant.NA,
                    "type": "MatMulV2",
                },
            ]
        )
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = raw_df

        with patch(self.NAMESPACE + "KernelShapeExport", return_value=mock_export):
            ok = calc._query_kernel_shapes()

        self.assertTrue(ok)
        self.assertIsNotNone(calc.shapes_df)
        # 去掉 NA 后只剩一行，并移除引号
        self.assertEqual(len(calc.shapes_df), 1)
        self.assertEqual(calc.shapes_df.iloc[0]["input_shapes"], "1,2")
        self.assertEqual(calc.shapes_df.iloc[0]["output_shapes"], "3,4")

    def test__query_op_kernel_correlation_when_export_empty_then_return_false(self):
        calc, _ = self.create_mfu_calculator()
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = pd.DataFrame()

        with patch(self.NAMESPACE + "FrameworkOpToKernelExport", return_value=mock_export):
            ok = calc._query_op_kernel_correlation()

        self.assertFalse(ok)
        self.assertTrue(calc.op_kernel_df.empty)

    def test__query_op_kernel_correlation_when_valid_then_convert_numeric_and_return_true(self):
        calc, _ = self.create_mfu_calculator()
        df = pd.DataFrame(
            [
                {
                    "kernel_ts": "1",
                    "kernel_end": "2",
                    "op_ts": "3",
                    "op_end": "4",
                }
            ]
        )
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = df

        with patch(self.NAMESPACE + "FrameworkOpToKernelExport", return_value=mock_export):
            ok = calc._query_op_kernel_correlation()

        self.assertTrue(ok)
        self.assertEqual(calc.op_kernel_df.iloc[0]["kernel_ts"], 1)
        self.assertEqual(calc.op_kernel_df.iloc[0]["op_end"], 4)

    def test__query_operator_args_when_table_missing_then_return_empty_dataframe(self):
        calc, _ = self.create_mfu_calculator()

        with patch(self.NAMESPACE + "DBManager.check_tables_in_db", return_value=False):
            result = calc._query_operator_args("flash_attn_args")

        self.assertTrue(result.empty)

    def test__query_operator_args_when_export_valid_then_return_dataframe_with_numeric(self):
        calc, _ = self.create_mfu_calculator()
        df = pd.DataFrame([{"startNs": "10"}])
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = df

        with (patch(self.NAMESPACE + "DBManager.check_tables_in_db", return_value=True),
              patch(self.NAMESPACE + "OperatorArgsExport", return_value=mock_export)):
            result = calc._query_operator_args("flash_attn_args")
        self.assertFalse(result.empty)
        self.assertEqual(result.iloc[0]["startNs"], 10)
