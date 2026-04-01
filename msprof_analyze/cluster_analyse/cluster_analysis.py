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
import argparse
import copy
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from msprof_analyze.cluster_analyse.analysis.analysis_facade import AnalysisFacade
from msprof_analyze.cluster_analyse.cluster_data_preprocess.prof_data_allocate import ProfDataAllocate
from msprof_analyze.cluster_analyse.communication_group.communication_group_generator import CommunicationGroupGenerator
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


def get_all_recipes():
    recipes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipes")
    all_recipes = []
    for dir_name in os.listdir(recipes_path):
        if os.path.isdir(os.path.join(recipes_path, dir_name)) and dir_name != "__pycache__":
            all_recipes.append(dir_name)
    return all_recipes


COMM_FEATURE_LIST = ['all', 'communication_time', 'communication_matrix']
ALL_FEATURE_LIST = COMM_FEATURE_LIST + get_all_recipes()


class Interface:
    ASCEND_PT = "ascend_pt"
    ASCEND_MS = "ascend_ms"
    PROF = "PROF_"

    def __init__(self, params: dict):
        self.collection_path = PathManager.get_realpath(params.get(Constant.PROFILING_PATH))
        self.analysis_mode = params.get(Constant.MODE)
        self.data_map = {}
        self.communication_group = {}
        self.collective_group_dict = {}
        self.communication_ops = []
        self.matrix_ops = []
        self.origin_params = params
        self.cluster_analysis_output_path = self.get_cluster_analysis_output_path(params)
        AdditionalArgsManager().init(params)

    def get_cluster_analysis_output_path(self, params):
        cluster_analysis_output_path = params.get(Constant.CLUSTER_ANALYSIS_OUTPUT_PATH)
        if cluster_analysis_output_path:
            return PathManager.get_realpath(cluster_analysis_output_path)
        return self.collection_path

    def allocate_prof_data(self):
        allocator = ProfDataAllocate(self.collection_path)
        if not allocator.allocate_prof_data():
            return {}
        return {Constant.DATA_MAP: allocator.data_map, Constant.DATA_TYPE: allocator.data_type,
                Constant.PROFILING_TYPE: allocator.prof_type}

    def run(self):
        PathManager.check_input_directory_path(self.collection_path)
        if os.path.exists(self.cluster_analysis_output_path):
            PathManager.check_output_directory_path(self.cluster_analysis_output_path)
        else:
            PathManager.input_path_common_check(self.cluster_analysis_output_path)
            PathManager.make_dir_safety(self.cluster_analysis_output_path)

        data_dict = self.allocate_prof_data()
        data_map, data_type, prof_type = (data_dict.get(Constant.DATA_MAP), data_dict.get(Constant.DATA_TYPE),
                                          data_dict.get(Constant.PROFILING_TYPE))
        if not data_map:
            logger.warning("Can not get rank info or profiling data.")
            return
        if data_type == Constant.INVALID:
            logger.error("The current folder contains both DB and other files. Please check.")
            return

        params = copy.deepcopy(self.origin_params)
        params.update({
            Constant.COLLECTION_PATH: self.collection_path,
            Constant.ANALYSIS_MODE: self.analysis_mode,
            Constant.DATA_MAP: data_map,
            Constant.DATA_TYPE: data_type,
            Constant.PROFILING_TYPE: data_dict.get(Constant.PROFILING_TYPE),
            Constant.IS_MSPROF: prof_type == Constant.MSPROF,
            Constant.IS_MINDSPORE: prof_type == Constant.MINDSPORE,
            Constant.CLUSTER_ANALYSIS_OUTPUT_PATH: self.cluster_analysis_output_path,
            Constant.DATA_SIMPLIFICATION: True
        })
        if self.analysis_mode in COMM_FEATURE_LIST:
            FileManager.create_output_dir(self.cluster_analysis_output_path)
            PathManager.check_output_directory_path(self.cluster_analysis_output_path)
            logger.info("Begin generate communication data.")
            if data_type == Constant.TEXT or not params.get(Constant.DATA_SIMPLIFICATION):
                comm_data_dict = CommunicationGroupGenerator(params).generate()
                logger.info("Communication data read completed.")
                params[Constant.COMM_DATA_DICT] = comm_data_dict
            AnalysisFacade(params).cluster_analyze()
            logger.info("The cluster analysis result file has been generated: %s",
                        self.cluster_analysis_output_path)
        elif data_type == Constant.TEXT:
            logger.error("The current analysis node only supports DB as input data. Please check.")
        else:
            FileManager.create_output_dir(self.cluster_analysis_output_path, is_overwrite=True)
            AnalysisFacade(params).recipe_analyze()


def cluster_analysis_main():
    parser = argparse.ArgumentParser(description="cluster analysis module")
    parser.add_argument('-d', '--profiling_path', type=PathManager.expanduser_for_argumentparser, required=True,
                        help="profiling data path")
    parser.add_argument('-m', '--mode', choices=ALL_FEATURE_LIST, default='all', help="different analysis mode")
    parser.add_argument('-o', '--output_path', type=PathManager.expanduser_for_argumentparser,
                        help='Path of cluster analysis output')
    parser.add_argument('--force', action='store_true',
                        help="Indicates whether to skip verification of the owner, size, and permissions.")
    parser.add_argument("--parallel_mode", type=str, help="context mode", default="concurrent")
    parser.add_argument("--export_type", type=str, help="recipe export type", choices=["db", "notebook", "text"],
                        default="db")
    parser.add_argument("--rank_list", type=str, help="Rank id list", default='all')
    parser.add_argument("--step_id", type=int, help="Step id", default=Constant.VOID_STEP)

    args, extra_args = parser.parse_known_args()
    parameter = vars(args)
    if extra_args:
        if parameter.get(Constant.MODE) in COMM_FEATURE_LIST:
            unknown_args = " ".join(extra_args)
            logger.warning(f"Invalid parameters: {unknown_args}. It will not have any effect.")
        else:
            parameter[Constant.EXTRA_ARGS] = extra_args
    Interface(parameter).run()


if __name__ == "__main__":
    cluster_analysis_main()
