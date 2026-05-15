# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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
import json
from msprof_analyze.prof_common.logger import get_logger
import os
from collections import defaultdict

import numpy as np
import pandas as pd
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.cluster_analyse.common_func.table_constant import TableConstant
from msprof_analyze.prof_common.singleton import singleton
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.advisor.dataset.cluster.hccl_collection import HcclInfo
from msprof_analyze.advisor.utils.utils import CheckPathAccess
from msprof_analyze.advisor.dataset.dataset import Dataset
from msprof_analyze.prof_exports.communicaion_info_export import CommunicationInfoExport

logger = get_logger()


@singleton
class CommunicationDataset(Dataset):
    RANK = "rank"
    hccl_dict = defaultdict(list)

    def __init__(self, collection_path, data: dict, **kwargs) -> None:
        self.collection_path = collection_path
        self.communication_file = ""
        self.hccl_dict = defaultdict(list)
        self.step = kwargs.get("step")
        super().__init__(collection_path, data, **kwargs)

    @staticmethod
    def load_json_data(json_path):
        if not os.path.exists(json_path):
            msg = "[ERROR] cluster_communication.json doesn't exist, terminate analysis."
            raise RuntimeError(msg)
        data = FileManager.read_json_file(json_path)
        return data

    @staticmethod
    @CheckPathAccess
    def get_file_path_from_directory(path, check_func):
        """
        get file from directory
        """
        file_list = []

        if not path:
            return file_list

        if not os.path.isdir(path):
            logger.warning("Expected existed directory, but got %s", path)

        for root, _, files in PathManager.limited_depth_walk(path):
            if os.path.basename(root) != "ASCEND_PROFILER_OUTPUT":
                continue
            for filename in files:
                filepath = os.path.join(root, filename)
                if check_func(filename):
                    file_list.append(filepath)
        return file_list

    @classmethod
    def get_key(cls):
        """
        get key of dataset
        :return: key
        """
        return cls.__module__.rsplit('.', maxsplit=1)[-1]

    def get_communication_file_list(self):
        file_name = ""
        if self.data_type == Constant.TEXT:
            file_name = Constant.COMMUNICATION_JSON
        elif self.data_type == Constant.DB:
            file_name = Constant.DB_COMMUNICATION_ANALYZER if self.collection_path.endswith("ascend_pt") \
                        else Constant.DB_MS_COMMUNICATION_ANALYZER
        if not file_name:
            logger.error("Invalid collection path, can not get communication file name pattern")
            return False

        communication_data_list = self.get_file_path_from_directory(
            self.collection_path,
            lambda file: file.endswith(file_name)
        )
        if len(communication_data_list) == 0:
            logger.warning(f"Please ensure {file_name} in {self.collection_path}, skip timeline analysis.")
            return False
        if len(communication_data_list) > 1:
            logger.warning(f"Found multiple {file_name} in {self.collection_path}, "
                           f"load the file of device 0 for analysis.")
        self.communication_file = sorted(communication_data_list)[0]
        return True


    def parse_from_text(self):
        json_data = self.load_json_data(self.communication_file)
        self.process_communication_json(json_data)
        return True

    def process_communication_json(self, communication_json: dict):
        for step, step_dict in communication_json.items():
            for group, group_dict in step_dict.items():
                for op, op_dict in group_dict.items():
                    self.process_hccl_info(group, step, op, op_dict)

    def process_hccl_info(self, group, step, op, op_dict):
        try:
            hccl_info = HcclInfo.construct_instance_from_dict(group, step, "None", op, op_dict)
            if self.hccl_dict.get(step) is None:
                self.hccl_dict.setdefault(step, list())
            self.hccl_dict[step].append(hccl_info)
        except ValueError as e:
            msg = "[ERROR] Cluster_communication.json has invalid structure."
            raise ValueError(msg) from e

    def parse_from_db(self):
        expected_tables = [Constant.TABLE_COMM_ANALYZER_TIME, Constant.TABLE_COMM_ANALYZER_BANDWIDTH]
        if not DBManager.check_tables_in_db(self.communication_file, *expected_tables):
            logger.warning(f"Communication tables: {expected_tables} not found in {self.communication_file}")
            return False
        is_pta = self.collection_path.endswith("ascend_pt")
        export = CommunicationInfoExport(self.communication_file, is_pta)
        df = export.read_export_db()
        if TableConstant.STEP not in df.columns:
            df[TableConstant.STEP] = 'step'
        if TableConstant.TYPE not in df.columns:
            is_p2p = df[TableConstant.HCCL_OP_NAME].str.lower().str.contains('send|receive|recv', regex=True)
            df[Constant.TYPE] = np.where(is_p2p, Constant.P2P, Constant.COLLECTIVE)

        df['sdma_dict'] = df['sdma_dict'].apply(lambda x: json.loads(x) if pd.notna(x) else {})
        df['rdma_dict'] = df['rdma_dict'].apply(lambda x: json.loads(x) if pd.notna(x) else {})
        for row in df.itertuples(index=False):
            self.hccl_dict[row.step].append(HcclInfo(row.type, row.step, "None", row.hccl_op_name,
                                                     row.start_timestamp, row.elapse_time,
                                                     row.sdma_dict, row.rdma_dict))
        return True

    def _parse(self):
        if not self.get_communication_file_list():
            return False
        return self.parse_from_db() if self.data_type == Constant.DB else self.parse_from_text()