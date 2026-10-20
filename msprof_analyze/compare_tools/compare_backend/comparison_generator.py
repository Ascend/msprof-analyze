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
from msprof_analyze.compare_tools.compare_backend.generator.detail_performance_generator import (
    DetailPerformanceGenerator,
)
from msprof_analyze.compare_tools.compare_backend.generator.overall_performance_generator import (
    OverallPerformanceGenerator,
)
from msprof_analyze.compare_tools.compare_backend.interface.overall_interface import OverallInterface
from msprof_analyze.compare_tools.compare_backend.interface.compare_interface import CompareInterface
from msprof_analyze.compare_tools.compare_backend.profiling_parser.gpu_profiling_parser import GPUProfilingParser
from msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_parser import NPUProfilingParser
from msprof_analyze.compare_tools.compare_backend.utils.args_manager import ArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_db_parser import NPUProfilingDbParser

logger = get_logger()


class ComparisonGenerator:
    PARSER_DICT = {Constant.NPU: NPUProfilingParser, Constant.GPU: GPUProfilingParser}
    INTERFACE_DICT = {Constant.OVERALL_COMPARE: OverallInterface}

    def __init__(self, args):
        AdditionalArgsManager().init(args)
        self._args_manager = ArgsManager(args)
        self._data_dict = {}

    def run(self):
        try:
            self._args_manager.init()
            self.load_data()
            self.generate_compare_result()
        except NotImplementedError as e:
            logger.error("%s", e)
        except RuntimeError as e:
            logger.error("%s", e)
        except FileNotFoundError as e:
            logger.error("%s", e)
        except Exception as e:
            logger.error("%s", e)

    def load_data(self):
        if self._args_manager.base_path_dict.get(Constant.PROFILER_DB_PATH):
            self._data_dict[Constant.BASE_DATA] = NPUProfilingDbParser(
                self._args_manager.args, self._args_manager.base_path_dict, self._args_manager.base_step
            ).load_data()
        else:
            self._data_dict[Constant.BASE_DATA] = self.PARSER_DICT.get(self._args_manager.base_profiling_type)(
                self._args_manager.args, self._args_manager.base_path_dict, self._args_manager.base_step
            ).load_data()
        if self._args_manager.comparison_path_dict.get(Constant.PROFILER_DB_PATH):
            self._data_dict[Constant.COMPARISON_DATA] = NPUProfilingDbParser(
                self._args_manager.args, self._args_manager.comparison_path_dict, self._args_manager.comparison_step
            ).load_data()
        else:
            self._data_dict[Constant.COMPARISON_DATA] = self.PARSER_DICT.get(
                self._args_manager.comparison_profiling_type
            )(
                self._args_manager.args, self._args_manager.comparison_path_dict, self._args_manager.comparison_step
            ).load_data()

    def generate_compare_result(self):
        overall_data = {
            Constant.BASE_DATA: self._data_dict.get(Constant.BASE_DATA).overall_metrics,
            Constant.COMPARISON_DATA: self._data_dict.get(Constant.COMPARISON_DATA).overall_metrics,
        }
        overall_generator = OverallPerformanceGenerator(overall_data, self._args_manager.args)
        overall_generator.start()
        DetailPerformanceGenerator(self._data_dict, self._args_manager.args).run()
        overall_generator.join()

    def run_interface(self, compare_type: str) -> dict:
        try:
            self._args_manager.init()
            self._args_manager.set_compare_type(compare_type)
            self.load_data()
            interface = self.INTERFACE_DICT.get(compare_type)
            if interface:
                return interface(self._data_dict).run()
            return CompareInterface(self._data_dict, self._args_manager).run()
        except NotImplementedError as e:
            logger.error("%s", e)
        except RuntimeError as e:
            logger.error("%s", e)
        except FileNotFoundError as e:
            logger.error("%s", e)
        except Exception as e:
            logger.error("%s", e)
        return {}
