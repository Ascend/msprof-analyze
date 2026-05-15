# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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
from abc import ABC
import multiprocessing
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset

logger = get_logger()


class TimelineBaseChecker(ABC):

    def __init__(self, n_processes: int = 1):
        self.n_processes = n_processes
        self._matched_op_index = {} if self.n_processes <= 1 else multiprocessing.Manager().dict()
        self.matched_op_stacks = {}
        self.empty_stacks = True
        self.framework_black_list = False

    def query_stack(self, event_dataset: ScheduleAnalysisDataset = None, profiling_with_stack: str = None):
        if all([len(matched_index) == 0 for matched_index in self._matched_op_index.values()]):
            return

        event_dataset = event_dataset if not profiling_with_stack else ScheduleAnalysisDataset(
            collection_path=profiling_with_stack, data={}, _datasets={}, analysis_mode="fusion_ops",
            build_dataset=False)

        op_stack_list = event_dataset.parse_data_with_generator(self._query_stack_by_matched_index)
        for op_stack in op_stack_list:
            for op, stack in op_stack.items():
                if op not in self.matched_op_stacks:
                    self.matched_op_stacks[op] = {}
                if stack == Constant.TIMELINE_FUSION_OPS_NO_STACK_FLAG:
                    continue
                if stack not in self.matched_op_stacks[op]:
                    self.matched_op_stacks[op][stack] = 0
                self.matched_op_stacks[op][stack] += 1

    def _query_stack_by_matched_index(self, index, event):
        stack_record = {}
        event = TimelineEvent(event)

        matched_ops = []
        for op, matched_index in self._matched_op_index.items():
            if index not in matched_index:
                continue

            matched_ops.append(op)
            stack = event.args.get(Constant.CALL_STACKS)

            if not stack:
                logger.debug("Got empty '%s' for event %s", Constant.CALL_STACKS, event)
                continue

            if not self._is_keep_stack(stack):
                self.framework_black_list = True
                logger.debug("Drop stack from framework %s", Constant.FRAMEWORK_STACK_BLACK_LIST)
                continue

            if self.empty_stacks and stack:
                self.empty_stacks = False

            stack_record[op] = stack

        if matched_ops and not stack_record:
            for op in matched_ops:
                stack_record[op] = Constant.TIMELINE_FUSION_OPS_NO_STACK_FLAG

        return stack_record

    def _is_keep_stack(self, stack):
        # 过滤掉torch, torch_npu, megatron, deepspeed等框架下的堆栈，这些源码基本是不能被修改的
        stack_list = stack.replace("\\r\\n", ";").split(";")
        if not stack_list:
            return False

        final_called_stack = stack_list[0]
        for framework in Constant.FRAMEWORK_STACK_BLACK_LIST:
            if framework in final_called_stack.split("/"):
                return False
        return True
