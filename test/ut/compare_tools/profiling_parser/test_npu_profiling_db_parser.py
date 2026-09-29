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
from unittest.mock import MagicMock

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_db_parser import \
    NPUProfilingDbParser
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.framework_api_bean import \
    FrameworkApiBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.hccl_op_bean import \
    HcclOpBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.hccl_task_bean import \
    HcclTaskBean
from msprof_analyze.prof_common.db_manager import DBManager


class TestNPUProfilingDbParser(unittest.TestCase):
    db_path, args, conn, cursor = None, None, None, None

    @classmethod
    def setUpClass(cls) -> None:
        cls.db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "ascend_pytorch_profiler_0.db")
        cls.conn, cls.cursor = DBManager.create_connect_db(cls.db_path)

        cls._create_test_tables()
        cls._insert_test_data()

        cls.args = MagicMock()
        cls.path_dict = {Constant.PROFILER_DB_PATH: cls.db_path}

    @classmethod
    def tearDownClass(cls) -> None:
        DBManager.destroy_db_connect(cls.conn, cls.cursor)
        cls.conn, cls.cursor = None, None
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    @classmethod
    def _create_test_tables(cls):
        cls.cursor.execute("""
        CREATE TABLE PYTORCH_API (
            id INTEGER PRIMARY KEY,
            startNs INTEGER,
            endNs INTEGER,
            connectionId INTEGER,
            name INTEGER,
            inputShapes INTEGER,
            type INTEGER
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE STRING_IDS (
            id INTEGER PRIMARY KEY,
            value TEXT
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE ENUM_API_TYPE (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE COMPUTE_TASK_INFO (
            globalTaskId INTEGER PRIMARY KEY,
            name INTEGER,
            opType INTEGER,
            taskType INTEGER,
            inputShapes INTEGER
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE TASK (
            globalTaskId INTEGER PRIMARY KEY,
            startNs INTEGER,
            endNs INTEGER,
            streamId INTEGER,
            connectionId INTEGER,
            taskType INTEGER
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE COMMUNICATION_OP (
            opId INTEGER PRIMARY KEY,
            startNs INTEGER,
            endNs INTEGER,
            opType INTEGER,
            opName INTEGER,
            groupName INTEGER,
            connectionId INTEGER
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE COMMUNICATION_TASK_INFO (
            opId INTEGER PRIMARY KEY,
            planeId INTEGER,
            globalTaskId INTEGER,
            taskType INTEGER,
            groupName INTEGER
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE OP_MEMORY (
            name INTEGER,
            size INTEGER,
            allocationTime INTEGER,
            releaseTime INTEGER,
            duration INTEGER
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE STEP_TIME (
            id INTEGER PRIMARY KEY,
            startNs INTEGER,
            endNs INTEGER
        )
        """)

        cls.cursor.execute("""
        CREATE TABLE CONNECTION_IDS (
            id INTEGER PRIMARY KEY,
            connectionId INTEGER
        )
        """)

    @classmethod
    def _insert_test_data(cls):
        cls.cursor.execute("INSERT INTO STRING_IDS (id, value) VALUES (1, 'op')")
        cls.cursor.execute("INSERT INTO STRING_IDS (id, value) VALUES (2, 'hcom_allReduce_')")
        cls.cursor.execute("INSERT INTO STRING_IDS (id, value) VALUES (3, 'hcom_allReduce__568_1_1')")
        cls.cursor.execute("INSERT INTO STRING_IDS (id, value) VALUES (4, '1')")
        cls.cursor.execute("INSERT INTO STRING_IDS (id, value) VALUES (536870915, 'aten::zeros')")
        cls.cursor.execute("INSERT INTO CONNECTION_IDS (id, connectionId) VALUES (1, 1)")
        cls.cursor.execute("INSERT INTO ENUM_API_TYPE (id, name) VALUES (1, 'op')")
        cls.cursor.execute("INSERT INTO STEP_TIME (id, startNs, endNs) VALUES (1, 1500, 1600)")
        cls.cursor.execute("""
        INSERT INTO PYTORCH_API (startNs, endNs, connectionId, name, inputShapes, type)
        VALUES (1500, 1600, 1, 2, 3, 1)
        """)
        cls.cursor.execute("""
        INSERT INTO COMMUNICATION_OP (opId, startNs, endNs, opType, opName, groupName, connectionId)
        VALUES (1, 1500, 1600, 2, 3, 3, 1)
        """)
        cls.cursor.execute("""
        INSERT INTO TASK (globalTaskId, startNs, endNs, streamId, connectionId, taskType)
        VALUES (1, 1500, 1600, 2, 2, 3), (2, 1700, 1800, 3, 3, 1)
        """)
        cls.cursor.execute("""
        INSERT INTO COMMUNICATION_TASK_INFO (opId, planeId, globalTaskId, taskType, groupName)
        VALUES (1, 1, 1, 2, 3)
        """)
        cls.cursor.execute("""
        INSERT INTO COMPUTE_TASK_INFO (globalTaskId, name, opType, taskType, inputShapes)
        VALUES (2, 1, 1, 1, 4)
        """)
        cls.cursor.execute("""
        INSERT INTO OP_MEMORY (name, size, allocationTime, releaseTime, duration)
        VALUES (536870915, 512, 1756713554749777610, 1756713556949777610, 2223184720)
        """)
        cls.conn.commit()

    def setUp(self):
        self.args.enable_profiling_compare = True
        self.args.enable_operator_compare = True
        self.args.enable_memory_compare = True
        self.args.enable_communication_compare = True
        self.args.enable_api_compare = True
        self.args.enable_kernel_compare = True
        self.args.use_kernel_type = False
        self.args.max_kernel_num = 100

    def test_initialization(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        self.assertEqual(parser._db_path, self.db_path)
        self.assertTrue(parser._enable_profiling_compare)
        self.assertIsNotNone(parser.conn)
        self.assertIsNotNone(parser.cursor)

    def test_load_data(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        result = parser.load_data()
        self.assertEqual(1, len(result.communication_dict))
        self.assertIn("allreduce", result.communication_dict)
        self.assertEqual({"comm_list", "comm_task"}, set(result.communication_dict.get("allreduce").keys()))
        self.assertEqual(1, len(result.torch_op_data))

    def test_load_data_given_enable_profiling_compare_and_enable_communication_compare_false(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        parser._args.enable_profiling_compare = False
        parser._args.enable_communication_compare = False
        result = parser.load_data()
        self.assertEqual(1, len(result.torch_op_data))

    def test_get_step_range(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict, step_id=1)
        parser._get_step_range()
        self.assertEqual(parser.step_range, [1500, 1600])

    def test_get_step_range_invalid_id(self):
        with self.assertRaises(RuntimeError):
            parser = NPUProfilingDbParser(self.args, self.path_dict, step_id=999)
            parser._get_step_range()

    def test_query_torch_op_data(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        parser._get_step_range()
        parser._query_torch_op_data()

        self.assertGreater(len(parser.result_data.torch_op_data), 0)
        self.assertIsInstance(parser.result_data.torch_op_data[0], FrameworkApiBean)

    def test_query_compute_op_data(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        parser._query_compute_op_data()

        self.assertTrue(hasattr(parser.result_data, 'kernel_dict'))
        if parser._enable_kernel_compare:
            self.assertTrue(hasattr(parser.result_data, 'kernel_details'))

    def test_query_compute_op_data_given_enable_kernel_compare_and_enable_profiling_compare_false(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        parser._enable_kernel_compare = False
        parser._enable_profiling_compare = False
        parser._query_compute_op_data()
        self.assertTrue(hasattr(parser.result_data, 'kernel_dict'))
        if parser._enable_kernel_compare:
            self.assertTrue(hasattr(parser.result_data, 'kernel_details'))

    def test_query_compute_op_data_given_use_kernel_type_true(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        parser._args.use_kernel_type = True
        parser._query_compute_op_data()
        self.assertTrue(hasattr(parser.result_data, 'kernel_dict'))
        if parser._enable_kernel_compare:
            self.assertTrue(hasattr(parser.result_data, 'kernel_details'))

    def test_query_comm_data(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        parser._query_comm_op_data()
        parser._query_comm_task_data()

        self.assertGreater(len(parser.comm_op_data), 0)
        self.assertIsInstance(parser.comm_op_data[0], HcclOpBean)
        self.assertGreater(len(parser.comm_task_data), 0)
        self.assertIsInstance(parser.comm_task_data[0], HcclTaskBean)

    def test_query_memory_data(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        parser._query_memory_data()

        self.assertTrue(hasattr(parser.result_data, 'memory_list'))

    def test_update_memory_data(self):
        parser = NPUProfilingDbParser(self.args, self.path_dict)
        memory_data = (
            {"opName": "cann::add", "size": 512, "allocationTime": 3, "releaseTime": 6, "duration": 5},
            {"opName": "cann::matmul", "size": 82, "allocationTime": 7, "releaseTime": 9, "duration": 5},
        )
        task_queue_data = [
            {Constant.TS: 0, Constant.START_NS: 4, Constant.END_NS: 6},
            {Constant.TS: 1, Constant.START_NS: 5, Constant.END_NS: 8}
        ]
        parser._update_memory_data(memory_data, task_queue_data)
        self.assertEqual(1, len(parser.result_data.memory_list))
