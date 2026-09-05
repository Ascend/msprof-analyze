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

import argparse
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.operator_mbu.operator_mbu import OperatorMbu
from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant


def _calc_result_df():
    """MBUCalculator.run() 的典型返回（kernel 级，带宽单位 Byte/s）。"""
    return pd.DataFrame(
        [
            {
                "kernel_name": "mm_kernel",
                "kernel_ts": 10,
                "kernel_end": 20,
                "op_type": "MatMulV2",
                "access_bytes": 52,
                "kernel_duration": 10,
                "achieved_bandwidth": 5.2e9,
                "chip_peak_bandwidth": 1e12,
                "mbu": 0.0052,
                "input_shapes": "2,3;3,4",
                "output_shapes": "2,4",
            }
        ]
    )


class TestOperatorMbu(unittest.TestCase):
    """测试算子 MBU 分析任务。"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.analysis = OperatorMbu(self._params(Constant.TEXT))

    def _params(self, export_type):
        return {
            Constant.COLLECTION_PATH: self.temp_dir,
            Constant.RECIPE_NAME: "operator_mbu",
            Constant.EXPORT_TYPE: export_type,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.temp_dir,
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_operator_mbu_then_inherit_base_recipe_analysis(self):
        self.assertIsInstance(self.analysis, BaseRecipeAnalysis)

    def test_add_parser_argument_registers_peak_bandwidth(self):
        parser = argparse.ArgumentParser()
        OperatorMbu.add_parser_argument(parser)
        args = parser.parse_args(["--chip_peak_bandwidth", "1600"])
        self.assertEqual(1600.0, args.chip_peak_bandwidth)

    def test_run_when_save_is_false_then_return_non_empty_mapper_results(self):
        mapper_res = [(0, pd.DataFrame({"mbu": [0.5]})), (1, pd.DataFrame())]
        with patch.object(self.analysis, "mapper_func", return_value=mapper_res):
            result = self.analysis.run(context=None, save=False)
        self.assertEqual(1, len(result))
        self.assertEqual(0, result[0][0])

    def test_mapper_func_when_no_mbu_then_empty(self):
        data_map = {Constant.PROFILER_DB_PATH: "fake.db", Constant.RANK_ID: 5}
        ns = "msprof_analyze.cluster_analyse.recipes.operator_mbu.operator_mbu."
        with patch(ns + "MBUCalculator") as mock_calc:
            mock_calc.return_value.run.return_value = pd.DataFrame()
            rank_id, df = self.analysis._mapper_func(data_map, "operator_mbu")
        self.assertEqual(5, rank_id)
        self.assertTrue(df.empty)

    def test_mapper_func_when_mbu_exists_then_insert_rank_id(self):
        data_map = {Constant.PROFILER_DB_PATH: "fake.db", Constant.RANK_ID: 3}
        ns = "msprof_analyze.cluster_analyse.recipes.operator_mbu.operator_mbu."
        with patch(ns + "MBUCalculator") as mock_calc:
            mock_calc.return_value.run.return_value = _calc_result_df()
            rank_id, df = self.analysis._mapper_func(data_map, "operator_mbu")
        self.assertEqual(3, rank_id)
        self.assertFalse(df.empty)
        self.assertEqual(3, df.iloc[0]["rank_id"])
        self.assertEqual("MatMulV2", df.iloc[0]["op_type"])

    def test_mapper_func_passes_peak_bandwidth_from_extra_args(self):
        data_map = {Constant.PROFILER_DB_PATH: "fake.db", Constant.RANK_ID: 0}
        ns = "msprof_analyze.cluster_analyse.recipes.operator_mbu.operator_mbu."
        self.analysis._extra_args["chip_peak_bandwidth"] = 1600.0
        with patch(ns + "MBUCalculator") as mock_calc:
            mock_calc.return_value.run.return_value = pd.DataFrame()
            self.analysis._mapper_func(data_map, "operator_mbu")
        # 第二个位置参数应为传入的峰值带宽，第三个位置参数应为 analysis_class
        self.assertEqual(1600.0, mock_calc.call_args[0][1])
        self.assertEqual("operator_mbu", mock_calc.call_args[0][2])

    def test_reducer_func_then_concat_non_empty_ranks(self):
        mapper_res = [
            (0, pd.DataFrame({"mbu": [0.5]})),
            (1, pd.DataFrame()),
            (2, pd.DataFrame({"mbu": [0.7]})),
        ]
        result = self.analysis.reducer_func(mapper_res)
        self.assertEqual(2, len(result))
        self.assertEqual({0.5, 0.7}, set(result["mbu"]))

    def test_reducer_func_when_all_empty_then_return_empty(self):
        self.assertTrue(self.analysis.reducer_func([(0, pd.DataFrame())]).empty)

    def test_reducer_func_then_sorted_by_rank_and_kernel_ts(self):
        # 合并结果应按 rank_id、kernel_ts 排序
        mapper_res = [
            (1, pd.DataFrame({"rank_id": [1, 1], "kernel_ts": [30, 10], "mbu": [0.3, 0.1]})),
            (0, pd.DataFrame({"rank_id": [0], "kernel_ts": [20], "mbu": [0.2]})),
        ]
        result = self.analysis.reducer_func(mapper_res)
        self.assertEqual([0, 1, 1], result["rank_id"].tolist())
        self.assertEqual([20, 10, 30], result["kernel_ts"].tolist())

    def test_save_csv_then_write_single_mbu_csv_with_friendly_headers(self):
        df = _calc_result_df()
        df.insert(0, "rank_id", 0)
        self.analysis.save_csv(df)
        output_file = os.path.join(self.analysis.output_path, OperatorMbu.MBU_CSV)
        self.assertTrue(os.path.exists(output_file))
        written = pd.read_csv(output_file)
        self.assertIn("MBU", written.columns)
        self.assertIn("Rank ID", written.columns)
        self.assertIn("Op Type", written.columns)
        self.assertIn("Achieved Bandwidth(GB/s)", written.columns)
        # Byte/s -> GB/s: 5.2e9 / 1e9 = 5.2
        self.assertAlmostEqual(5.2, written.iloc[0]["Achieved Bandwidth(GB/s)"])

    def test_save_csv_when_empty_then_skip_writing(self):
        self.analysis.save_csv(pd.DataFrame())
        output_file = os.path.join(self.analysis.output_path, OperatorMbu.MBU_CSV)
        self.assertFalse(os.path.exists(output_file))

    def test_save_db_then_write_operator_mbu_table_with_db_headers(self):
        analysis = OperatorMbu(self._params(Constant.DB))
        df = _calc_result_df()
        df.insert(0, "rank_id", 0)
        analysis.save_db(df)

        db_file = os.path.join(analysis.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        self.assertTrue(os.path.exists(db_file))
        conn = sqlite3.connect(db_file)
        try:
            written = pd.read_sql(f"SELECT * FROM {OperatorMbu.TABLE_OPERATOR_MBU}", conn)
        finally:
            conn.close()
        self.assertEqual(1, len(written))
        # 精确比对列名与顺序：DataFrame 索引不应落库，列名应为 DB 风格。
        self.assertEqual(list(OperatorMbu.DB_COLUMN_MAPPING.values()), list(written.columns))
        # Byte/s -> GB/s: 5.2e9 / 1e9 = 5.2
        self.assertAlmostEqual(5.2, written.iloc[0]["achieved_bandwidth(GB/s)"])

    def test_save_db_when_empty_then_skip_dump_data(self):
        analysis = OperatorMbu(self._params(Constant.DB))
        # 断言未进入 dump_data，避免被基类自带的空数据兜底掩盖 save_db 自身的校验。
        with patch.object(analysis, "dump_data") as mock_dump:
            analysis.save_db(pd.DataFrame())
        mock_dump.assert_not_called()
        db_file = os.path.join(analysis.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        self.assertFalse(os.path.exists(db_file))

    def test_run_when_export_type_is_db_then_dispatch_to_save_db(self):
        analysis = OperatorMbu(self._params(Constant.DB))
        mapper_res = [(0, _calc_result_df())]
        with (
            patch.object(analysis, "mapper_func", return_value=mapper_res),
            patch.object(analysis, "save_db") as mock_save_db,
            patch.object(analysis, "save_csv") as mock_save_csv,
        ):
            analysis.run(context=None)
        mock_save_db.assert_called_once()
        mock_save_csv.assert_not_called()

    def test_run_when_export_type_is_text_then_dispatch_to_save_csv(self):
        mapper_res = [(0, _calc_result_df())]
        with (
            patch.object(self.analysis, "mapper_func", return_value=mapper_res),
            patch.object(self.analysis, "save_db") as mock_save_db,
            patch.object(self.analysis, "save_csv") as mock_save_csv,
        ):
            self.analysis.run(context=None)
        mock_save_csv.assert_called_once()
        mock_save_db.assert_not_called()

    def test_run_when_export_type_is_notebook_then_return_none_without_mapper(self):
        analysis = OperatorMbu(self._params(Constant.NOTEBOOK))
        with patch.object(analysis, "mapper_func") as mock_mapper:
            self.assertIsNone(analysis.run(context=None))
        mock_mapper.assert_not_called()

    def test_run_when_export_type_is_db_then_write_table_end_to_end(self):
        # 只 mock mapper_func，让 run 走完 reducer 与落库全链路。
        analysis = OperatorMbu(self._params(Constant.DB))
        rank_df = _calc_result_df()
        rank_df.insert(0, "rank_id", 0)
        with patch.object(analysis, "mapper_func", return_value=[(0, rank_df)]):
            self.assertIsNone(analysis.run(context=None))

        db_file = os.path.join(analysis.output_path, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER)
        self.assertTrue(os.path.exists(db_file))
        conn = sqlite3.connect(db_file)
        try:
            written = pd.read_sql(f"SELECT * FROM {OperatorMbu.TABLE_OPERATOR_MBU}", conn)
        finally:
            conn.close()
        self.assertEqual(list(OperatorMbu.DB_COLUMN_MAPPING.values()), list(written.columns))
        self.assertEqual(0, written.iloc[0]["rank_id"])
        self.assertEqual("MatMulV2", written.iloc[0]["op_type"])
        self.assertAlmostEqual(0.0052, written.iloc[0]["mbu"])

    def test_run_when_export_type_is_text_then_write_csv_end_to_end(self):
        # 只 mock mapper_func，让 run 走完 reducer 与写文件全链路。
        rank_df = _calc_result_df()
        rank_df.insert(0, "rank_id", 0)
        with patch.object(self.analysis, "mapper_func", return_value=[(0, rank_df)]):
            self.assertIsNone(self.analysis.run(context=None))

        output_file = os.path.join(self.analysis.output_path, OperatorMbu.MBU_CSV)
        self.assertTrue(os.path.exists(output_file))
        written = pd.read_csv(output_file)
        self.assertEqual(list(OperatorMbu.TEXT_COLUMN_MAPPING.values()), list(written.columns))
        self.assertAlmostEqual(5.2, written.iloc[0]["Achieved Bandwidth(GB/s)"])


if __name__ == "__main__":
    unittest.main()
