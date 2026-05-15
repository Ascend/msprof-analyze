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
from msprof_analyze.prof_common.logger import get_logger
from typing import List

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from msprof_analyze.advisor.dataset.timeline_event_dataset import ComputationAnalysisDataset
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.utils.utils import get_analyze_processes, ParallelJob
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()


class TimelineOpStackFinder:

    def __init__(self):
        self.n_processes = get_analyze_processes()
        self._stack_record = []
        self._task_id_record = {}
        self.op_name = None
        self.task_type = None
        self.matched_index = set()

    @staticmethod
    def _query_index_by_torch_to_npu(event_dataset, torch_to_npu_event):
        dst_op_event_key = torch_to_npu_event.ts
        dst_op_event = event_dataset.ops_with_stack.get(dst_op_event_key)

        if not dst_op_event:
            return Constant.TIMELINE_BACKWARD_NO_STACK_CODE

        return int(dst_op_event.get("dataset_index"))

    @staticmethod
    def _query_index_by_acl_to_npu(acl_to_npu_event):
        if acl_to_npu_event:
            return Constant.TIMELINE_ACL_TO_NPU_NO_STACK_CODE

        return Constant.TIMELINE_BACKWARD_NO_STACK_CODE

    def get_api_stack_by_op_name(self, event_dataset: ComputationAnalysisDataset, op_name: List[str] = None,
                                 task_type: str = None,
                                 disable_multiprocess=False):
        """
        :Param event_dataset: dataset of timeline event
        :Param op_name: operator name, e.g. IndexPutV2
        :Param task_type: operator task type, optionals are AI_CPU and AI_CORE
        :Param disable_multiprocess: disable multiprocessing, avoid cost time of enable new process for light task
        """
        if not op_name:
            op_name = []
        if not isinstance(op_name, list):
            op_name = [op_name]

        self.op_name = ",".join(op_name)
        self.task_type = task_type
        op_name_list = event_dataset.task_op_names if not op_name else op_name

        if self.n_processes <= 1 or disable_multiprocess:
            self._query_stacks_multiprocess(event_dataset, op_name_list, task_type)
        else:
            event_num_per_process = int(len(op_name_list) / self.n_processes) + 1
            parallel_analyzer = ParallelJob(
                self._query_stacks_multiprocess,
                [[event_dataset, op_name_list[i:i + event_num_per_process], task_type]
                 for i in range(0, len(op_name_list), event_num_per_process)],
                job_name="Analyzing operator stacks from timeline"
            )
            parallel_analyzer.start(self.n_processes)
        self.query_stack(event_dataset)

    def make_record(self, result: OptimizeResult):
        """
        make record for what and how to optimize
        """
        if not self._stack_record:
            return

        language = AdditionalArgsManager().language
        if language == "en":
            desc = f"Found {len(self._stack_record)} called stacks for"
            if self.op_name and self.task_type:
                desc += f" operators with name '{self.op_name}' with task type '{self.task_type}'"
            elif self.op_name and not self.task_type:
                desc += f" operators with name '{self.op_name}'"
            elif self.task_type and not self.op_name:
                desc += f" operators with task type '{self.task_type}'"
            else:
                desc += " all operators"

            suggestion = f"Please use command 'ma-advisor analyze profiling' to analyze operators"
        else:
            desc = f"发现以下{len(self._stack_record)}个算子的调用堆栈，"
            if self.op_name and self.task_type:
                desc += f"任务类型为'{self.task_type}'的'{self.op_name}'算子"
            elif self.op_name and not self.task_type:
                desc += f"'{self.op_name}'算子"
            elif self.task_type and not self.op_name:
                desc += f"算子类型为'{self.task_type}'"
            else:
                desc += "包括全部算子"

            suggestion = f"请用命令'ma-advisor analyze profiling'分析算子"


        optimization_item = OptimizeItem(
            "Operator stacks",
            desc,
            [suggestion]
        )
        result.add(OptimizeRecord(optimization_item))

        record_title = ["Task ID", "op name", "op type", "code stacks"]
        result.add_detail('operator stacks', headers=record_title)

        for op_info in self._stack_record:
            result.add_detail('operator stacks', detail=op_info)

    def query_stack(self, event_dataset: ComputationAnalysisDataset):

        if not event_dataset.dataset_len:
            return
        _ = event_dataset.parse_data_with_generator(self._query_stack_by_matched_index)

    def get_stack_record(self):
        return self._stack_record

    def _get_api_stack_by_op(self, event_dataset: ComputationAnalysisDataset, op_name: str, task_type: str):
        """
        对于单个op，从timeline文件中获取stack信息
        根据torch_to_npu连线：
            input: hardware层op_name, task_type
            step1: 根据op_name, task_type 找到timeline中对应的event，得到ts, tid, task_id等信息
            step2: dataset.torch_to_npu, key: f"{op.ph}-{op.id}", op.id为end_event.ts，也就是当前op的ts
                找到ph=s时的连线信息，pid: start_event.pid, tid=start_event.tid, ts: start_event.ts
            step3: dataset.ops_with_stack, key: op.ts, value: TimelineEvent, 记录了所有有stack信息的event
                根据start_event.ts 获取其对应的dataset_index，记录到self.matched_index
                self._task_id_record记录了start_event's index, 对应的hardware层[task_id, op_name, op_type]
            step4: 在dataset初始化阶段并没有读取全部的stack信息并保存，在后续需要重新遍历获取
        """
        for _, src_op_event in event_dataset.ops_with_task_type.items():

            op_task_type = src_op_event.get(Constant.TASK_TYPE)
            if not (src_op_event.name == op_name and op_task_type and op_task_type == task_type):
                continue

            torch_to_npu_key = f"s-{src_op_event.tid}-{src_op_event.ts}"
            torch_to_npu_event = event_dataset.torch_to_npu.get(torch_to_npu_key) or event_dataset.torch_to_npu.get(
                f"s-{src_op_event.ts}") or event_dataset.torch_to_npu.get(f"s-{src_op_event.ts.replace('.', '')}")

            acl_to_npu_event = src_op_event.ts in event_dataset.acl_to_npu

            if not torch_to_npu_event and not acl_to_npu_event:
                continue

            # query stack by torch_to_npu first, due to each operator had acl_to_npu incoming flow in cann6.3
            if torch_to_npu_event:
                dst_op_index = self._query_index_by_torch_to_npu(event_dataset, torch_to_npu_event)
            else:
                dst_op_index = self._query_index_by_acl_to_npu(acl_to_npu_event)

            if not dst_op_index:
                continue

            task_id = src_op_event.task_id
            if not task_id:
                continue

            self.matched_index.add(dst_op_index)
            if dst_op_index not in self._task_id_record:
                self._task_id_record[dst_op_index] = []
            self._task_id_record[dst_op_index].append([task_id, op_name, task_type])

    def _query_stacks_multiprocess(self, event_dataset, op_name_list, task_type):

        for op_name in op_name_list:
            if task_type is not None:
                self._get_api_stack_by_op(event_dataset, op_name, task_type)
            else:
                self._get_api_stack_by_op(event_dataset, op_name, Constant.AI_CORE)
                self._get_api_stack_by_op(event_dataset, op_name, Constant.AI_CPU)

    def _format_stack_record(self):
        stack_list = []
        for task_id, stack_info in self._task_id_record.items():
            stack_list.append([task_id, *stack_info])
        return stack_list

    def _query_stack_by_matched_index(self, index, event):
        if index not in self.matched_index:
            return None
        event = TimelineEvent(event)
        stack = event.args.get(Constant.CALL_STACKS)

        stack = stack if stack else Constant.NO_STACK_REASON_MAP.get(Constant.TIMELINE_BACKWARD_NO_STACK_CODE)
        for matched_op_info in self._task_id_record.get(index, []):
            self._stack_record.append([*matched_op_info, stack])

        for matched_op_info in self._task_id_record.get(Constant.TIMELINE_ACL_TO_NPU_NO_STACK_CODE, []):
            self._stack_record.append([*matched_op_info,
                                       Constant.NO_STACK_REASON_MAP.get(Constant.TIMELINE_ACL_TO_NPU_NO_STACK_CODE)])
        return None
