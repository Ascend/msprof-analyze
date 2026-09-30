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


class ClusterStepTraceTimeBean:
    STEP = "Step"
    TYPE = "Type"
    INDEX = "Index"
    COMPUTING = "Computing"
    COMMUNICATION = "Communication(Not Overlapped)"
    FREE = "Free"

    def __init__(self, data: dict):
        self._data = data

    @property
    def step(self) -> str:
        return self._data.get(self.STEP, '')

    @property
    def type(self) -> str:
        return self._data.get(self.TYPE, '')

    @property
    def index(self) -> int:
        try:
            return int(self._data.get(self.INDEX))
        except ValueError as e:
            msg = "[ERROR] Cluster step trace time.csv has invalid value in column 'Index'."
            raise ValueError(msg) from e

    @property
    def compute(self) -> float:
        try:
            return float(self._data.get(self.COMPUTING, ''))
        except ValueError as e:
            msg = "[ERROR] Cluster step trace time.csv has invalid value in column 'Computing'."
            raise ValueError(msg) from e

    @property
    def communication(self) -> float:
        try:
            return float(self._data.get(self.COMMUNICATION, ''))
        except ValueError as e:
            msg = "[ERROR] Cluster step trace time.csv has invalid value in column 'Communication'."
            raise ValueError(msg) from e

    @property
    def free(self) -> float:
        try:
            return float(self._data.get(self.FREE, ''))
        except ValueError as e:
            msg = "[ERROR] Cluster step trace time.csv has invalid value in column 'Free'."
            raise ValueError(msg) from e
