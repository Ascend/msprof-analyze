import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_calculator import MFUCalculator
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

    def test_run_when_mfu_flops_missing_then_return_empty_dataframe(self):
        calc, _ = self.create_mfu_calculator()
        calc.shapes_df = pd.DataFrame([{"kernel_name": "kernel_a"}])
        with (
            patch.object(calc, "_query_kernel_shapes", return_value=True),
            patch.object(calc, "_query_mfu_flops", return_value=None),
        ):
            result = calc.run()
        self.assertTrue(result.empty)

    def test_calculate_mfu_from_recorded_flops_when_label_valid_then_parse_name(self):
        calc, _ = self.create_mfu_calculator()
        calc.op_kernel_df = pd.DataFrame(
            [
                {
                    "kernel_name": "kernel_a",
                    "kernel_ts": 20,
                    "kernel_end": 30,
                    "op_ts": 15,
                    "op_end": 35,
                }
            ]
        )
        calc.shapes_df = pd.DataFrame(
            [
                {
                    "kernel_name": "kernel_a",
                    "kernel_ts": 20,
                    "kernel_end": 30,
                    "task_duration": 10,
                    "input_types": "FLOAT16",
                }
            ]
        )
        mfu_flops_df = pd.DataFrame(
            [
                {"startNs": 10, "endNs": 40, "flops": "100-demo-op"},
                {"startNs": 10, "endNs": 40, "flops": "100:legacy"},
            ]
        )

        with patch.object(calc, "_get_peak_performance", return_value=100):
            result = calc._calculate_mfu_from_recorded_flops(mfu_flops_df)

        self.assertEqual(1, len(result))
        self.assertEqual("demo-op", result.iloc[0]["flops_op_name"])
        self.assertEqual(100, result.iloc[0]["flops"])

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

    def test__query_mfu_flops_when_table_missing_then_return_none(self):
        calc, _ = self.create_mfu_calculator()

        with patch(self.NAMESPACE + "DBManager.check_tables_in_db", return_value=False):
            result = calc._query_mfu_flops()

        self.assertIsNone(result)

    def test__query_mfu_flops_when_export_valid_then_convert_numeric(self):
        calc, _ = self.create_mfu_calculator()
        df = pd.DataFrame([{"startNs": "10", "endNs": "20", "flops": "100-mm"}])
        mock_export = MagicMock()
        mock_export.read_export_db.return_value = df

        with (
            patch(self.NAMESPACE + "DBManager.check_tables_in_db", return_value=True),
            patch(self.NAMESPACE + "MfuFlopsExport", return_value=mock_export),
        ):
            result = calc._query_mfu_flops()
        self.assertFalse(result.empty)
        self.assertEqual(result.iloc[0]["startNs"], 10)
        self.assertEqual(result.iloc[0]["endNs"], 20)
