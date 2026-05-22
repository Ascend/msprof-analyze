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

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from msprof_analyze.prof_exports.summary_export import ApiStatisticExport, KernelDetailsExport
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant


class TestApiStatisticExport(unittest.TestCase):

    def test_get_param_order_should_return_empty_list(self):
        export = ApiStatisticExport("/tmp/not_used.db", "summary")

        self.assertEqual(export.get_param_order(), [])
        self.assertIn("FROM CANN_API", export.get_query())

    def test_read_export_db_should_return_api_statistic_from_sqlite_db(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "summary.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE STRING_IDS (id INTEGER PRIMARY KEY, value TEXT)")
            cursor.execute("CREATE TABLE CANN_API (name INTEGER, connectionId INTEGER)")
            cursor.execute("CREATE TABLE TASK (connectionId INTEGER, startNs INTEGER, endNs INTEGER)")
            cursor.executemany("INSERT INTO STRING_IDS VALUES (?, ?)", [(1, "api_a"), (2, "api_b")])
            cursor.executemany("INSERT INTO CANN_API VALUES (?, ?)", [(1, 10), (1, 11), (2, 12)])
            cursor.executemany("INSERT INTO TASK VALUES (?, ?, ?)", [(10, 0, 100), (11, 10, 40), (12, 0, 200)])
            conn.commit()
            conn.close()

            result = ApiStatisticExport(db_path, "summary").read_export_db()

        self.assertEqual(result["API Name"].tolist(), ["api_b", "api_a"])
        self.assertEqual(result["Total Time(ns)"].tolist(), [200, 130])
        self.assertEqual(result["Count"].tolist(), [1, 2])
        self.assertEqual(result["Min Time(ns)"].tolist(), [200, 30])
        self.assertEqual(result["Max Time(ns)"].tolist(), [200, 100])


class TestKernelDetailsExport(unittest.TestCase):

    @staticmethod
    def _create_empty_db(tmp_dir):
        db_path = os.path.join(tmp_dir, "kernel_details.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        return db_path

    @staticmethod
    def _create_full_db(tmp_dir, use_block_num=True, include_op_state=True, include_pmu=True,
                        include_communication=True, include_schedule=True):
        db_path = os.path.join(tmp_dir, "kernel_details.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE STRING_IDS (id INTEGER PRIMARY KEY, value TEXT)")
        cursor.executemany("INSERT INTO STRING_IDS VALUES (?, ?)", [
            (1, "MatMul"),
            (2, "MatMulType"),
            (3, "AI_CORE"),
            (4, "ND"),
            (5, "[1, 2]"),
            (6, "float16"),
            (7, "[1, 3]"),
            (8, "COMM_OP"),
            (9, "AllReduce"),
            (10, "aiv_total_time"),
            (11, "aic_total_time"),
            (12, "active"),
            (13, "ScheduleOp"),
            (14, "COMMUNICATION_SCHEDULE")
        ])
        block_columns = "blockNum INTEGER, mixBlockNum INTEGER" if use_block_num else \
            "blockDim INTEGER, mixBlockDim INTEGER"
        op_state_column = ", opState INTEGER" if include_op_state else ""
        cursor.execute(f"""
            CREATE TABLE COMPUTE_TASK_INFO (
                globalTaskId INTEGER,
                name INTEGER,
                {block_columns},
                opType INTEGER,
                taskType INTEGER,
                inputFormats INTEGER,
                inputShapes INTEGER,
                inputDataTypes INTEGER,
                outputShapes INTEGER,
                outputFormats INTEGER,
                outputDataTypes INTEGER
                {op_state_column}
            )
        """)
        block_names = "blockNum, mixBlockNum" if use_block_num else "blockDim, mixBlockDim"
        op_state_names = ", opState" if include_op_state else ""
        op_state_values = ", 12" if include_op_state else ""
        cursor.execute(f"""
            INSERT INTO COMPUTE_TASK_INFO (
                globalTaskId, name, {block_names}, opType, taskType, inputFormats, inputShapes, inputDataTypes,
                outputShapes, outputFormats, outputDataTypes{op_state_names}
            ) VALUES (100, 1, 32, 16, 2, 3, 4, 5, 6, 7, 4, 6{op_state_values})
        """)
        cursor.execute("""
            CREATE TABLE TASK (
                globalTaskId INTEGER,
                connectionId INTEGER,
                startNs INTEGER,
                endNs INTEGER,
                deviceId INTEGER,
                modelId INTEGER,
                streamId INTEGER,
                contextId INTEGER,
                taskId INTEGER
            )
        """)
        cursor.execute("INSERT INTO TASK VALUES (100, 1000, 1000, 5000, 0, 1, 2, 3, 4)")

        if include_pmu:
            cursor.execute("CREATE TABLE TASK_PMU_INFO (globalTaskId INTEGER, name INTEGER, value INTEGER)")
            cursor.executemany("INSERT INTO TASK_PMU_INFO VALUES (?, ?, ?)", [
                (100, 10, 700),
                (100, 11, 900)
            ])

        if include_communication:
            cursor.execute("""
                CREATE TABLE COMMUNICATION_OP (
                    opName INTEGER,
                    opType INTEGER,
                    startNs INTEGER,
                    endNs INTEGER,
                    connectionId INTEGER
                )
            """)
            cursor.execute("INSERT INTO COMMUNICATION_OP VALUES (9, 8, 6000, 9000, 2000)")
            cursor.execute("INSERT INTO TASK VALUES (200, 2000, 6000, 9000, 5, 6, 7, 8, 9)")

        if include_schedule:
            cursor.execute("""
                CREATE TABLE COMMUNICATION_SCHEDULE_TASK_INFO (
                    globalTaskId INTEGER,
                    name INTEGER,
                    opType INTEGER,
                    taskType INTEGER
                )
            """)
            cursor.execute("INSERT INTO COMMUNICATION_SCHEDULE_TASK_INFO VALUES (300, 13, 8, 14)")
            cursor.execute("INSERT INTO TASK VALUES (300, 3000, 10000, 12000, 2, 3, 4, 5, 6)")

        conn.commit()
        conn.close()
        return db_path

    def test_read_export_db_should_return_none_when_db_path_invalid(self):
        self.assertIsNone(KernelDetailsExport("", "summary").read_export_db())
        self.assertIsNone(KernelDetailsExport("/not/exist/summary.db", "summary").read_export_db())

    def test_read_export_db_should_return_none_when_all_sources_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_empty_db(tmp_dir)
            export = KernelDetailsExport(db_path, "summary")

            result = export.read_export_db()

        self.assertIsNone(result)

    def test_read_export_db_should_merge_compute_communication_and_schedule_data(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_full_db(tmp_dir)
            result = KernelDetailsExport(db_path, "summary").read_export_db()

        self.assertEqual(result["op_name"].tolist(), ["MatMul", "AllReduce", "ScheduleOp"])
        self.assertEqual(result["task_duration"].tolist(), [4.0, 3.0, 2.0])
        self.assertEqual(result["task_wait_time"].tolist(), [0.0, 8.0, 6.0])
        self.assertIn("aiv_time", result.columns)
        self.assertIn("aicore_time", result.columns)
        self.assertNotIn("aiv_total_time", result.columns)
        self.assertNotIn("aic_total_time", result.columns)
        self.assertNotIn("task_end_time", result.columns)
        self.assertNotIn("globalTaskId", result.columns)
        self.assertNotIn("connectionId", result.columns)
        self.assertTrue(result.loc[0, "has_op_state"] if "has_op_state" in result.columns else True)
        self.assertEqual(result.loc[0, "op_state"], "active")
        self.assertEqual(result.loc[0, "block_dim"], 32)
        self.assertEqual(result.loc[1, "task_type"], "COMMUNICATION")
        self.assertEqual(result.loc[2, "task_type"], "COMMUNICATION_SCHEDULE")

    def test_export_compute_task_should_use_block_dim_when_block_num_column_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_full_db(tmp_dir, use_block_num=False, include_op_state=False,
                                           include_communication=False, include_schedule=False)
            export = KernelDetailsExport(db_path, "summary")

            result = export._export_compute_task()

        self.assertFalse(export.has_op_state)
        self.assertEqual(result["block_dim"].tolist(), [32])
        self.assertEqual(result["mix_block_dim"].tolist(), [16])
        self.assertNotIn("op_state", result.columns)

    def test_export_compute_task_should_return_basic_data_when_pmu_data_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_full_db(tmp_dir, include_pmu=False, include_communication=False,
                                           include_schedule=False)
            export = KernelDetailsExport(db_path, "summary")

            result = export._export_compute_task()

        self.assertEqual(result["op_name"].tolist(), ["MatMul"])
        self.assertNotIn("aiv_total_time", result.columns)

    def test_post_process_should_keep_na_time_values_and_sort_by_start_time(self):
        export = KernelDetailsExport("/tmp/not_used.db", "summary")
        df = pd.DataFrame({
            "op_name": ["late", "early"],
            "task_start_time": [3000, 1000],
            "task_end_time": [5000, "N/A"],
            "task_duration": [2000, "N/A"],
            "globalTaskId": [2, 1],
            "connectionId": [20, 10],
            "aiv_total_time": [1000, "N/A"],
            "aic_total_time": [2000, "N/A"]
        })

        result = export._post_process([df])

        self.assertEqual(result["op_name"].tolist(), ["early", "late"])
        self.assertEqual(result["task_start_time"].tolist(), [1.0, 3.0])
        self.assertEqual(result["task_duration"].tolist(), ["N/A", 2.0])
        self.assertTrue(pd.isna(result["task_wait_time"].iloc[0]))
        self.assertEqual(result["task_wait_time"].iloc[1], 0.0)
        self.assertEqual(result["aiv_time"].tolist(), ["N/A", 1.0])
        self.assertEqual(result["aicore_time"].tolist(), ["N/A", 2.0])

    def test_check_table_column_exists_should_return_false_when_db_missing_or_connection_invalid(self):
        export = KernelDetailsExport("/not/exist/summary.db", "summary")
        self.assertFalse(export._check_table_column_exists(Constant.TABLE_COMPUTE_TASK_INFO, TableConstant.OP_STATE))

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_empty_db(tmp_dir)
            export = KernelDetailsExport(db_path, "summary")
            with patch("msprof_analyze.prof_exports.summary_export.DBManager.create_connect_db",
                       return_value=(None, None)):
                self.assertFalse(export._check_table_column_exists(Constant.TABLE_COMPUTE_TASK_INFO,
                                                                   TableConstant.OP_STATE))

    def test_check_table_column_exists_should_detect_existing_column(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_full_db(tmp_dir)
            export = KernelDetailsExport(db_path, "summary")

            self.assertTrue(export._check_table_column_exists(Constant.TABLE_COMPUTE_TASK_INFO,
                                                              TableConstant.OP_STATE))
            self.assertFalse(export._check_table_column_exists(Constant.TABLE_COMPUTE_TASK_INFO, "not_exist"))

    def test_execute_sql_should_return_empty_when_db_missing_connection_invalid_table_missing_or_sql_error(self):
        export = KernelDetailsExport("/not/exist/summary.db", "summary")
        self.assertTrue(export._execute_sql("SELECT 1").empty)

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_empty_db(tmp_dir)
            export = KernelDetailsExport(db_path, "summary")
            self.assertTrue(export._execute_sql("SELECT 1", ["NOT_EXISTS"]).empty)
            self.assertTrue(export._execute_sql("SELECT * FROM NOT_EXISTS").empty)

            with patch("msprof_analyze.prof_exports.summary_export.DBManager.create_connect_db",
                       return_value=(None, None)):
                self.assertTrue(export._execute_sql("SELECT 1").empty)

    @patch("msprof_analyze.prof_exports.summary_export.KernelDetailsExport._export_compute_task")
    def test_read_export_db_should_return_none_when_export_compute_task_raises(self, mock_export_compute_task):
        mock_export_compute_task.side_effect = RuntimeError("boom")
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = self._create_empty_db(tmp_dir)
            result = KernelDetailsExport(db_path, "summary").read_export_db()

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
