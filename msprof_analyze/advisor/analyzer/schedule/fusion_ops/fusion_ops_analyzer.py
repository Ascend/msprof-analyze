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
import os
import multiprocessing
from msprof_analyze.prof_common.logger import get_logger
import re

from tqdm import tqdm

from msprof_analyze.advisor.dataset.stack.db_stack_finder import DBStackFinder
from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.display.prompt.base_prompt import BasePrompt
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.dataset.timeline_event_dataset import ScheduleAnalysisDataset
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord
from msprof_analyze.advisor.utils.utils import format_timeline_result
from msprof_analyze.advisor.common.timeline.fusion_ops_db import init_timeline_ops_db
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor

logger = get_logger()


class TimelineFusionOpsAnalyzer(BaseAnalyzer):
    dataset_cls_list = [ScheduleAnalysisDataset]

    def __init__(self, collection_path, n_processes: int = 1, **kwargs):
        super().__init__(collection_path, n_processes, **kwargs)
        self._matched_op_index = {} if self.n_processes <= 1 else multiprocessing.Manager().dict()
        self.matched_op_stacks = {}
        self.empty_stacks = True
        key = ScheduleAnalysisDataset.get_key()
        self.timeline_event_dataset = self.get_first_data_by_key(self.dataset_list, key)

    def get_priority(self, max_mem_op_dur=None):
        return PriorityBackgroundColor.low

    def optimize(self, **kwargs):
        disable_affinity_api = os.getenv(Constant.DISABLE_AFFINITY_API)
        if disable_affinity_api is not None and disable_affinity_api.lower() == "true":
            logger.info(
                "Skip affinity api analysis due to longer processing time due to env 'DISABLE_AFFINITY_API'")
            return self.result

        for mode in [Constant.ATEN.lower(), Constant.OPTIMIZER.lower()]:

            for op_combined, npu_apis in tqdm(getattr(init_timeline_ops_db(self.cann_version,
                                                                           self.profiling_type,
                                                                           self.profiling_version),
                                                      f"_{mode}_op_api_map").items(), leave=False, ncols=100,
                                              desc="Scanning timeline for affinity apis"):
                for npu_api in npu_apis.split("/"):
                    self.find_fusion_ops(self.timeline_event_dataset, op_combined, npu_api, mode)

        self.query_stack(self.timeline_event_dataset)

        logger.info("Finish timeline analysis")
        self.make_record()
        self.make_render(rank=kwargs.get("rank"))
        return self.result

    def find_fusion_ops(self, event_dataset, ops: str, npu_api: str, mode: str):
        """
        :Param event_dataset: dataset of timeline event
        :Param ops: operator combination with '-' as separator , e.g. permute-reshape
        :Param npu_api: api of torch_npu, generally more efficient than torch api
        :Param mode: aten or dequeue or optimizer
        :Return: json of op_name and called times and detail stacks
        """
        op_rule_pattern, enable_regex = self._format_rule_to_pattern(ops)
        if not enable_regex:
            self._match_ops(event_dataset, op_rule_pattern, npu_api, mode)
        else:
            try:
                self._match_ops_with_regex(event_dataset, op_rule_pattern, npu_api, mode)
            except Exception as e:
                logger.warning("Failed to find fusion operators with regex %s, reason is %s", ops, e)

    def make_record(self):
        """
        make record for what and how to optimize
        """
        if not self.matched_op_stacks:
            return
        
        prompt_class = BasePrompt.get_prompt_class(self.__class__.__name__)

        desc = prompt_class.DESCRIPTION.format(self.cann_version, self.profiling_version,
                                                  len(format_timeline_result(self.matched_op_stacks)))
        suggestion = prompt_class.SUGGESTION
        if self.empty_stacks:
            desc += prompt_class.EMPTY_STACK_DESCRIPTION
            suggestion = prompt_class.EMPTY_STACKS_SUGGESTION.format(Config().timeline_with_stack_doc_url)

        optimization_item = OptimizeItem(prompt_class.PROBLEM, desc, [suggestion])

        self.result.add(OptimizeRecord(optimization_item))
        record_title = ["Affinity API", "Code stacks", "Stack called counts"]
        self.result.add_detail(prompt_class.PROBLEM, headers=record_title)

        for api_name, stacks_info in format_timeline_result(self.matched_op_stacks).items():
            if not stacks_info:
                detail = [api_name, "null", "null"]
                self.result.add_detail(prompt_class.PROBLEM, detail=detail)
            else:
                for stack in stacks_info:
                    detail = [api_name, *stack]
                    self.result.add_detail(prompt_class.PROBLEM, detail=detail)

    def make_render(self, **kwargs):
        rank = kwargs.get("rank")
        format_result_for_html = format_timeline_result(dict(self.matched_op_stacks), dump_html=True)

        self.html_render.render_template(key="schedule",
                                         template_dir="templates",
                                         template_name="affinity_api.html",
                                         cann_version=self.cann_version,
                                         profiling_type=self.profiling_type,
                                         profiling_version=self.profiling_version,
                                         empty_stacks=self.empty_stacks,
                                         with_stack_doc_url=Config().timeline_with_stack_doc_url,
                                         api_doc_url=Config().timeline_api_doc_url,
                                         result=format_result_for_html,
                                         priority_background_color=self.get_priority(),
                                         rank=rank)

    def query_stack(self, event_dataset):
        if all([len(matched_index) == 0 for matched_index in self._matched_op_index.values()]):
            return
        if event_dataset.data_type == Constant.TEXT:
            self.query_stack_from_timeline_json(event_dataset)
        elif event_dataset.data_type == Constant.DB:
            self.query_stack_from_db(event_dataset.timeline_file)


    def query_stack_from_timeline_json(self, event_dataset):
        op_stack_list = event_dataset.parse_data_with_generator(self._query_stack_by_matched_index)
        for op_stack in op_stack_list:
            for op_rule, stack in op_stack.items():
                if op_rule not in self.matched_op_stacks:
                    self.matched_op_stacks[op_rule] = {}
                if stack == Constant.TIMELINE_FUSION_OPS_NO_STACK_FLAG:
                    continue
                self.matched_op_stacks[op_rule].setdefault(stack, 0)
                self.matched_op_stacks[op_rule][stack] += 1

    def query_stack_from_db(self, db_path):
        stack_helper = DBStackFinder(db_path)
        for op_rule, matched_index in self._matched_op_index.items():
            stack_dict = stack_helper.get_api_stack_by_api_index(matched_index)
            self.matched_op_stacks[op_rule] = {}
            if not stack_dict:
                continue
            self.empty_stacks = False
            for stack in stack_dict.values():
                self.matched_op_stacks[op_rule].setdefault(stack, 0)
                self.matched_op_stacks[op_rule][stack] += 1

    def _match_ops(self, event_dataset, ops: str, npu_api: str, mode: str):
        """ match operator based on fusion operators rule(without regex),
            only strictly equals of op name list means matched
        :Param event_dataset: dataset of timeline event
        :Param ops: operator combination with '-' as separator , e.g. permute-reshape
        :Param npu_api: api of torch_npu, generally more efficient than torch api
        :Param mode: aten or dequeue or optimizer
        """
        op_list = ops.split(Constant.OP_SEP)

        matched_op_index = set()
        api_ops_matched = False

        for index, event in enumerate(getattr(event_dataset, mode)):
            if self._replace_op_name_prefix(event.name, mode) != op_list[0]:
                continue
            tmp_dequeue_event_names = [self._replace_op_name_prefix(event.name, mode)
                                       for event in getattr(event_dataset, mode)[index: index + len(op_list)]]
            if tmp_dequeue_event_names != op_list:
                continue
            api_ops_matched = True
            matched_op_index.add(event.dataset_index)

        if api_ops_matched:
            self._matched_op_index[npu_api + f":{ops}"] = matched_op_index

    def _match_ops_with_regex(self, event_dataset, op_rule_pattern: str, npu_api: str,
                              mode: str):
        """ match operator based on fusion operators rule(with regex),
            using regex to support condition like 'a = torch.mul(xxx) if xxx else torch.add(xxx)'
        :Param event_dataset: dataset of timeline event
        :Param op_rule_pattern: fusion operators rule with regex definition , e.g. add-mul{0,10}, add-mul*
        :Param npu_api: api of torch_npu, generally more efficient than torch api
        :Param mode: aten or dequeue or optimizer
        """
        matched_op_index = set()
        total_op_name = "".join([f"{Constant.OP_SEP}{self._replace_op_name_prefix(event.name, mode)}{Constant.OP_SEP}"
                                 for event in getattr(event_dataset, mode)])

        matched_pattern_index_tuple = [(x.start(0), x.end(0)) for x in re.finditer(op_rule_pattern, total_op_name)]
        # convert list of index tuple to a whole list:  [(3, 25), ...] -> [3, 25, ...]
        total_ops_split_points = [num
                                  for sublist in matched_pattern_index_tuple
                                  for num in sublist]

        api_ops_matched = len(total_ops_split_points) != 0

        op_index = []
        if 0 not in total_ops_split_points:
            total_ops_split_points = [0] + total_ops_split_points
        if len(list(total_op_name)) not in total_ops_split_points:
            total_ops_split_points.append(len(list(total_op_name)))

        # convert total ops name like "-add-mul-xxx-div-" to small pieces like [["add", "mul"], [...], ["div"]]
        # by the regex index and then calculate the real index for matched fusion operators in event dataset
        for left, right in zip(total_ops_split_points, total_ops_split_points[1:]):
            matched_op_flag = True if (left, right) in matched_pattern_index_tuple else False
            matched_ops_list = \
                total_op_name[left: right].strip(Constant.OP_SEP).split(Constant.OP_SEP + Constant.OP_SEP)
            op_index.append([matched_op_flag, len(matched_ops_list)])
        for i, _ in enumerate(op_index):
            if i > 0:
                # calculate cumsum for indexing matched operator
                op_index[i][1] = op_index[i][1] + op_index[i - 1][1]
        op_index = [[False, 0]] + op_index

        for i, _ in enumerate(op_index):
            if not op_index[i][0]:
                continue
            index = op_index[i - 1][1]
            matched_op_index.add(index)

            if index > len(getattr(event_dataset, mode)) - 1:
                continue
            dataset_index = getattr(event_dataset, mode)[index].get("dataset_index")
            matched_op_index.add(dataset_index)

        if api_ops_matched:
            self._matched_op_index[npu_api + f":{op_rule_pattern}"] = sorted(list(matched_op_index))

    def _query_stack_by_matched_index(self, index, event):
        stack_record = {}
        event = TimelineEvent(event)

        matched_op_rules = []
        for op_rule, matched_index in self._matched_op_index.items():
            if index not in matched_index:
                continue

            matched_op_rules.append(op_rule)
            stack = event.args.get(Constant.CALL_STACKS)

            if not stack:
                logger.debug("Got empty '%s' for event %s", Constant.CALL_STACKS, event)
                continue

            if self.empty_stacks and stack:
                self.empty_stacks = False

            stack_record[op_rule] = stack

        if matched_op_rules and not stack_record:
            for op_rule in matched_op_rules:
                stack_record[op_rule] = Constant.TIMELINE_FUSION_OPS_NO_STACK_FLAG

        return stack_record

    def _replace_op_name_prefix(self, event_name, mode):
        if mode == Constant.DEQUEUE.lower():
            op_name_prefix = f"{Constant.DEQUEUE}{Constant.DEQUEUE_SEP}"
        elif mode == Constant.ATEN:
            op_name_prefix = f"{Constant.ATEN}{Constant.ATEN_SEP}"
        else:
            op_name_prefix = f"{Constant.OPTIMIZER}.{Constant.OPTIMIZER_STEP}{Constant.OPTIMIZER_SEP}"

        return event_name.replace(op_name_prefix, "")

    def _format_rule_to_pattern(self, op_rule):
        """
        Args:
            op_rule: like (mul){0,1}-(add|neg){0,2}-dropout-(softmax)*

        Returns: op_pattern like (-mul-){0,1}(-add-|-neg-){0,2}(-dropout-)(-softmax-)*
        """
        enable_regex = False
        if "(" not in op_rule and ")" not in op_rule:
            # op_rule which requires fuzzy matching mush consist of "()"
            return op_rule, enable_regex

        enable_regex = True
        op_pattern_list = op_rule.split(Constant.OP_SEP)
        format_op_pattern = ""
        for op_pattern in op_pattern_list:
            matched_res = re.search(r'\((\w+)\)', op_pattern)

            ops_index_range = (matched_res.start() + 1, matched_res.end() - 1) if matched_res else (
                0, len(op_pattern))

            op_names = op_pattern[ops_index_range[0]: ops_index_range[1]]
            tmp_op_names_record = []
            for op_name in op_names.split("|"):
                tmp_op_names_record.append(f"{Constant.OP_SEP}{op_name.strip(' ')}{Constant.OP_SEP}")
            op_suffix = op_pattern[ops_index_range[1] + 1:]
            op_names_format = f"({'|'.join(tmp_op_names_record)}){op_suffix}"

            format_op_pattern += op_names_format
        return format_op_pattern, enable_regex
