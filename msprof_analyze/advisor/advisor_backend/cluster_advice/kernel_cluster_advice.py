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

import os
import pandas as pd
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant as AdvisorConstant
from msprof_analyze.advisor.advisor_backend.cluster_advice.cluster_advice_base import ClusterAdviceBase
from msprof_analyze.cluster_analyse.cluster_data_preprocess.pytorch_data_preprocessor import PytorchDataPreprocessor
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.path_manager import PathManager


class KernelClusterAdvice(ClusterAdviceBase):
    COLUMNS_TO_GROUP = ["Name", "Input Shapes", "Input Data Types", "Output Shapes"]
    COLUMNS_TO_CAL = ["Duration(us)"]
    CAL_FUN = ['mean', 'var', 'max', 'min', 'count', 'sum']

    def __init__(self, collection_path: str, kwargs: dict = None):
        super().__init__(collection_path)
        self.all_kernel_data = pd.DataFrame()

    def run(self):
        self.load_kernel_details_data()
        return self.calculate_data()

    def load_kernel_details_data(self):
        prof_dirs = self.get_prof_dirs(self.collection_path)
        if not prof_dirs:
            msg = "[ERROR] There is no profile in this collection path, terminate analysis."
            raise RuntimeError(msg)

        data_map = PytorchDataPreprocessor(prof_dirs).get_data_map()
        self.all_kernel_data = pd.DataFrame()
        for rank_id, profiling_dir_path in data_map.items():
            kernel_file = os.path.join(profiling_dir_path, Constant.SINGLE_OUTPUT, Constant.KERNEL_DETAILS_CSV)
            if kernel_file:
                # 判断csv文件大小
                FileManager.check_file_size(kernel_file)
                PathManager.check_input_file_path(kernel_file)
                # 读取CSV文件
                df_temp = pd.read_csv(kernel_file)
                columns_to_keep = self.COLUMNS_TO_GROUP + self.COLUMNS_TO_CAL
                if [1 for element in columns_to_keep if element not in list(df_temp)]:
                    msg = "[ERROR] Kernel details.csv has wrong data columns, terminate analysis."
                    raise RuntimeError(msg)
                df = df_temp[columns_to_keep]
                df.insert(loc=0, column='rank id', value=rank_id)
                # 将数据添加到最终的数据框中
                self.all_kernel_data = pd.concat([self.all_kernel_data, df], ignore_index=True)

    def calculate_data(self):
        # 存储所有合并后的数据
        calculate_dict = {self.COLUMNS_TO_CAL[i]: self.CAL_FUN for i in range(len(self.COLUMNS_TO_CAL))}
        group_col = ["rank id"] + self.COLUMNS_TO_GROUP
        view_data = self.all_kernel_data.groupby(group_col).agg(calculate_dict).reset_index()
        view_data.columns = [''.join(col) if col[1] == "" else '_'.join(col) for col in view_data.columns]
        return view_data

    def get_prof_dirs(self, collection_path):
        prof_dirs = []
        for prof_dir in os.listdir(collection_path):
            if prof_dir.endswith(AdvisorConstant.PT_PROF_SUFFIX):
                prof_dirs.append(os.path.join(collection_path, prof_dir))

        return prof_dirs

    def output(self):
        raise NotImplementedError
