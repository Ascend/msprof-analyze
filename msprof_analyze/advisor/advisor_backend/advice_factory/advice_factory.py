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

from msprof_analyze.prof_common.path_manager import PathManager


class AdviceFactory:
    ADVICE_LIB = {}

    def __init__(self, collection_path: str):
        self.collection_path = os.path.abspath(collection_path)

    def run_advice(self, advice: str, kwargs: dict):
        """
        run advice to produce data
        """

    def produce_advice(self, advice: str, kwargs: dict):
        """
        produce data for input mode and advice
        """
        self.path_check()
        self.advice_check(advice)
        return self.run_advice(advice, kwargs)

    def path_check(self):
        """
        check whether input path is valid
        """
        PathManager.input_path_common_check(self.collection_path)

    def advice_check(self, advice: str):
        """
        check whether input advice is valid
        """
        if advice not in self.ADVICE_LIB:
            msg = '[ERROR]Input advice is illegal.'
            raise RuntimeError(msg)
