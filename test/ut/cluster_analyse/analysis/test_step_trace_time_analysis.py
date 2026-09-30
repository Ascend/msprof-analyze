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

import os
import unittest
import tempfile
from unittest.mock import patch

from msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis import StepTraceTimeAnalysis
from msprof_analyze.cluster_analyse.prof_bean.step_trace_time_bean import StepTraceTimeBean
from msprof_analyze.prof_common.constant import Constant


def _build_analysis(**kwargs):
    # Build analysis instance with defaults
    params = {
        Constant.COLLECTION_PATH: str(kwargs.get("collection_path", "")),
        Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: str(kwargs.get("output_path", "")),
        Constant.DATA_MAP: kwargs.get("data_map", {}),
        Constant.COMM_DATA_DICT: kwargs.get("comm_data_dict", {}),
        Constant.DATA_TYPE: kwargs.get("data_type", Constant.TEXT),
        Constant.IS_MSPROF: kwargs.get("is_msprof", False),
        Constant.IS_MINDSPORE: kwargs.get("is_mindspore", False),
    }
    return StepTraceTimeAnalysis(params)


class TestStepTraceTimeAnalysis(unittest.TestCase):
    DIR_PATH = ''

    def test_get_max_data_row_when_given_data_return_max_rows(self):
        check = StepTraceTimeAnalysis({})
        ls = [
            [1, 3, 5, 7, 10],
            [2, 4, 6, 8, 11],
            [1000, -1, -1, -1, -1]
        ]
        ret = check.get_max_data_row(ls)
        self.assertEqual([1000, 4, 6, 8, 11], ret)

    def test_get_max_data_when_given_row_single_ls_return_this_row(self):
        check = StepTraceTimeAnalysis({})
        ls = [
            [1, 3, 5, 7, 10]
        ]
        ret = check.get_max_data_row(ls)
        self.assertEqual([1, 3, 5, 7, 10], ret)

    def test_analyze_step_time_when_give_normal_expect_stage(self):
        check = StepTraceTimeAnalysis({})
        check.data_type = Constant.TEXT
        check.step_time_dict = {
            0: [
                StepTraceTimeBean({"Step": 0, "time1": 1, "time2": 2}),
                StepTraceTimeBean({"Step": 1, "time1": 1, "time2": 2}),
            ],
            1: [
                StepTraceTimeBean({"Step": 0, "time1": 10, "time2": 20}),
                StepTraceTimeBean({"Step": 1, "time1": 10, "time2": 20})
            ]
        }
        check.communication_data_dict = {Constant.STAGE: [[0, 1]]}
        check.analyze_step_time()
        self.assertIn([0, 'stage', (0, 1), 10.0, 20.0], check.step_data_list)

    def test_analyze_step_time_when_given_none_step_expect_stage_and_rank_row(self):
        check = StepTraceTimeAnalysis({})
        check.data_type = Constant.TEXT
        check.step_time_dict = {
            0: [
                StepTraceTimeBean({"Step": None, "time1": 1, "time2": 2})
            ],
            1: [
                StepTraceTimeBean({"Step": None, "time1": 10, "time2": 20}),
            ],
            2: [
                StepTraceTimeBean({"Step": None, "time1": 2, "time2": 3}),
            ],
            3: [
                StepTraceTimeBean({"Step": None, "time1": 1, "time2": 1}),
            ],
        }
        check.communication_data_dict = {Constant.STAGE: [[0, 1], [2, 3]]}
        check.analyze_step_time()
        self.assertIn([None, 'stage', (2, 3), 2.0, 3.0], check.step_data_list)
        self.assertIn([None, 'rank', 0, 1.0, 2.0], check.step_data_list)

    def test_find_msprof_json_when_multi_msprof_json_timestamps_then_return_latest_files(self):
        # Create two timestamped files and expect the latest one
        with tempfile.TemporaryDirectory() as d:
            older = os.path.join(d, "msprof_20240101010101.json")
            newer = os.path.join(d, "msprof_20250101010101.json")
            with open(older, "w", encoding="utf-8") as f:
                f.write("{}")
            with open(newer, "w", encoding="utf-8") as f:
                f.write("{}")
            analysis = _build_analysis()
            ret = analysis.find_msprof_json(d)
            self.assertEqual(len(ret), 1)
            self.assertEqual(os.path.basename(ret[0]), "msprof_20250101010101.json")

    def test_find_msprof_json_when_multi_msprof_slice_json_then_return_latest_files(self):
        # Create two timestamped files and expect the latest one
        with tempfile.TemporaryDirectory() as d:
            older = os.path.join(d, "msprof_slice_0_20240101010101.json")
            newer = os.path.join(d, "msprof_slice_0_20250101010101.json")
            with open(older, "w", encoding="utf-8") as f:
                f.write("{}")
            with open(newer, "w", encoding="utf-8") as f:
                f.write("{}")
            analysis = _build_analysis()
            ret = analysis.find_msprof_json(d)
            self.assertEqual(len(ret), 1)
            self.assertEqual(os.path.basename(ret[0]), "msprof_slice_0_20250101010101.json")

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.ParallelStrategyCalculator")
    def test_partition_ranks_data_when_parallel_map_available_then_append_parallel_columns(self, mock_calc_cls):
        # Simulate parallel strategy result and validate appended columns
        analysis = _build_analysis(data_type=Constant.TEXT)
        analysis.distributed_args = {"dummy": True}
        analysis.step_time_dict = {
            0: [StepTraceTimeBean({"Step": 1, "time1": 7, "time2": 8})],
            1: [StepTraceTimeBean({"Step": 1, "time1": 5, "time2": 10})]
        }
        analysis.step_data_list = [
            [1, Constant.RANK, 0, 1],
            [1, Constant.RANK, 1, 2],
        ]

        instance = mock_calc_cls.return_value
        instance.run.return_value = {0: (0, 1, 2), 1: (3, 4, 5)}

        analysis.partition_ranks_data()
        # Each rank row should be extended by 3 parallel columns
        self.assertEqual(analysis.step_data_list[0][-3:], [0, 1, 2])
        self.assertEqual(analysis.step_data_list[1][-3:], [3, 4, 5])

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.ParallelStrategyCalculator")
    def test_partition_ranks_data_when_parallel_map_not_available_then_return(self, mock_calc_cls):
        analysis = _build_analysis(data_type=Constant.TEXT)
        # distributed_args is None
        analysis.partition_ranks_data()
        mock_calc_cls.assert_not_called()

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.FileManager.create_csv_file")
    def test_dump_data_when_text_then_write_csv_with_headers(self, mock_create_csv):
        # Verify CSV writer called with proper headers
        with tempfile.TemporaryDirectory() as d:
            output_dir = os.path.join(d, "out")
            os.makedirs(output_dir, exist_ok=True)
            analysis = _build_analysis(data_type=Constant.TEXT, output_path=str(output_dir))

            analysis.step_data_list = [[1, Constant.RANK, 0, 1, 2, 3]]
            fake_bean = StepTraceTimeBean({"Step": 1, "time1": 7, "time2": 8})
            analysis.step_time_dict = {0: [fake_bean]}
            analysis.dump_data()

            self.assertTrue(mock_create_csv.called)
            args, _ = mock_create_csv.call_args # args: (path, rows, filename, headers)
            self.assertEqual(args[2], analysis.CLUSTER_TRACE_TIME_CSV)
            self.assertEqual(args[3], fake_bean.all_headers)
            self.assertEqual(args[1], analysis.step_data_list)

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.MsprofStepTraceTimeAdapter")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.StepTraceTimeAnalysis.find_msprof_json")
    def test_load_step_trace_time_data_when_text_msprof_then_populates_dict(self, mock_find_json, mock_adapter_cls):
        # Should populate step_time_dict for TEXT + is_msprof flow
        with tempfile.TemporaryDirectory() as d:
            # Prepare data_map: rank_id -> profiling dir
            profiling_dir = os.path.join(d, "rank0")
            os.makedirs(os.path.join(profiling_dir, "mindstudio_profiler_output"), exist_ok=True)
            data_map = {0: profiling_dir}

            analysis = _build_analysis(data_type=Constant.TEXT, is_msprof=True, data_map=data_map)

            # Mock json discovery and adapter return
            mock_find_json.return_value = [os.path.join(profiling_dir, "mindstudio_profiler_output",
                                                        "msprof_20240101010101.json")]
            adapter_instance = mock_adapter_cls.return_value
            adapter_instance.generate_step_trace_time_data.return_value = [StepTraceTimeBean({"Step": 1, "time1": 7,
                                                                                              "time2": 8})]

            analysis.load_step_trace_time_data()
            self.assertIn(0, analysis.step_time_dict)
            self.assertEqual(len(analysis.step_time_dict[0]), 1)
            self.assertIsInstance(analysis.step_time_dict[0][0], StepTraceTimeBean)

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.FileManager.read_csv_file")
    def test_load_step_trace_time_data_when_text_plain_then_reads_csv(self, mock_read_csv):
        # Should read csv for TEXT non-msprof when file exists
        with tempfile.TemporaryDirectory() as d:
            profiling_dir = os.path.join(d, "rank0")
            single_output = os.path.join(profiling_dir, Constant.SINGLE_OUTPUT)
            os.makedirs(single_output, exist_ok=True)
            step_time_csv = os.path.join(single_output, Constant.STEP_TIME_CSV)
            with open(step_time_csv, "w", encoding="utf-8") as f:
                f.write("Step,time1,time2\n")
                f.write("1,7,8\n")

            mock_read_csv.return_value = [StepTraceTimeBean({"Step": 1, "time1": 7, "time2": 8})]

            data_map = {0: profiling_dir}
            analysis = _build_analysis(data_type=Constant.TEXT, is_msprof=False, data_map=data_map)
            analysis.load_step_trace_time_data()

            self.assertIn(0, analysis.step_time_dict)
            self.assertEqual(len(analysis.step_time_dict[0]), 1)
            self.assertIsInstance(analysis.step_time_dict[0][0], StepTraceTimeBean)

    def test_load_step_trace_time_data_when_text_plain_file_missing_then_empty(self):
        # Should not populate when csv missing
        with tempfile.TemporaryDirectory() as d:
            profiling_dir = os.path.join(d, "rank0")
            data_map = {0: profiling_dir}
            analysis = _build_analysis(data_type=Constant.TEXT, is_msprof=False, data_map=data_map)
            analysis.load_step_trace_time_data()
            self.assertNotIn(0, analysis.step_time_dict)

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.MsprofDataPreprocessor."
           "get_msprof_profiler_db_path")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.MsprofStepTraceTimeDBAdapter")
    def test_load_step_trace_time_data_when_db_msprof_then_use_db_adapter(self, mock_db_adapter_cls, mock_get_db_path):
        # Should use DB adapter for DB + is_msprof
        with tempfile.TemporaryDirectory() as d:
            profiling_dir = os.path.join(d, "rank0")
            data_map = {0: profiling_dir}
            analysis = _build_analysis(data_type=Constant.DB, is_msprof=True, data_map=data_map)

            mock_get_db_path.return_value = os.path.join(profiling_dir, "profiler.db")
            adapter_instance = mock_db_adapter_cls.return_value
            adapter_instance.generate_step_trace_time_data.return_value = [(1, 2, 3)]

            analysis.load_step_trace_time_data()
            self.assertIn(0, analysis.step_time_dict)
            self.assertEqual(analysis.step_time_dict[0], [(1, 2, 3)])

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.MsprofStepTraceTimeDBAdapter")
    def test_load_step_trace_time_data_when_db_mindspore_then_use_db_adapter(self, mock_db_adapter_cls):
        # Should use DB adapter for DB + is_mindspore
        with tempfile.TemporaryDirectory() as d:
            profiling_dir = os.path.join(d, "rank0")
            single_output = os.path.join(profiling_dir, Constant.SINGLE_OUTPUT)
            os.makedirs(single_output, exist_ok=True)
            data_map = {0: profiling_dir}
            analysis = _build_analysis(data_type=Constant.DB, is_mindspore=True, data_map=data_map)

            adapter_instance = mock_db_adapter_cls.return_value
            adapter_instance.generate_step_trace_time_data.return_value = [(4, 5, 6)]

            analysis.load_step_trace_time_data()
            self.assertIn(0, analysis.step_time_dict)
            self.assertEqual(analysis.step_time_dict[0], [(4, 5, 6)])
            self.assertTrue(mock_db_adapter_cls.called)

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.check_tables_in_db")
    def test_load_step_trace_time_data_when_db_plain_no_table_then_empty(self, mock_check):
        # Should not populate when table missing or file missing
        with tempfile.TemporaryDirectory() as d:
            profiling_dir = os.path.join(d, "rank0")
            single_output = os.path.join(profiling_dir, Constant.SINGLE_OUTPUT)
            os.makedirs(single_output, exist_ok=True)
            mock_check.return_value = False

            data_map = {0: profiling_dir}
            analysis = _build_analysis(data_type=Constant.DB, data_map=data_map)
            analysis.load_step_trace_time_data()
            self.assertFalse(len(analysis.step_time_dict))

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.FileManager.read_json_file")
    def test_load_step_trace_time_data_when_metadata_present_then_set_distributed_args(self, mock_read_json):
        # Should set distributed_args from profiler_metadata.json when present
        with tempfile.TemporaryDirectory() as d:
            profiling_dir = os.path.join(d, "rank0")
            os.makedirs(profiling_dir, exist_ok=True)
            # Create metadata file path
            metadata_path = os.path.join(profiling_dir, StepTraceTimeAnalysis.PROFILER_METADATA_JSON)
            with open(metadata_path, "w", encoding="utf-8") as f:
                f.write("{}")

            dist_args = {"dp": 2, "pp": 1, "tp": 4}
            mock_read_json.return_value = {Constant.DISTRIBUTED_ARGS: dist_args}

            data_map = {0: profiling_dir}
            analysis = _build_analysis(data_type=Constant.TEXT, data_map=data_map)
            self.assertIsNone(analysis.distributed_args)

            analysis.load_step_trace_time_data()
            self.assertEqual(analysis.distributed_args, dist_args)

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.destroy_db_connect")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.executemany_sql")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.create_connect_db")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.get_table_column_count")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.create_tables")
    def test_dump_data_when_db_and_rows_short_then_pad_and_insert(self, mock_create_tables, mock_col_count,
                                                                  mock_connect, mock_execmany, mock_destroy):
        # Validate that rows are padded to match table columns and inserted
        with tempfile.TemporaryDirectory() as d:
            output_dir = d
            analysis = _build_analysis(data_type=Constant.DB, output_path=str(output_dir))
            # Two rows with length 5; table expects 8
            analysis.step_data_list = [
                [1, Constant.RANK, 0, 1, 2],
                [1, Constant.RANK, 1, 3, 4],
            ]

            mock_col_count.return_value = 8
            mock_connect.return_value = (object(), object())
            analysis.dump_data()

            # Verify padding happened before insert
            args, _ = mock_execmany.call_args
            conn_arg, sql_arg, data_arg = args
            self.assertIsNotNone(conn_arg)
            self.assertIn("values (?,?,?,?,?,?,?,?)", sql_arg)  # Expect 8 placeholders for insert
            self.assertTrue(all(len(row) == 8 for row in data_arg))  # Each row should be length 8 now

    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.destroy_db_connect")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.executemany_sql")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.create_connect_db")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.get_table_column_count")
    @patch("msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis.DBManager.create_tables")
    def test_dump_data_when_db_and_rows_long_enough_then_insert_without_padding(self, mock_create_tables,
                                                                                mock_col_count, mock_connect,
                                                                                mock_execmany, mock_destroy):
        # Validate no padding when row length >= column count
        with tempfile.TemporaryDirectory() as d:
            output_dir = d
            analysis = _build_analysis(data_type=Constant.DB, output_path=str(output_dir))
            # Rows length 6; table expects 6
            analysis.step_data_list = [
                [1, Constant.RANK, 0, 1, 2, 3],
                [1, Constant.RANK, 1, 4, 5, 6],
            ]

            mock_col_count.return_value = 6
            mock_connect.return_value = (object(), object())

            analysis.dump_data()

            args, _ = mock_execmany.call_args
            _, sql_arg, data_arg = args
            self.assertIn("values (?,?,?,?,?,?)", sql_arg)
            self.assertEqual(data_arg, analysis.step_data_list)
