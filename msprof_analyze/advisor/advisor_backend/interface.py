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
        Constant.OVERALL: OverallAdviceFactory
    }

    def __init__(self, collection_path: str):
        self.collection_path = os.path.abspath(collection_path)
        self.temp_input_path = None

    def create_advice_factory(self, mode: str, input_path: str):
        collection_path = input_path if input_path else self.collection_path
        return self.FACTORY_LIB.get(mode)(collection_path)
