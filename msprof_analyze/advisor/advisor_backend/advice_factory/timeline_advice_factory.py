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
from msprof_analyze.advisor.advisor_backend.advice_factory.advice_factory import AdviceFactory
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant
from msprof_analyze.advisor.advisor_backend.timeline_advice.optimizer_advice import OptimizerAdvice
from msprof_analyze.advisor.advisor_backend.timeline_advice.op_schedule_advice import OpScheduleAdvice


class TimelineAdviceFactory(AdviceFactory):
    ADVICE_LIB = {
        Constant.OPTIM: OptimizerAdvice,
        Constant.OP_SCHE: OpScheduleAdvice,
    }

    def run_advice(self, advice: str, kwargs: dict):
        """
        run advice to produce data
        """
        return self.ADVICE_LIB.get(advice)(self.collection_path).run()
