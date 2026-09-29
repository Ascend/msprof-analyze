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
from msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_db_parser import NPUProfilingDbParser
from msprof_analyze.compare_tools.compare_backend.profiling_parser.gpu_profiling_parser import GPUProfilingParser
from msprof_analyze.compare_tools.compare_backend.profiling_parser.npu_profiling_parser import NPUProfilingParser
from msprof_analyze.compare_tools.compare_backend.utils.args_manager import ArgsManager
from msprof_analyze.compare_tools.compare_backend.utils.compare_args import Args
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


class OverallPerfInterface:
    PARSER_DICT = {Constant.NPU: NPUProfilingParser, Constant.GPU: GPUProfilingParser}

    def __init__(self, profiling_path: str):
        self._profiling_path = profiling_path
        self._profiling_path_dict = {}
        self._result_data = {}
        self._profiling_data = None

    def run(self):
        try:
            self._check_path()
            self._load_data()
            self._generate_result()
        except NotImplementedError as e:
            logger.error("%s", e)
        except RuntimeError as e:
            logger.error("%s", e)
        except FileNotFoundError as e:
            logger.error("%s", e)
        except Exception as e:
            logger.error("%s", e)
        return self._result_data

    def _check_path(self):
        profiling_path = PathManager.get_realpath(self._profiling_path)
        self._profiling_path_dict = ArgsManager(Args(enable_profiling_compare=True)).parse_profiling_path(
            profiling_path
        )

    def _load_data(self):
        args = Args(enable_profiling_compare=True)
        if self._profiling_path_dict.get(Constant.PROFILER_DB_PATH):
            self._profiling_data = NPUProfilingDbParser(args, self._profiling_path_dict).load_data()
        else:
            profiling_type = self._profiling_path_dict.get(Constant.PROFILING_TYPE, Constant.NPU)
            self._profiling_data = self.PARSER_DICT.get(profiling_type)(args, self._profiling_path_dict).load_data()

    def _generate_result(self):
        overall_data = self._profiling_data.overall_metrics

        self._result_data = {
            "profiling_type": overall_data.profiling_type,
            "minimal_profiling": overall_data.minimal_profiling,
            "overall": {
                "e2e_time_ms": overall_data.e2e_time_ms,
                "computing_time_ms": overall_data.compute_time_ms,
                "uncovered_communication_time_ms": overall_data.communication_not_overlapped_ms,
                "free_time_ms": overall_data.free_time_ms,
            },
            "computing_time_disaggregate": {
                "fa_time_ms": overall_data.fa_fwd_time + overall_data.fa_bwd_time,
                "conv_time_ms": overall_data.conv_fwd_time + overall_data.conv_bwd_time,
                "matmul_time_ms": overall_data.mm_total_time,
                "page_attention_time_ms": overall_data.page_attention_time,
                "vector_time_ms": overall_data.vector_total_time,
                "tensor_move_time_ms": overall_data.sdma_time_tensor_move,
                "other_cube_time_ms": overall_data.other_cube_time,
            },
            "computing_num_disaggregate": {
                "fa_num": overall_data.fa_fwd_num + overall_data.fa_bwd_num,
                "conv_num": overall_data.conv_fwd_num + overall_data.conv_bwd_num,
                "matmul_num": overall_data.mm_total_num,
                "page_attention_num": overall_data.page_attention_num,
                "vector_num": overall_data.vector_total_num,
                "tensor_move_num": overall_data.sdma_num_tensor_move,
                "other_cube_num": overall_data.other_cube_num,
            },
            "communication_time_disaggregate": {
                "wait_time_ms": overall_data.wait_time_ms,
                "transmit_time_ms": overall_data.transmit_time_ms,
            },
            "free_time_disaggregate": {
                "sdma_time_ms": overall_data.sdma_time_stream,
                "free_ms": overall_data.free_time_ms - overall_data.sdma_time_stream,
            },
        }
