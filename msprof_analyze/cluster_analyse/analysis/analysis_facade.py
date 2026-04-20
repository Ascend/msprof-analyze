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
from multiprocessing import Process, Value, Lock
from tqdm import tqdm

from msprof_analyze.cluster_analyse.analysis.communication_analysis import CommunicationAnalysis
from msprof_analyze.cluster_analyse.analysis.comm_matrix_analysis import CommMatrixAnalysis
from msprof_analyze.cluster_analyse.analysis.step_trace_time_analysis import StepTraceTimeAnalysis
from msprof_analyze.cluster_analyse.analysis.host_info_analysis import HostInfoAnalysis
from msprof_analyze.cluster_analyse.analysis.cluster_base_info_analysis import ClusterBaseInfoAnalysis
from msprof_analyze.cluster_analyse.common_func.context import Context
from msprof_analyze.cluster_analyse.common_func.context import init_subprocess
from msprof_analyze.cluster_analyse.common_func.analysis_loader import get_class_from_name
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.cluster_analyse.recipes.communication_group_map.communication_group_map import CommunicationGroupMap
from msprof_analyze.cluster_analyse.recipes.communication_time_sum.communication_time_sum import \
    CommunicationTimeSum
from msprof_analyze.cluster_analyse.recipes.communication_matrix_sum.communication_matrix_sum import CommMatrixSum

logger = get_logger()


def run_task(analysis_cls, params, completed_processes, lock, config):
    init_subprocess(config)
    analysis = analysis_cls(params)
    analysis.run(completed_processes, lock)


class AnalysisFacade:
    default_module = {CommunicationAnalysis, StepTraceTimeAnalysis, CommMatrixAnalysis, HostInfoAnalysis,
                      ClusterBaseInfoAnalysis}
    simplified_module = {StepTraceTimeAnalysis, ClusterBaseInfoAnalysis, HostInfoAnalysis}

    def __init__(self, params: dict):
        self.params = params

    def cluster_analyze(self):
        # 多个profiler用多进程处理
        process_list = []
        if self.params.get(Constant.DATA_SIMPLIFICATION) and self.params.get(Constant.DATA_TYPE) == Constant.DB:
            analysis_module = self.simplified_module
            self.cluster_analyze_with_recipe()
        else:
            analysis_module = self.default_module

        num_processes = len(analysis_module)
        completed_processes = Value('i', 0)
        lock = Lock()

        # 自定义进度条格式，显示已完成任务数量和总数量
        bar_format = '{l_bar}{bar} | {n_fmt}/{total_fmt}'
        config = {
            "force": AdditionalArgsManager().force,
        }
        with tqdm(total=num_processes, desc="Cluster analyzing", bar_format=bar_format) as pbar:
            for analysis in analysis_module:
                pbar.n = completed_processes.value
                pbar.refresh()
                process = Process(target=run_task, args=(analysis, self.params, completed_processes, lock, config))
                process.start()
                process_list.append(process)

            while any(p.is_alive() for p in process_list):
                with lock:
                    pbar.n = completed_processes.value
                    pbar.refresh()

        for process in process_list:
            process.join()

        with lock:
            pbar.n = completed_processes.value
            pbar.refresh()

    def do_recipe(self, recipe_class):
        if not recipe_class or len(recipe_class) != 2:
            logger.error(f"Invalid input recipe_class, should be two elements, e.g. (class_name, class)")
            return
        try:
            logger.info(f"Recipe {recipe_class[0]} analysis is starting to launch.")
            with Context.create_context(self.params.get(Constant.PARALLEL_MODE)) as context:
                self.params[Constant.RECIPE_NAME] = recipe_class[0]
                with recipe_class[1](self.params) as recipe:
                    recipe.run(context)
            logger.info(f"Recipe {recipe_class[0]} analysis launched successfully.")
        except Exception as e:
            logger.error(f"Recipe {recipe_class[0]} analysis launched failed, {e}.")

    def recipe_analyze(self):
        recipe_class = get_class_from_name(self.params.get(Constant.ANALYSIS_MODE))
        if recipe_class:
            self.do_recipe(recipe_class)

    def cluster_analyze_with_recipe(self):
        recipes = [["CommunicationGroupMap", CommunicationGroupMap]]
        if self.params.get(Constant.ANALYSIS_MODE) in (Constant.ALL, Constant.COMMUNICATION_TIME):
            recipes.append(["CommunicationTimeSum", CommunicationTimeSum])
        if self.params.get(Constant.ANALYSIS_MODE) in (Constant.ALL, Constant.COMMUNICATION_MATRIX):
            recipes.append(["CommMatrixSum", CommMatrixSum])
        for recipe_class in recipes:
            self.do_recipe(recipe_class)
