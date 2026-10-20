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
import re
from collections import defaultdict

from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.prof_common.utils import compute_ratio

logger = get_logger()


class MsprofCommunicationMatrixAdapter:
    P2P_HCOM = ["hcom_send", "hcom_receive", "hcom_batchsendrecv"]
    HCCL_PATTERN = (
        r"send|reduce|invalid|broadcast|allreduce|"
        r"receive|allgather|reducescatter|scatter|alltoall|alltoallv|alltoallvc|batchsendrecv"
    )
    BANDWIDTH_GB_S = "Bandwidth(GB/s)"
    TRANSPORT_TYPE = "Transport Type"
    TRANSIT_SIZE_MB = "Transit Size(MB)"
    TRANSIT_TIME_MS = "Transit Time(ms)"

    def __init__(self, file_path):
        self.file_path = file_path

    def generate_comm_matrix_data(self):
        output_comm_matrix = {"step": {Constant.P2P: {}, Constant.COLLECTIVE: {}}}
        comm_matrix_data = FileManager.read_json_file(self.file_path)
        split_comm_dict = {Constant.P2P: {}, Constant.COLLECTIVE: {}}
        for communication_op, comm_matrix_info in comm_matrix_data.items():
            lower_op_name = communication_op.lower()
            if any(lower_op_name.startswith(start_str) for start_str in self.P2P_HCOM):
                split_comm_dict[Constant.P2P][communication_op] = comm_matrix_info
            elif lower_op_name.startswith(Constant.TOTAL):
                continue
            else:
                split_comm_dict[Constant.COLLECTIVE][communication_op] = comm_matrix_info
        output_comm_matrix["step"][Constant.P2P] = self.integrate_matrix_data(
            self.get_comm_type(split_comm_dict[Constant.P2P])
        )
        output_comm_matrix["step"][Constant.COLLECTIVE] = self.integrate_matrix_data(
            self.get_comm_type(split_comm_dict[Constant.COLLECTIVE])
        )
        return output_comm_matrix

    def get_comm_type(self, op_data: dict) -> dict:
        new_comm_op_dict = defaultdict(list)
        for communication_op, communication_info in op_data.items():
            match_obj = re.compile(self.HCCL_PATTERN).search((communication_op.lower()))
            if match_obj:
                comm_op_type = match_obj.group()
            else:
                comm_op_type = communication_op.split("__")[0]
                logger.warning("Unknown communication op type: %s", comm_op_type)
            for link, data in communication_info.items():
                new_comm_op_name = (comm_op_type, communication_op.split("@")[-1], link)
                data['Op Name'] = communication_op.split("@")[0]
                new_comm_op_dict[new_comm_op_name].append(data)
        return new_comm_op_dict

    def integrate_matrix_data(self, new_comm_op_dict: dict):
        """integrate the matrix data"""
        comm_op_dict = defaultdict(dict)
        for new_comm_op_name, data in new_comm_op_dict.items():
            data.sort(key=lambda x: x[self.BANDWIDTH_GB_S], reverse=True)
            t_type = data[0].get(self.TRANSPORT_TYPE, '')
            t_size = sum(x.get(self.TRANSIT_SIZE_MB, 0) for x in data)
            t_time = sum(x.get(self.TRANSIT_TIME_MS, 0) for x in data)
            bandwidth = compute_ratio(t_size, t_time)

            link = new_comm_op_name[2]
            new_comm_op_name_top1 = f'{new_comm_op_name[0]}-top1@{new_comm_op_name[1]}'
            new_comm_op_name_middle = f'{new_comm_op_name[0]}-middle@{new_comm_op_name[1]}'
            new_comm_op_name_bottom1 = f'{new_comm_op_name[0]}-bottom1@{new_comm_op_name[1]}'
            new_comm_op_name_bottom2 = f'{new_comm_op_name[0]}-bottom2@{new_comm_op_name[1]}'
            new_comm_op_name_bottom3 = f'{new_comm_op_name[0]}-bottom3@{new_comm_op_name[1]}'
            new_comm_op_name_total = f'{new_comm_op_name[0]}-total@{new_comm_op_name[1]}'
            comm_op_dict[new_comm_op_name_top1].update({link: data[0]})
            comm_op_dict[new_comm_op_name_middle].update({link: data[len(data) // 2]})
            comm_op_dict[new_comm_op_name_bottom1].update({link: data[-1]})
            comm_op_dict[new_comm_op_name_total].update(
                {
                    link: {
                        self.TRANSPORT_TYPE: t_type,
                        self.TRANSIT_SIZE_MB: t_size,
                        self.TRANSIT_TIME_MS: t_time,
                        self.BANDWIDTH_GB_S: bandwidth,
                    }
                }
            )
            if len(data) >= 2:
                comm_op_dict[new_comm_op_name_bottom2].update({link: data[-2]})
            if len(data) >= 3:
                comm_op_dict[new_comm_op_name_bottom3].update({link: data[-3]})
        return comm_op_dict
