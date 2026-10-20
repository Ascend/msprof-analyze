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

import unittest

from msprof_analyze.cluster_analyse.cluster_utils.data_transfer_adapter import DataTransferAdapter
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.prof_common.constant import Constant


class TestDataTransferAdapter(unittest.TestCase):
    """
    DataTransferAdapter UTest
    DataTransferAdapter mainly inter-transfer data with database and json
    """

    def setUp(self):

        self.adapter = DataTransferAdapter()

        self.mock_time_info = [
            {
                TableConstant.STEP: "step_0",
                TableConstant.TYPE: "forward",
                TableConstant.HCCL_OP_NAME: "AllReduce",
                TableConstant.GROUP_NAME: "group_0",
                TableConstant.START_TIMESTAMP: 1000,
                TableConstant.ELAPSED_TIME: 100,
                TableConstant.TRANSIT_TIME: 50,
                TableConstant.WAIT_TIME: 30,
                TableConstant.SYNCHRONIZATION_TIME: 20,
                TableConstant.IDLE_TIME: 10,
                TableConstant.SYNCHRONIZATION_TIME_RATIO: 0.2,
                TableConstant.WAIT_TIME_RATIO: 0.3
            }
        ]

        self.mock_bandwidth_info = [
            {
                TableConstant.STEP: "step_0",
                TableConstant.TYPE: "forward",
                TableConstant.HCCL_OP_NAME: "AllReduce",
                TableConstant.GROUP_NAME: "group_0",
                TableConstant.TRANSPORT_TYPE: "RDMA",
                TableConstant.TRANSIT_SIZE: 1024,
                TableConstant.TRANSIT_TIME: 50,
                TableConstant.BANDWIDTH: 20.48,
                TableConstant.LARGE_PACKET_RATIO: 0.8,
                TableConstant.PACKAGE_SIZE: "1MB",
                TableConstant.COUNT: 10,
                TableConstant.TOTAL_DURATION: 500
            }
        ]

        self.mock_matrix_data = [
            {
                TableConstant.STEP: "step_0",
                TableConstant.TYPE: "forward",
                TableConstant.HCCL_OP_NAME: "AllReduce",
                TableConstant.GROUP_NAME: "group_0",
                TableConstant.SRC_RANK: "0",
                TableConstant.DST_RANK: "1",
                TableConstant.TRANSIT_SIZE: 1024,
                TableConstant.TRANSIT_TIME: 50,
                TableConstant.BANDWIDTH: 20.48,
                TableConstant.TRANSPORT_TYPE: "RDMA",
                TableConstant.OPNAME: "AllReduce"
            }
        ]

    def test_init(self):
        """
        test DataTransferAdapter init
        """
        adapter = DataTransferAdapter()
        self.assertIsInstance(adapter, DataTransferAdapter)

        self.assertIsInstance(adapter.COMM_TIME_TABLE_COLUMN, list)
        self.assertIsInstance(adapter.COMM_TIME_JSON_COLUMN, list)
        self.assertIsInstance(adapter.MATRIX_TABLE_COLUMN, list)
        self.assertIsInstance(adapter.MATRIX_JSON_COLUMN, list)
        self.assertIsInstance(adapter.COMM_BD_TABLE_COLUMN, list)
        self.assertIsInstance(adapter.COMM_BD_JSON_COLUMN, list)

    def test_transfer_comm_from_db_to_json_empty_data_success(self):
        """
        test from database to json with empty data
        """
        result = self.adapter.transfer_comm_from_db_to_json([], [])
        self.assertEqual(result, {})

        result = self.adapter.transfer_comm_from_db_to_json(None, None)
        self.assertEqual(result, {})


    def test_transfer_comm_from_db_to_json_both_info(self):
        """
        test from database to json with both time and bandwidth info
        """
        result = self.adapter.transfer_comm_from_db_to_json(self.mock_time_info, self.mock_bandwidth_info)

        expected_hccl_name = "AllReduce@group_0"

        # 验证时间信息
        self.assertIn(Constant.COMMUNICATION_TIME_INFO, result["step_0"]["forward"][expected_hccl_name])

        # 验证带宽信息
        self.assertIn(Constant.COMMUNICATION_BANDWIDTH_INFO, result["step_0"]["forward"][expected_hccl_name])

    def test_transfer_comm_from_json_to_db_empty_data_success(self):
        """
        test from json transfer to db with empty data
        """
        comm_data, bd_data = self.adapter.transfer_comm_from_json_to_db({})
        self.assertEqual(comm_data, [])
        self.assertEqual(bd_data, [])

    def test_transfer_comm_from_json_to_db_with_data_success(self):
        """
        test from json transfer to db with data
        """
        json_data = {
            "rank_set_0": {
                "step_0": {
                    "AllReduce@group_0": {
                        "rank0": {
                            Constant.COMMUNICATION_TIME_INFO: {
                                Constant.START_TIMESTAMP: 1000,
                                Constant.ELAPSE_TIME_MS: 100,
                                Constant.TRANSIT_TIME_MS: 50,
                                Constant.WAIT_TIME_MS: 30,
                                Constant.SYNCHRONIZATION_TIME_MS: 20,
                                Constant.IDLE_TIME_MS: 10,
                                Constant.SYNCHRONIZATION_TIME_RATIO: 0.2,
                                Constant.WAIT_TIME_RATIO: 0.3
                            },
                            Constant.COMMUNICATION_BANDWIDTH_INFO: {
                                "RDMA": {
                                    Constant.TRANSIT_SIZE_MB: 1024,
                                    Constant.TRANSIT_TIME_MS: 50,
                                    Constant.BANDWIDTH_GB_S: 20.48,
                                    Constant.LARGE_PACKET_RATIO: 0.8,
                                    Constant.SIZE_DISTRIBUTION: {
                                        "1MB": [10, 500]
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        comm_data, bd_data = self.adapter.transfer_comm_from_json_to_db(json_data)

        # 验证通信时间数据
        self.assertEqual(len(comm_data), 1)
        comm_record = comm_data[0]
        self.assertEqual(comm_record[TableConstant.RANK_SET], "rank_set_0")
        self.assertEqual(comm_record[TableConstant.STEP], "step_0")
        self.assertEqual(comm_record[TableConstant.HCCL_OP_NAME], "AllReduce")
        self.assertEqual(comm_record[TableConstant.GROUP_NAME], "group_0")
        self.assertEqual(comm_record[TableConstant.START_TIMESTAMP], 1000)
        self.assertEqual(comm_record[TableConstant.ELAPSED_TIME], 100)

        # 验证带宽数据
        self.assertEqual(len(bd_data), 1)
        bd_record = bd_data[0]
        self.assertEqual(bd_record[TableConstant.RANK_SET], "rank_set_0")
        self.assertEqual(bd_record[TableConstant.STEP], "step_0")
        self.assertEqual(bd_record[TableConstant.HCCL_OP_NAME], "AllReduce")
        self.assertEqual(bd_record[TableConstant.GROUP_NAME], "group_0")
        self.assertEqual(bd_record[TableConstant.TRANSPORT_TYPE], "RDMA")
        self.assertEqual(bd_record[TableConstant.TRANSIT_SIZE], 1024)
        self.assertEqual(bd_record[TableConstant.PACKAGE_SIZE], "1MB")
        self.assertEqual(bd_record[TableConstant.COUNT], 10)
        self.assertEqual(bd_record[TableConstant.TOTAL_DURATION], 500)

    def test_set_value_by_key(self):
        """
        test set value by key
        """
        src_dict = {}
        dst_dict = {
            TableConstant.TRANSIT_SIZE: 1024,
            TableConstant.TRANSIT_TIME: 50,
            TableConstant.BANDWIDTH: 20.48
        }
        key_dict = {
            Constant.TRANSIT_SIZE_MB: TableConstant.TRANSIT_SIZE,
            Constant.TRANSIT_TIME_MS: TableConstant.TRANSIT_TIME,
            Constant.BANDWIDTH_GB_S: TableConstant.BANDWIDTH
        }

        self.adapter.set_value_by_key(src_dict, dst_dict, key_dict)

        expected = {
            Constant.TRANSIT_SIZE_MB: 1024,
            Constant.TRANSIT_TIME_MS: 50,
            Constant.BANDWIDTH_GB_S: 20.48
        }
        self.assertEqual(src_dict, expected)

    def test_set_value_by_key_with_missing_values(self):
        """
        test set value by key with missing values
        """
        src_dict = {}
        dst_dict = {
            TableConstant.TRANSIT_SIZE: 1024
        }
        key_dict = {
            Constant.TRANSIT_SIZE_MB: TableConstant.TRANSIT_SIZE,
            Constant.TRANSIT_TIME_MS: TableConstant.TRANSIT_TIME,
            Constant.BANDWIDTH_GB_S: TableConstant.BANDWIDTH
        }

        self.adapter.set_value_by_key(src_dict, dst_dict, key_dict)

        expected = {
            Constant.TRANSIT_SIZE_MB: 1024,
            Constant.TRANSIT_TIME_MS: 0,
            Constant.BANDWIDTH_GB_S: 0
        }
        self.assertEqual(src_dict, expected)

    def test_transfer_matrix_from_db_to_json_empty_data(self):
        """
        test transfer matrix from db to json with empty data
        """
        result = self.adapter.transfer_matrix_from_db_to_json([])
        self.assertEqual(result, {})

        result = self.adapter.transfer_matrix_from_db_to_json(None)
        self.assertEqual(result, {})

    def test_transfer_matrix_from_db_to_json_with_data(self):
        """
        test transfer matrix from db to json with data
        """
        result = self.adapter.transfer_matrix_from_db_to_json(self.mock_matrix_data)

        expected_hccl_name = "AllReduce@group_0"
        expected_key = "0-1"
        expected_matrix_data = {
            Constant.TRANSIT_SIZE_MB: 1024,
            Constant.TRANSIT_TIME_MS: 50,
            Constant.BANDWIDTH_GB_S: 20.48,
            Constant.TRANSPORT_TYPE: "RDMA",
            Constant.OP_NAME: "AllReduce"
        }

        self.assertIn("step_0", result)
        self.assertIn("forward", result["step_0"])
        self.assertIn(expected_hccl_name, result["step_0"]["forward"])
        self.assertIn(expected_key, result["step_0"]["forward"][expected_hccl_name])
        self.assertEqual(result["step_0"]["forward"][expected_hccl_name][expected_key], expected_matrix_data)

    def test_transfer_matrix_from_json_to_db_empty_data(self):
        """
        test transfer matrix from json to db with empty data
        """
        result = self.adapter.transfer_matrix_from_json_to_db({})
        self.assertEqual(result, [])

    def test_transfer_matrix_from_json_to_db_with_data(self):
        """
        test transfer matrix from json to db with data
        """
        json_data = {
            "rank_set_0": {
                "step_0": {
                    "AllReduce@group_0": {
                        "0-1": {
                            Constant.TRANSIT_SIZE_MB: 1024,
                            Constant.TRANSIT_TIME_MS: 50,
                            Constant.BANDWIDTH_GB_S: 20.48,
                            Constant.TRANSPORT_TYPE: "RDMA",
                            Constant.OP_NAME: "AllReduce"
                        }
                    }
                }
            }
        }

        result = self.adapter.transfer_matrix_from_json_to_db(json_data)

        self.assertEqual(len(result), 1)
        matrix_record = result[0]

        self.assertEqual(matrix_record[TableConstant.RANK_SET], "rank_set_0")
        self.assertEqual(matrix_record[TableConstant.STEP], "step_0")
        self.assertEqual(matrix_record[TableConstant.HCCL_OP_NAME], "AllReduce")
        self.assertEqual(matrix_record[TableConstant.GROUP_NAME], "group_0")
        self.assertEqual(matrix_record[TableConstant.SRC_RANK], "0")
        self.assertEqual(matrix_record[TableConstant.DST_RANK], "1")
        self.assertEqual(matrix_record[TableConstant.TRANSIT_SIZE], 1024)
        self.assertEqual(matrix_record[TableConstant.TRANSIT_TIME], 50)
        self.assertEqual(matrix_record[TableConstant.BANDWIDTH], 20.48)
        self.assertEqual(matrix_record[TableConstant.TRANSPORT_TYPE], "RDMA")
        self.assertEqual(matrix_record[TableConstant.OPNAME], "AllReduce")

    def test_transfer_matrix_from_json_to_db_without_group_name_success(self):
        """
        test matrix from json to db without group name
        """
        json_data = {
            "rank_set_0": {
                "step_0": {
                    "AllReduce": {  # 没有@group_0
                        "0-1": {
                            Constant.TRANSIT_SIZE_MB: 1024,
                            Constant.TRANSIT_TIME_MS: 50
                        }
                    }
                }
            }
        }

        result = self.adapter.transfer_matrix_from_json_to_db(json_data)

        self.assertEqual(len(result), 1)
        matrix_record = result[0]
        self.assertEqual(matrix_record[TableConstant.HCCL_OP_NAME], "AllReduce")
        self.assertEqual(matrix_record[TableConstant.GROUP_NAME], "")

    def test_transfer_comm_from_json_to_db_without_ratio_fields_success(self):
        """
        test from json to db without ratio field
        """
        json_data = {
            "rank_set_0": {
                "step_0": {
                    "rank_0": {
                        "AllReduce@group_0": {
                            Constant.COMMUNICATION_TIME_INFO: {
                                Constant.START_TIMESTAMP: 1000,
                                Constant.ELAPSE_TIME_MS: 100
                                # no other param
                            }
                        }
                    }
                }
            }
        }

        comm_data, bd_data = self.adapter.transfer_comm_from_json_to_db(json_data)

        self.assertEqual(len(comm_data), 1)
        comm_record = comm_data[0]
        self.assertEqual(comm_record[TableConstant.START_TIMESTAMP], 1000)
        self.assertEqual(comm_record[TableConstant.ELAPSED_TIME], 100)
        # 其他字段应该为默认值0
        self.assertEqual(comm_record[TableConstant.TRANSIT_TIME], 0)
        self.assertEqual(comm_record[TableConstant.WAIT_TIME], 0)

    def test_transfer_comm_from_db_to_json_multiple_steps(self):
        """
        test from db to json multiple_steps
        """
        multi_step_time_info = [
            {
                TableConstant.STEP: "step_0",
                TableConstant.TYPE: "forward",
                TableConstant.HCCL_OP_NAME: "AllReduce",
                TableConstant.GROUP_NAME: "group_0",
                TableConstant.START_TIMESTAMP: 1000,
                TableConstant.ELAPSED_TIME: 100
            },
            {
                TableConstant.STEP: "step_1",
                TableConstant.TYPE: "backward",
                TableConstant.HCCL_OP_NAME: "AllGather",
                TableConstant.GROUP_NAME: "group_1",
                TableConstant.START_TIMESTAMP: 2000,
                TableConstant.ELAPSED_TIME: 200
            }
        ]

        result = self.adapter.transfer_comm_from_db_to_json(multi_step_time_info, [])

        # 验证两个步骤都存在
        self.assertIn("step_0", result)
        self.assertIn("step_1", result)
        self.assertIn("forward", result["step_0"])
        self.assertIn("backward", result["step_1"])

        # 验证不同的HCCL操作
        self.assertIn("AllReduce@group_0", result["step_0"]["forward"])
        self.assertIn("AllGather@group_1", result["step_1"]["backward"])
