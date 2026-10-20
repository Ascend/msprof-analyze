# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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
import copy
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.prof_common.constant import Constant


class DataTransferAdapter:
    COMM_TIME_TABLE_COLUMN = [
        TableConstant.START_TIMESTAMP,
        TableConstant.ELAPSED_TIME,
        TableConstant.TRANSIT_TIME,
        TableConstant.WAIT_TIME,
        TableConstant.SYNCHRONIZATION_TIME,
        TableConstant.IDLE_TIME,
        TableConstant.SYNCHRONIZATION_TIME_RATIO,
        TableConstant.WAIT_TIME_RATIO,
    ]
    COMM_TIME_JSON_COLUMN = [
        Constant.START_TIMESTAMP,
        Constant.ELAPSE_TIME_MS,
        Constant.TRANSIT_TIME_MS,
        Constant.WAIT_TIME_MS,
        Constant.SYNCHRONIZATION_TIME_MS,
        Constant.IDLE_TIME_MS,
        Constant.SYNCHRONIZATION_TIME_RATIO,
        Constant.WAIT_TIME_RATIO,
    ]
    MATRIX_TABLE_COLUMN = [
        TableConstant.TRANSIT_SIZE,
        TableConstant.TRANSIT_TIME,
        TableConstant.BANDWIDTH,
        TableConstant.TRANSPORT_TYPE,
        TableConstant.OPNAME,
    ]
    MATRIX_JSON_COLUMN = [
        Constant.TRANSIT_SIZE_MB,
        Constant.TRANSIT_TIME_MS,
        Constant.BANDWIDTH_GB_S,
        Constant.TRANSPORT_TYPE,
        Constant.OP_NAME,
    ]
    COMM_BD_TABLE_COLUMN = [
        TableConstant.TRANSIT_SIZE,
        TableConstant.TRANSIT_TIME,
        TableConstant.BANDWIDTH,
        TableConstant.LARGE_PACKET_RATIO,
    ]
    COMM_BD_JSON_COLUMN = [
        Constant.TRANSIT_SIZE_MB,
        Constant.TRANSIT_TIME_MS,
        Constant.BANDWIDTH_GB_S,
        Constant.LARGE_PACKET_RATIO,
    ]

    def transfer_comm_from_db_to_json(self, time_info: list, bandwidth_info: list):
        result = {}
        if not time_info and not bandwidth_info:
            return result
        for time_data in time_info:
            comm_time = dict()
            hccl_name = time_data[TableConstant.HCCL_OP_NAME] + "@" + time_data[TableConstant.GROUP_NAME]
            for key, value in dict(zip(self.COMM_TIME_JSON_COLUMN, self.COMM_TIME_TABLE_COLUMN)).items():
                if not key.endswith("ratio"):
                    comm_time[key] = time_data.get(value, 0)
            result.setdefault(time_data[TableConstant.STEP], {}).setdefault(
                time_data[TableConstant.TYPE], {}
            ).setdefault(hccl_name, {})[Constant.COMMUNICATION_TIME_INFO] = comm_time
        hccl_set = set()
        for bd_data in bandwidth_info:
            hccl_name = bd_data[TableConstant.HCCL_OP_NAME] + "@" + bd_data[TableConstant.GROUP_NAME]
            hccl_set.add(hccl_name)
        for hccl in hccl_set:
            comm_bd = dict()
            for bd_data in bandwidth_info:
                if hccl == (bd_data[TableConstant.HCCL_OP_NAME] + "@" + bd_data[TableConstant.GROUP_NAME]):
                    temp_dict = dict()
                    key_dict = dict(zip(self.COMM_BD_JSON_COLUMN, self.COMM_BD_TABLE_COLUMN))
                    self.set_value_by_key(temp_dict, bd_data, key_dict)
                    comm_bd.setdefault(bd_data[TableConstant.TRANSPORT_TYPE], temp_dict).setdefault(
                        Constant.SIZE_DISTRIBUTION, {}
                    )[bd_data[TableConstant.PACKAGE_SIZE]] = [
                        bd_data[TableConstant.COUNT],
                        bd_data[TableConstant.TOTAL_DURATION],
                    ]
                    result.setdefault(bd_data[TableConstant.STEP], {}).setdefault(
                        bd_data[TableConstant.TYPE], {}
                    ).setdefault(hccl, {})[Constant.COMMUNICATION_BANDWIDTH_INFO] = comm_bd
        return result

    def transfer_comm_from_json_to_db(self, res_data: dict):
        res_comm_data, res_bd_data = [], []

        def split_comm_time(rank_set, step, op_name, op_data):
            for rank_id, comm_data in op_data.items():
                time_data = comm_data.get(Constant.COMMUNICATION_TIME_INFO)
                res_time = set_only_value(rank_set, step, op_name, rank_id)
                for key, value in dict(zip(self.COMM_TIME_TABLE_COLUMN, self.COMM_TIME_JSON_COLUMN)).items():
                    res_time[key] = time_data.get(value, 0)
                res_comm_data.append(res_time)
                bd_data = comm_data.get(Constant.COMMUNICATION_BANDWIDTH_INFO, {})
                for transport_type, data in bd_data.items():
                    res_bandwidth = set_only_value(rank_set, step, op_name, rank_id)
                    key_dict = dict(zip(self.COMM_BD_TABLE_COLUMN, self.COMM_BD_JSON_COLUMN))
                    res_bandwidth[TableConstant.TRANSPORT_TYPE] = transport_type
                    self.set_value_by_key(res_bandwidth, data, key_dict)
                    for key, value in data.get(Constant.SIZE_DISTRIBUTION, {}).items():
                        res_bandwidth[TableConstant.PACKAGE_SIZE] = key
                        res_bandwidth[TableConstant.COUNT] = value[0]
                        res_bandwidth[TableConstant.TOTAL_DURATION] = value[1]
                        temp_dict = copy.deepcopy(res_bandwidth)
                        res_bd_data.append(temp_dict)

        def set_only_value(rank_set, step, op_name, rank_id):
            res_dict = dict()
            res_dict[TableConstant.RANK_SET] = str(rank_set)
            res_dict[TableConstant.STEP] = step
            res_dict[TableConstant.RANK_ID] = rank_id
            res_dict[TableConstant.HCCL_OP_NAME] = op_name.split("@")[0] if "@" in op_name else op_name
            res_dict[TableConstant.GROUP_NAME] = op_name.split("@")[1] if "@" in op_name else ""
            return res_dict

        for rank_set, step_dict in res_data.items():
            for step, op_dict in step_dict.items():
                for op_name, op_data in op_dict.items():
                    split_comm_time(rank_set, step, op_name, op_data)
        return res_comm_data, res_bd_data

    def set_value_by_key(self, src_dict, dst_dict, key_dict):
        for key, value in key_dict.items():
            src_dict[key] = dst_dict.get(value, 0)

    def transfer_matrix_from_db_to_json(self, matrix_data: list):
        result = {}
        if not matrix_data:
            return result
        hccl_set = set()
        for data in matrix_data:
            hccl = data[TableConstant.HCCL_OP_NAME] + "@" + data[TableConstant.GROUP_NAME]
            hccl_set.add(hccl)
        for hccl in hccl_set:
            for data in matrix_data:
                if hccl == (data[TableConstant.HCCL_OP_NAME] + "@" + data[TableConstant.GROUP_NAME]):
                    key = data[TableConstant.SRC_RANK] + '-' + data[TableConstant.DST_RANK]
                    temp_dict = dict()
                    key_dict = dict(zip(self.MATRIX_JSON_COLUMN, self.MATRIX_TABLE_COLUMN))
                    self.set_value_by_key(temp_dict, data, key_dict)
                    result.setdefault(data[TableConstant.STEP], {}).setdefault(data[TableConstant.TYPE], {}).setdefault(
                        hccl, {}
                    ).setdefault(key, temp_dict)
        return result

    def transfer_matrix_from_json_to_db(self, res_data: dict):
        result = []

        def split_matrix_data(rank_set, step, op_dict):
            group_name = ""
            for op_name, op_data in op_dict.items():
                for link_key, link_data in op_data.items():
                    if "@" in op_name:
                        hccl_op_name, group_name = op_name.split("@")[0], op_name.split("@")[1]
                    else:
                        hccl_op_name = op_name
                    matrix_data = {
                        TableConstant.RANK_SET: str(rank_set),
                        TableConstant.STEP: step,
                        TableConstant.HCCL_OP_NAME: hccl_op_name,
                        TableConstant.GROUP_NAME: group_name,
                        TableConstant.SRC_RANK: link_key.split("-")[0],
                        TableConstant.DST_RANK: link_key.split("-")[1],
                    }
                    key_dict = dict(zip(self.MATRIX_TABLE_COLUMN, self.MATRIX_JSON_COLUMN))
                    self.set_value_by_key(matrix_data, link_data, key_dict)
                    result.append(matrix_data)

        for rank_set, step_dict in res_data.items():
            for step, op_dict in step_dict.items():
                split_matrix_data(rank_set, step, op_dict)
        return result
