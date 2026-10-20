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
from abc import ABC, abstractmethod
from collections import OrderedDict
from multiprocessing import Process


class BaseGenerator(Process, ABC):
    def __init__(self, profiling_data_dict: dict, args: any):
        super().__init__()
        self._profiling_data_dict = profiling_data_dict
        self._args = args
        self._result_data = OrderedDict()

    def run(self):
        self.compare()
        self.generate_view()

    @abstractmethod
    def compare(self):
        raise NotImplementedError("Function compare need to be implemented.")

    @abstractmethod
    def generate_view(self):
        raise NotImplementedError("Function generate_view need to be implemented.")
