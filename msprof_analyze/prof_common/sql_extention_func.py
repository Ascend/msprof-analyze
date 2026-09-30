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

import numpy as np


class Median:
    def __init__(self) -> None:
        self.data = []

    def step(self, value) -> None:
        self.data.append(value)

    def finalize(self):
        return np.median(self.data)


class LowerQuartile:
    def __init__(self) -> None:
        self.data = []

    def step(self, value) -> None:
        self.data.append(value)

    def finalize(self):
        return np.quantile(self.data, 0.25)


class UpperQuartile:
    def __init__(self) -> None:
        self.data = []

    def step(self, value) -> None:
        self.data.append(value)

    def finalize(self):
        return np.quantile(self.data, 0.75)


class StandardDeviation:
    def __init__(self) -> None:
        self.data = []

    def step(self, value) -> None:
        self.data.append(value)

    def finalize(self):
        return np.std(self.data)


# func_name, params_count, class
SqlExtentionAggregateFunc = [
    ('median', 1, Median),
    ('lower_quartile', 1, LowerQuartile),
    ('upper_quartile', 1, UpperQuartile),
    ('stdev', 1, StandardDeviation),
]
