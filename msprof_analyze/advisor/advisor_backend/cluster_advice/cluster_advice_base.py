# Copyright (c) 2023, Huawei Technologies Co., Ltd.
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
from abc import abstractmethod
from math import isclose

from msprof_analyze.advisor.advisor_backend.advice_base import AdviceBase
from msprof_analyze.cluster_analyse.cluster_analysis import Interface
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.constant import Constant

logger = get_logger()


class ClusterAdviceBase(AdviceBase):
    def __init__(self, collection_path: str):
        super().__init__(collection_path)

    @staticmethod
    def compute_max_gap_ratio(data: list, mean: float):
        if data and not isclose(mean, 0):
            return (max(data) - min(data)) / mean
        return 0

    def path_check(self):
        """
        check whether input path is valid
        """
        for file in os.listdir(self.collection_path):
            if file == 'cluster_analysis_output':
                logger.info("Cluster has been analyzed "
                            "because of the existence of cluster analysis output directory.")
                logger.info("Skip Cluster analyze backend.")
                return
        logger.info("cluster analysis is in the process, please wait...")
        self.cluster_analyze()

    def cluster_analyze(self):
        parameter = {
            Constant.COLLECTION_PATH: self.collection_path,
            Constant.ANALYSIS_MODE: "all"
        }
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
