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

from msprof_analyze.advisor.advisor_backend.timeline_advice.timeline_advice_base import TimelineAdviceBase


class OptimizerAdvice(TimelineAdviceBase):  # pylint: disable=abstract-method
    OPTIMIZER_MAP = {
        "Optimizer.step#SGD.step": "torch_npu.optim.NpuFusedSGD",
        "Optimizer.step#Adadelta.step": "torch_npu.optim.NpuFusedAdadelta",
        "Optimizer.step#Lamb.step": "torch_npu.optim.NpuFusedLamb",
        "Optimizer.step#Adam.step": "torch_npu.optim.NpuFusedAdam",
        "Optimizer.step#AdamW.step": "torch_npu.optim.NpuFusedAdamW",
        "Optimizer.step#AdamP.step": "torch_npu.optim.NpuFusedAdamP",
        "Optimizer.step#BertAdam.step": "torch_npu.optim.NpuFusedBertAdam",
        "Optimizer.step#RMSprop.step": "torch_npu.optim.NpuFusedRMSprop",
        "Optimizer.step#RMSpropTF.step": "torch_npu.optim.NpuFusedRMSpropTF",
    }

    def __init__(self, collection_path: str):
        super().__init__(collection_path)
        self.cur_data = []
        self.cur_bottleneck = str()
        self.cur_advice = str()

    def run(self):
        if not self.path_check():
            return self.output_format_data
        self.preparse()
        self.process()
        self.output()
        return self.output_format_data

    def process(self):
        if not self.preparse_data[self.PreParseType.OPTIMIZER]:
            return

        self.cur_data = list({entry.get("name", None) for entry in self.preparse_data[self.PreParseType.OPTIMIZER]})
        for index, opt_name in enumerate(self.cur_data):
            self.cur_advice += (
                f"You can choose {self.OPTIMIZER_MAP.get(opt_name)} to replace the current Optimizer: {opt_name}."
            )
            if index != len(self.cur_data) - 1:
                self.cur_advice += "\n"
        self.cur_bottleneck = self.cur_advice
