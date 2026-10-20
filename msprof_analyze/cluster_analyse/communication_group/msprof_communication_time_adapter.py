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
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.constant import Constant


class MsprofCommunicationTimeAdapter:
    P2P_HCOM = ["hcom_send", "hcom_receive", "hcom_batchsendrecv"]
    TOTAL = "total"

    def __init__(self, file_path):
        self.file_path = file_path

    def generate_comm_time_data(self):
        output_communication = {"step": {Constant.P2P: {}, Constant.COLLECTIVE: {}}}
        communication_data = FileManager.read_json_file(self.file_path)
        for communication_op, communication_info in communication_data.items():
            lower_op_name = communication_op.lower()
            if any(lower_op_name.startswith(start_str) for start_str in self.P2P_HCOM):
                output_communication["step"][Constant.P2P][communication_op] = communication_info
            elif lower_op_name.startswith(self.TOTAL):
                continue
            else:
                output_communication["step"][Constant.COLLECTIVE][communication_op] = communication_info

        return output_communication
