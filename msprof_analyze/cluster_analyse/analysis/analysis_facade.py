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
import json
import sqlite3
import time
from contextlib import closing
from multiprocessing import Process, Value, Lock
from pathlib import Path
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
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.json_output import set_json_success
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.cluster_analyse.recipes.communication_group_map.communication_group_map import CommunicationGroupMap
from msprof_analyze.cluster_analyse.recipes.communication_time_sum.communication_time_sum import CommunicationTimeSum
from msprof_analyze.cluster_analyse.recipes.communication_matrix_sum.communication_matrix_sum import CommMatrixSum

logger = get_logger()


def run_task(analysis_cls, params, completed_processes, lock, config):
    init_subprocess(config)
    analysis = analysis_cls(params)
    analysis.run(completed_processes, lock)


class AnalysisFacade:
    text_module = {
        CommunicationAnalysis,
        StepTraceTimeAnalysis,
        CommMatrixAnalysis,
        HostInfoAnalysis,
        ClusterBaseInfoAnalysis,
    }
    db_module = {StepTraceTimeAnalysis, ClusterBaseInfoAnalysis, HostInfoAnalysis}

    def __init__(self, params: dict):
        self.params = params

    def cluster_analyze(self):
        # 多个profiler用多进程处理
        process_list = []
        if self.params.get(Constant.DATA_TYPE) == Constant.DB:
            analysis_module = self.db_module
            self.cluster_analyze_with_recipe()
        else:
            analysis_module = self.text_module

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
                process = Process(target=run_task, args=(analysis, self.params, completed_processes, lock, config))
                process.start()
                process_list.append(process)
            last_progress = 0
            while any(p.is_alive() for p in process_list):
                with lock:
                    current_progress = completed_processes.value
                if current_progress > last_progress:
                    pbar.update(current_progress - last_progress)
                    last_progress = current_progress
                time.sleep(0.1)
            for process in process_list:
                process.join()
            final_progress = completed_processes.value
            if final_progress > last_progress:
                pbar.update(final_progress - last_progress)

    def do_recipe(self, recipe_class):
        if not recipe_class or len(recipe_class) != 2:
            logger.error("Invalid input recipe_class, should be two elements, e.g. (class_name, class)")
            return
        try:
            logger.info("Recipe %s analysis is starting to launch.", recipe_class[0])
            with Context.create_context(self.params.get(Constant.PARALLEL_MODE)) as context:
                self.params[Constant.RECIPE_NAME] = recipe_class[0]
                with recipe_class[1](self.params) as recipe:
                    recipe.run(context)
            logger.info("Recipe %s analysis finished.", recipe_class[0])
        except Exception as e:
            logger.error("Recipe %s analysis launched failed, %s.", recipe_class[0], e)

    def recipe_analyze(self):
        recipe_class = get_class_from_name(self.params.get(Constant.ANALYSIS_MODE))
        if recipe_class:
            self.do_recipe(recipe_class)

    def cluster_statistic(self):
        recipe_class = get_class_from_name(Constant.CLUSTER_STATISTIC)
        if not recipe_class:
            raise RuntimeError("Could not load the cluster_statistic recipe.")
        recipe_name, recipe_type = recipe_class
        params = dict(self.params, **{Constant.RECIPE_NAME: recipe_name})
        output_dir = Path(params[Constant.CLUSTER_ANALYSIS_OUTPUT_PATH]) / Constant.CLUSTER_ANALYSIS_OUTPUT
        PathManager.check_output_directory_path(str(output_dir))
        db_path = output_dir / Constant.DB_CLUSTER_COMMUNICATION_ANALYZER
        tables = (*recipe_type.TABLES, Constant.TABLE_COMMUNICATION_GROUP_MAPPING, Constant.TABLE_CLUSTER_BASE_INFO)
        mode = params.get(Constant.PARALLEL_MODE, Constant.CONCURRENT_MODE)

        if db_path.is_symlink():
            raise ValueError(
                f"Output database is a symbolic link at {db_path}. Use -o to select another output directory."
            )
        with closing(sqlite3.connect(str(db_path))) as connection:
            connection.execute("PRAGMA temp_store = FILE")
            with Context.create_context(mode, max_workers=recipe_type.MAX_PENDING_RANKS) as context:
                with recipe_type(params, connection) as recipe:
                    mapping_input = recipe.run(context)
                if mapping_input is None:
                    raise ValueError("No usable communication data for the selected ranks. See the analysis log.")
            self._write_statistic_group_mapping(connection, mapping_input)
            self._write_statistic_base_info(connection)
        logger.info("Generated cluster statistics in %s.", db_path)
        set_json_success(msg_dict={"db_path": str(db_path), "tables": list(tables)})

    def _write_statistic_group_mapping(self, connection, mapping_input):
        recipe = CommunicationGroupMap(self.params)
        recipe.reducer_func(mapping_input)
        schema = DBManager.sql_generate_table("CommunicationGroupMappingMap")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE IF EXISTS CommunicationGroupMapping")
            connection.execute(f"CREATE TABLE CommunicationGroupMapping {schema}")  # nosec B608
            if recipe.group_df is not None:
                connection.executemany(
                    "INSERT INTO CommunicationGroupMapping VALUES (?, ?, ?, ?, ?)",
                    recipe.group_df.itertuples(index=False, name=None),
                )

    def _write_statistic_base_info(self, connection):
        schema = DBManager.sql_generate_table("ClusterBaseInfoMap")
        analysis = ClusterBaseInfoAnalysis(self.params)
        analysis.extract_base_info()
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE IF EXISTS ClusterBaseInfo")
            connection.execute(f"CREATE TABLE ClusterBaseInfo {schema}")  # nosec B608
            if analysis.distributed_args:
                connection.execute(
                    "INSERT INTO ClusterBaseInfo VALUES (?, ?)",
                    (Constant.DISTRIBUTED_ARGS, json.dumps(analysis.distributed_args)),
                )

    def cluster_analyze_with_recipe(self):
        recipes = [["CommunicationGroupMap", CommunicationGroupMap]]
        if self.params.get(Constant.ANALYSIS_MODE) in (Constant.ALL, Constant.COMMUNICATION_TIME):
            recipes.append(["CommunicationTimeSum", CommunicationTimeSum])
        if self.params.get(Constant.ANALYSIS_MODE) in (Constant.ALL, Constant.COMMUNICATION_MATRIX):
            recipes.append(["CommMatrixSum", CommMatrixSum])
        for recipe_class in recipes:
            self.do_recipe(recipe_class)
