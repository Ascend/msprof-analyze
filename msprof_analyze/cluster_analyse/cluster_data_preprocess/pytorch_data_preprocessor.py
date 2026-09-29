# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2023 Huawei Technologies Co.,Ltd.
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
from collections import defaultdict
import os

from msprof_analyze.cluster_analyse.cluster_data_preprocess.data_preprocessor import DataPreprocessor
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class PytorchDataPreprocessor(DataPreprocessor):
    @property
    def db_pattern(self):
        return r'^ascend_pytorch_profiler(?:_\d+)?\.db$'

    def get_data_map(self) -> dict:
        unknown_rank_paths = []
        rank_id_map = defaultdict(list)
        for dir_name in self.path_list:
            rank_id = self.get_rank_id(dir_name)
            if rank_id < 0:
                unknown_rank_paths.append(dir_name)
                continue
            ascend_profiler_output = os.path.join(dir_name, Constant.ASCEND_PROFILER_OUTPUT)
            if os.path.exists(ascend_profiler_output) and os.path.isdir(ascend_profiler_output):
                rank_id_map[rank_id].append(dir_name)
        self.data_map = self.postprocess_data_map(rank_id_map, Constant.PYTORCH)
        if unknown_rank_paths:
            logger.warning(
                "Failed to get rank_id for some paths."
                "Affected paths: %s\n"
                "Expected to get rank_id from profiler_info_{rank_id}.json",
                unknown_rank_paths,
            )
        return self.data_map
