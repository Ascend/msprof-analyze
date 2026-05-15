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
from multiprocessing import Manager

from msprof_analyze.advisor.analyzer.base_analyzer import BaseAnalyzer
from msprof_analyze.advisor.common.analyzer_scopes import SupportedScopes
from msprof_analyze.advisor.display.html.render import HTMLRender
from msprof_analyze.advisor.display.html.priority_background_color import PriorityBackgroundColor
from msprof_analyze.advisor.interface.interface import Interface
from msprof_analyze.advisor.utils.utils import ParallelJob, get_analyze_processes
from msprof_analyze.advisor.result.result import OptimizeResult
from msprof_analyze.advisor.result.item import OptimizeItem, OptimizeRecord

logger = get_logger()


class PPStageComputationAnalyzer(BaseAnalyzer):

    def __init__(self, collection_path, **kwargs):
        super().__init__(collection_path, **kwargs)
        self.collection_path = collection_path
        self._stages_rendered_html = Manager().list()
        self._multiprocess_result = Manager().dict()
        # html render不能序列化，无法用多进程，放到optimize里面初始化
        self.html_render = None
        self.result = None

    @staticmethod
    def _get_valid_sheet_name(sheet_name, prefix):
        if not sheet_name.lower().startswith(prefix.lower()):
            sheet_name = f"{prefix} {sheet_name}"
        return sheet_name

    def optimize(self, stages_profiling_path, **kwargs):
        pp_stage_processes = min(get_analyze_processes(), len(stages_profiling_path))
        if pp_stage_processes <= 1:
            for stage_profiling_path in stages_profiling_path:
                self._optimize(**stage_profiling_path)
        else:
            logger.info("Start to parallel analysis of pp stages, number of processes is %s", pp_stage_processes)
            parallel_stage_analysis_job = ParallelJob(self._optimize, stages_profiling_path,
                                                      "Computation analysis of Pipeline parallel stages")
            parallel_stage_analysis_job.start(pp_stage_processes)
            self._merge_multiprocess_result()

        self.make_render()
        self.html_render = HTMLRender()
        return self.result

    def make_render(self):
        HTMLRender().render_template(key="computation",
                                     template_dir="templates",
                                     template_name="pp_stage_computation_analysis.html",
                                     stages_rendered_html=list(self._stages_rendered_html),
                                     priority_background_color=PriorityBackgroundColor.high)

    def get_priority(self, max_mem_op_dur=None):
        pass

    def _optimize(self, profiling_path, **kwargs):
        stage_html_record = dict(stage=kwargs.get("stage"), rank=kwargs.get("rank"), step=kwargs.get("step"))
        kwargs["add_render_list"] = False

        # stage 并行分析时，避免调用本身，即SupportedScopes.STAGE_COMPUTE
        scopes = Interface.get_scope(Interface.COMPUTATION)
        stage_analyzer_list = [Interface.get_analyzer(Interface.COMPUTATION, scope)
                               for scope in scopes
                               if scope != SupportedScopes.STAGE_COMPUTE]

        for analyzer_cls in stage_analyzer_list:
            analyzer = analyzer_cls(collection_path=profiling_path, **kwargs)
            result = analyzer.optimize(**kwargs)
            if hasattr(result, "data") and result.data:
                self.result = result
            if hasattr(analyzer, "html") and analyzer.html:
                if "html_list" not in stage_html_record:
                    stage_html_record["html_list"] = []
                stage_html_record["html_list"].append(analyzer.html)
        self._stages_rendered_html.append(stage_html_record)
        self._multiprocess_result[f"rank {kwargs.get('rank')}".capitalize()] = result.data

    def _merge_multiprocess_result(self):
        self.result = OptimizeResult()
        for key, result_data in self._multiprocess_result.items():
            problem_data = result_data.get("problems", {}).get("data", [])
            if not problem_data:
                continue

            for row in problem_data:
                if len(row) < 3:
                    continue
                issue_name, desc, suggestion = row[:3]
                sheet_name = PPStageComputationAnalyzer._get_valid_sheet_name(issue_name, key)
                optimization_item = OptimizeItem(sheet_name, desc, [suggestion])
                self.result.add(OptimizeRecord(optimization_item))
            del result_data["problems"]

            for issue_name, issue_details in result_data.items():
                headers = issue_details.get("headers", [])
                data = issue_details.get("data", [])
                sheet_name = PPStageComputationAnalyzer._get_valid_sheet_name(issue_name, key)
                self.result.add_detail(sheet_name, headers=headers)

                for row in data:
                    self.result.add_detail(sheet_name, detail=row)
