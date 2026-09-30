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

from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant
from msprof_analyze.advisor.advisor_backend.advice_factory.cluster_advice_factory import ClusterAdviceFactory
from msprof_analyze.advisor.advisor_backend.advice_factory.compute_advice_factory import ComputeAdviceFactory
from msprof_analyze.advisor.advisor_backend.advice_factory.timeline_advice_factory import TimelineAdviceFactory
from msprof_analyze.advisor.advisor_backend.advice_factory.overall_advice_factory import OverallAdviceFactory


class Interface:
    def __init__(self, collection_path: str):
        self.collection_path = os.path.abspath(collection_path)
        self._factory_controller = FactoryController(collection_path)

    def get_data(self: any, mode: str, advice: str, **kwargs):
        if len(mode) > Constant.MAX_INPUT_MODE_LEN or len(advice) > Constant.MAX_INPUT_ADVICE_LEN:
            msg = '[ERROR]Input Mode is illegal.'
            raise RuntimeError(msg)
        factory = self._factory_controller.create_advice_factory(mode, kwargs.get("input_path", ""))
        return factory.produce_advice(advice, kwargs)


class FactoryController:
    FACTORY_LIB = {
        Constant.CLUSTER: ClusterAdviceFactory,
        Constant.COMPUTE: ComputeAdviceFactory,
        Constant.TIMELINE: TimelineAdviceFactory,
        Constant.OVERALL: OverallAdviceFactory,
    }

    def __init__(self, collection_path: str):
        self.collection_path = os.path.abspath(collection_path)
        self.temp_input_path = None

    def create_advice_factory(self, mode: str, input_path: str):
        collection_path = input_path if input_path else self.collection_path
        return self.FACTORY_LIB.get(mode)(collection_path)
