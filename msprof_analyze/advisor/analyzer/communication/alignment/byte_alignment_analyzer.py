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
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.analyzer.communication.alignment.byte_alignment_checker import ByteAlignmentChecker
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.dataset.profiling.profiling_dataset import ProfilingDataset
from msprof_analyze.advisor.dataset.communication.hccl_detail_dataset import HcclDetailDataset
from msprof_analyze.advisor.result.result import OptimizeResult

logger = get_logger()


class ByteAlignmentAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ProfilingDataset]
    requires_cluster_dataset = False

    def __init__(self, collection_path, n_processes: int = 1, **kwargs) -> None:
        super().__init__(collection_path, n_processes, **kwargs)
        profiling_key = ProfilingDataset.get_key()
        self.profiling_dataset = self.get_first_data_by_key(self.dataset_list, profiling_key)
        self.hccl_detail_dataset = HcclDetailDataset(self.profiling_dataset.msprof)
        self.result = OptimizeResult()
        self.html_render = HTMLRender()
        self.html = None

    @BaseAnalyzer.check_data((ProfilingDataset.get_key(),))
    def optimize(self, **kwargs):
        byte_alignment_checker = ByteAlignmentChecker(**kwargs)
        byte_alignment_checker.check_alignment(self.hccl_detail_dataset)
        if not byte_alignment_checker.byge_alignment_issue:
            return self.result
        byte_alignment_checker.make_record(self.result)
        self.html = byte_alignment_checker.make_render(self.html_render, priority=self.get_priority())
        return self.result

    def get_priority(self, max_mem_op_dur=0):
        return PriorityBackgroundColor.medium
