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

import os
from abc import abstractmethod
from math import isclose

from msprof_analyze.advisor.advisor_backend.advice_base import AdviceBase
from msprof_analyze.cluster_analyse.cluster_analysis import Interface
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.constant import Constant

logger = get_logger()


class ClusterAdviceBase(AdviceBase):
    @staticmethod
    def compute_max_gap_ratio(data: list, mean: float):
        if data and not isclose(mean, 0):
            return (max(data) - min(data)) / mean
        return 0

    def path_check(self, result_file):
        result_path = os.path.join(self.collection_path, Constant.CLUSTER_ANALYSIS_OUTPUT, result_file)
        if os.path.isfile(result_path):
            logger.info("Cluster analysis output already exists (%s). Skip backend analysis.", result_path)
            return
        logger.info("cluster analysis is in the process, please wait...")
        self.cluster_analyze()

    def cluster_analyze(self):
        parameter = {Constant.PROFILING_PATH: self.collection_path, Constant.MODE: "all"}
        try:
            Interface(parameter).run()
        except Exception as e:
            raise ValueError(f"Cluster analyze backend failed:{e}") from e

    @abstractmethod
    def run(self):
        """
        analyze profiling data and advice
        """

    @abstractmethod
    def output(self):
        """
        output relevant data
        """
