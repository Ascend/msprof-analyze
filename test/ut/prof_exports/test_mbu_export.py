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

from msprof_analyze.prof_exports.mbu_export import KernelBytesExport, QUERY_KERNEL_BYTES, OP_TYPE_PARAMS
from msprof_analyze.prof_exports.mfu_export import KernelShapeExport
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mbu.mbu_calculator import MBUCalculator


class TestMbuExport(unittest.TestCase):
    def test_kernel_bytes_export_init_and_param_order(self):
        export = KernelBytesExport("dummy.db", "operator_mbu")
        self.assertEqual(export.get_param_order(), [Constant.START_NS, Constant.END_NS, *OP_TYPE_PARAMS])
        self.assertEqual(export.get_query(), QUERY_KERNEL_BYTES)

    def test_query_includes_output_data_types(self):
        # MBU 需要输出数据类型来计算访存字节，查询必须包含 outputDataTypes
        self.assertIn("outputDataTypes", QUERY_KERNEL_BYTES)
        self.assertIn("output_types", QUERY_KERNEL_BYTES)

    def test_sql_filters_steps_and_op_types_and_preserves_mfu_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "profiler.db")
            with sqlite3.connect(db_path) as conn:
                conn.executescript("""
                    CREATE TABLE STRING_IDS (id INTEGER PRIMARY KEY, value TEXT);
                    CREATE TABLE COMPUTE_TASK_INFO (
                        globalTaskId INTEGER, name INTEGER, opType INTEGER,
                        inputShapes INTEGER, inputDataTypes INTEGER, outputShapes INTEGER, outputDataTypes INTEGER
                    );
                    CREATE TABLE TASK (globalTaskId INTEGER, startNs INTEGER, endNs INTEGER);
                    INSERT INTO STRING_IDS VALUES
                        (1, 'mm'), (2, 'MatMulV2'), (3, '2,3;3,4'), (4, 'FLOAT16;FLOAT16'),
                        (5, '2,4'), (6, 'FLOAT16'), (7, 'Cast');
                    INSERT INTO COMPUTE_TASK_INFO VALUES
                        (1, 1, 2, 3, 4, 5, 6), (2, 1, 2, 3, 4, 5, 6),
                        (3, 1, 2, 3, 4, 5, 6), (4, 1, 7, 3, 4, 5, 6);
                    INSERT INTO TASK VALUES (1, 10, 15), (2, 20, 25), (3, 30, 35), (4, 15, 18);
                """)
            result = KernelBytesExport(db_path, "operator_mbu").read_export_db()
            self.assertEqual(result["globalTaskId"].tolist(), [1, 2, 3])
            self.assertEqual(result.iloc[0]["input_shapes"], "2,3;3,4")
            self.assertEqual(result.iloc[0]["input_types"], "FLOAT16;FLOAT16")
            self.assertEqual(result.iloc[0]["output_types"], "FLOAT16")
            self.assertEqual(result.iloc[0]["task_duration"], 5)
            data_map = {
                Constant.PROFILER_DB_PATH: db_path,
                Constant.STEP_RANGE: {Constant.START_NS: 10, Constant.END_NS: 20},
            }
            result = MBUCalculator(data_map, 1000, "operator_mbu").run()
            self.assertEqual(result["kernel_ts"].tolist(), [10, 20])
            self.assertEqual(result["access_bytes"].tolist(), [52, 52])
            mfu_result = KernelShapeExport(db_path, "operator_mfu").read_export_db()
            self.assertEqual(len(mfu_result), 4)
            self.assertEqual(
                mfu_result.columns.tolist(),
                [
                    "kernel_name",
                    "globalTaskId",
                    "type",
                    "input_shapes",
                    "input_types",
                    "output_shapes",
                    "kernel_ts",
                    "kernel_end",
                    "task_duration",
                ],
            )


if __name__ == "__main__":
    unittest.main()
