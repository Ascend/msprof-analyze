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
import copy
import logging
import json
import sys
import os
import platform
import multiprocessing as mp
from multiprocessing import Manager
from pathlib import Path

import psutil

from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.advisor.analyzer.cluster.slow_rank_analyzer import SlowRankAnalyzer
from msprof_analyze.advisor.analyzer.cluster.slow_link_analyzer import SlowLinkAnalyzer
from msprof_analyze.advisor.analyzer.computation.pp_stage_computation_analyzer import PPStageComputationAnalyzer
from msprof_analyze.advisor.analyzer.overall.overall_summary_analyzer import OverallSummaryAnalyzer
from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.common.analyzer_scopes import SupportedScopes
from msprof_analyze.advisor.common.async_analysis_status import AsyncAnalysisStatus
from msprof_analyze.advisor.common.enum_params_parser import EnumParamsParser
from msprof_analyze.advisor.utils.utils import Timer, safe_index_value, safe_division, safe_index, convert_to_int
from msprof_analyze.advisor.interface.interface import Interface
from msprof_analyze.cluster_analyse.cluster_data_preprocess.pytorch_data_preprocessor import PytorchDataPreprocessor
from msprof_analyze.cluster_analyse.cluster_data_preprocess.mindspore_data_preprocessor import MindsporeDataPreprocessor
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.constant import Constant

# 以spawn模式启动多进程，避免fork主进程资源。如果主进程逻辑较为复杂，fork可能会导致异常。
mp.set_start_method("spawn", force=True)
logger = logging.getLogger()


class AsyncParams:
    """处理用户异步请求的输入参数，包括cli arguments和环境变量两类参数."""
    user_valid_arguments = {}
    user_valid_envs = {}
    user_non_enum_params = {}
    user_invalid_values = []
    user_total_params = {}

    @staticmethod
    def parse_async_list_params(key, value, option_values, key_type, value_type):
        if isinstance(value, list):
            value_list = value
        else:
            value_list = [_.strip(" ") for _ in str(value).split(",")]

        if sorted(value_list) not in [sorted(option) for option in option_values]:
            AsyncParams.user_invalid_values.append(
                {"key": key, "invalid value": value, "optional values": option_values,
                 "required value type": value_type})
            return
        if key_type == EnumParamsParser.ENVS:
            AsyncParams.user_valid_envs[key.upper()] = ",".join(value_list)
        elif key_type == EnumParamsParser.ARGUMENTS:
            AsyncParams.user_valid_arguments[key] = value_list

    @staticmethod
    def parse_async_int_params(key, value, option_values, key_type, value_type):
        if convert_to_int(value) not in option_values:
            AsyncParams.user_invalid_values.append(
                {"key": key, "invalid value": value, "optional values": option_values,
                 "required value type": value_type})
            return

        if key_type == EnumParamsParser.ENVS:
            AsyncParams.user_valid_envs[key.upper()] = str(convert_to_int(value))
        elif key_type == EnumParamsParser.ARGUMENTS:
            AsyncParams.user_valid_arguments[key] = convert_to_int(value)

    @staticmethod
    def parse_async_str_params(key, value, option_values, key_type, value_type):
        if str(value) not in option_values:
            AsyncParams.user_invalid_values.append(
                {"key": key, "invalid value": value, "optional values": option_values,
                 "required value type": value_type})
            return
        if key_type == EnumParamsParser.ENVS:
            AsyncParams.user_valid_envs[key.upper()] = str(value)
        elif key_type == EnumParamsParser.ARGUMENTS:
            AsyncParams.user_valid_arguments[key] = str(value)

    @staticmethod
    def parse_async_boolean_params(key, value, option_values, key_type, value_type):

        if str(value).lower() not in ["true", "false"]:
            AsyncParams.user_invalid_values.append(
                {"key": key, "invalid value": value, "optional values": option_values,
                 "required value type": value_type})
            return

        if key_type == EnumParamsParser.ENVS:
            AsyncParams.user_valid_envs[key.upper()] = str(value)
        elif key_type == EnumParamsParser.ARGUMENTS:
            AsyncParams.user_valid_arguments[key] = str(value).lower() == "true"

    @staticmethod
    def parse_params(user_async_params):
        params_parser = EnumParamsParser()
        valid_env_keys = [key.lower() for key in params_parser.get_envs_keys()]
        valid_arg_keys = [key.lower() for key in params_parser.get_arguments_keys()]

        for key, value in user_async_params.items():
            key = key.lower()
            if key not in valid_env_keys + valid_arg_keys:
                AsyncParams.user_non_enum_params[key] = value
                continue

            if key in valid_env_keys:
                # 环境变量均大写，异步调用入参到analyzer controller时支持用户使用小写配置环境变量
                option_values = params_parser.get_options(key.upper())
                value_type = params_parser.get_value_type(key.upper())
                key_type = params_parser.ENVS
            else:
                option_values = params_parser.get_options(key)
                value_type = params_parser.get_value_type(key)
                key_type = params_parser.ARGUMENTS

            if hasattr(AsyncParams, f"parse_async_{value_type}_params"):
                getattr(AsyncParams, f"parse_async_{value_type}_params")(key, value, option_values, key_type,
                                                                         value_type)

        AsyncParams.user_total_params["async_analysis_env"] = AsyncParams.user_valid_envs
        AsyncParams.user_total_params.update(AsyncParams.user_valid_arguments)
        AsyncParams.user_total_params.update(AsyncParams.user_non_enum_params)


class AnalyzerController:
    CLUSTER_RANK_THRESHOLD = 2
    SDMA_SUPPORT_SCOPES = [SupportedScopes.BANDWIDTH_CONTENTION_DETECTION, SupportedScopes.BYTE_ALIGNMENT_DETECTION]
    RDMA_SUPPORT_SCOPES = [SupportedScopes.PACKET]
    COMMUNICATION_MAPPING = {
        SlowLinkAnalyzer.SDMA: SDMA_SUPPORT_SCOPES,
        SlowLinkAnalyzer.RDMA: RDMA_SUPPORT_SCOPES
    }

    def __init__(self):
        self.dimensions = Interface.all_dimension
        self.kwargs = {}
        self.args_manager = None
        self.slow_rank_analyzer = None
        self.slow_link_analyzer = None
        self.cluster_local_data_map = {}
        self.default_rank_id = None
        self.rank_id_map = {}
        self._is_cluster = False
        self.analysis_process_resp = Manager().dict()

    @staticmethod
    def _set_analysis_process_priority(pid):
        # 将分析进程优先级设置为最低，避免因为分析进程阻塞其他任务进程，unix上19表示最低优先级
        unix_process_lowest_priority = 19
        windows_platform = "windows"
        linux_platform = "linux"
        p = psutil.Process(pid)
        if platform.system().lower() == windows_platform:
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        elif platform.system().lower() == linux_platform:
            p.nice(unix_process_lowest_priority)

    @staticmethod
    def _check_profiling_path_valid(profiling_path):
        PathManager.input_path_common_check(profiling_path)

        if not Path(profiling_path).exists():
            logger.error("Profiling path is not existed. Invalid profiling path: %s", profiling_path)
            return False

        return True


    @staticmethod
    def _get_step_rank_for_cluster_statistic_diff(target_cluster_statistic_data, benchmark_cluster_statistic_data,
                                                  headers, dimension, get_max=False):
        if dimension not in headers:
            logger.warning("Invalid dimension %s for cluster statistics data, optionals are %s.", dimension, headers)
            return None, None, None

        dimension_index = safe_index_value(headers, dimension)
        diff_record = []
        # 对比目标profiling和benchmark profiling 每张卡的计算和下发和带宽，取计算、下发、带宽差异最大的卡进行下一步分析
        for target_row_data, benchmark_row_data in zip(target_cluster_statistic_data, benchmark_cluster_statistic_data):
            target_data = safe_index(target_row_data, dimension_index)
            benchmark_data = safe_index(benchmark_row_data, dimension_index)

            if not isinstance(target_data, (int, float)) or not isinstance(benchmark_data, (int, float)):
                continue
            diff_record.append(target_data - benchmark_data)

        if SlowRankAnalyzer.compute_max_gap_ratio(diff_record, safe_division(sum(diff_record), len(
                diff_record))) < SlowRankAnalyzer.RATIO_THRESHOLD:
            return None, None, None

        value = max(diff_record) if get_max else min(diff_record)
        value_index = safe_index_value(diff_record, value)

        step_value_index = safe_index_value(headers, "step")
        rank_id_value_index = safe_index_value(headers, "rank_id")

        step = safe_index(safe_index(target_cluster_statistic_data, value_index, []), step_value_index)
        benchmark_step = safe_index(safe_index(benchmark_cluster_statistic_data, value_index, []), step_value_index)
        target_rank_id = safe_index(safe_index(target_cluster_statistic_data, value_index, []), rank_id_value_index)
        benchmark_rank_id = safe_index(safe_index(benchmark_cluster_statistic_data, value_index, []),
                                       rank_id_value_index)

        if target_rank_id != benchmark_rank_id:
            logger.error(
                "Rank ids of target profiling must keep the same as benchmark profiling, skip cluster comparison")
            return None, None, None

        return step, benchmark_step, target_rank_id

    @staticmethod
    def _init_async_analysis_env(kwargs):
        envs = kwargs.get("async_analysis_env", {})
        for key, value in envs.items():
            os.environ[key] = value

    def format_async_analysis_params(self, pid, async_resp, dimensions, kwargs):

        AsyncParams.parse_params(kwargs)
        dimensions = AsyncParams.user_total_params.get("analysis_dimensions") or dimensions

        if AsyncParams.user_invalid_values:
            error_msg = "Got invalid arguments as follows: \n "
            for index, invalid_value in enumerate(AsyncParams.user_invalid_values):
                error_msg += f"{index + 1}. Key '{invalid_value.get('key')}', " \
                             f"invalid value '{invalid_value.get('invalid value')}', " \
                             f"optional valid values '{invalid_value.get('optional values')}', " \
                             f"required value type '{invalid_value.get('required value type')}'.\n "
            self._update_analysis_process_resp(pid, async_resp, error_msg=error_msg,
                                               status_code=AsyncAnalysisStatus.BAD_REQUEST_STATUS_CODE,
                                               status=AsyncAnalysisStatus.FAILED)
            raise ValueError(error_msg)

        logger.warning("User parameters for async analysis is as follows:\n %s",
                       json.dumps(AsyncParams.user_total_params, indent=4))
        return dimensions, AsyncParams.user_total_params

    def do_analysis(self, dimensions, **kwargs):
        pid = os.getpid()
        resp = {"id": pid}
        self.args_manager = AdditionalArgsManager()
        self.args_manager.init(kwargs)
        output_path = kwargs.get("output_path")

        AnalyzerController._set_analysis_process_priority(pid)
        if kwargs.get("is_async_analysis"):
            del kwargs["is_async_analysis"]
            dimensions, kwargs = self.format_async_analysis_params(pid, resp, dimensions, kwargs)
            AnalyzerController._init_async_analysis_env(kwargs)

        try:
            if output_path:  # 前段传入空字符串视为正常场景，这里不能用is not None判断
                output_path = PathManager.get_realpath(output_path)
                if os.path.exists(output_path):
                    PathManager.check_output_directory_path(output_path)
                else:
                    PathManager.make_dir_safety(output_path)

                Config().set_config("_work_path", output_path)
            Config().set_log_path(f"mstt_advisor_{Timer().strftime}.xlsx")

            self._do_analysis(dimensions, pid=pid, async_resp=resp, **kwargs)
        except Exception as e:
            self._update_analysis_process_resp(pid, resp, status_code=AsyncAnalysisStatus.INNER_ERROR_STATUS_CODE,
                                               status=AsyncAnalysisStatus.FAILED, error_msg=str(e))
            logger.error(e)
            raise RuntimeError("Do analysis error.") from e

    def async_do_analysis(self, dimensions, **kwargs):
        """ Deploy a online service to start async analysis job, wrap this api by flask or tornado and so on,
            then could query the analysis status by restful api.
            You can view file 'profiler/msprof_analyze/advisor/config/enum_parameters.yaml' to obtain detailed
            information for all the args listed below.

        Args:
            dimensions: analysis dimension, normally set as Interface.all_dimension, support specific dimension analysis
                such as ['computation'] or ['computation', 'schedule']
            cann_version: cann version of your runtime, inpact on the analysis of affinity api and AICPU operators
            profiling_type: profiling type of your runtime
            profiling_version: profiling version of your runtime, inpact on the analysis of affinity api
            analysis_dimensions: can overwite dimensions.
            advisor_analyze_processes: number of processes to use while the training params pipeline parallel(pp) >1,
                can reduce the time of analysis.
            disable_profiling_comparison: disable comparison of operators(including npu computation operator and
                cpu torch aten operator), can reduce the time of analysis.
            disable_affinity_api: disable analysis of affinity api, normally set as 'True' while you training job
                has been trained on NPU for a long time and suddenly shows performance degradation.
            output_path: analysis output path(including html and xlsx).

        Example:
            >>> # initialize a global analyzer controller
            >>> analyzer_controller = AnalyzerController()
            >>> analysis_kwargs = dict(advisor_analyze_processes=2, disable_profiling_comparison=True)
            >>>
            >>> async_analysis_process = analyzer_controller.async_do_analysis(
            >>>                     Interface.all_dimension, **analysis_kwargs)
            >>>
            >>>
            >>> # query the job status every second
            >>> while True:
            >>>     response = analyzer_controller.get_response_by_pid(async_analysis_process.pid)
            >>>     print(f'analysis response is {response}')
            >>>     if response.get("status") in ["success", "failed"]:
            >>>         async_analysis_process.join()
            >>>          break
            >>>     time.sleep(1)
        """
        kwargs["is_async_analysis"] = True

        async_analysis_process = mp.Process(target=self.do_analysis, args=(dimensions,), kwargs=kwargs,
                                            name="Async advisor performance analysis")
        async_analysis_process.start()
        self._update_analysis_process_resp(async_analysis_process.pid, {"id": async_analysis_process.pid},
                                           status_code=AsyncAnalysisStatus.NON_FAILED_STATUS_CODE,
                                           status=AsyncAnalysisStatus.ANALYZING)
        return async_analysis_process

    def get_response_by_pid(self, pid):
        def _is_pid_exists(pid):
            try:
                psutil.Process(pid)
                return True
            except psutil.NoSuchProcess:
                return False

        pid_not_exist_response = dict(id=pid, status_code=AsyncAnalysisStatus.NOT_FOUND_STATUS_CODE,
                                      status=AsyncAnalysisStatus.FAILED,
                                      error_msg="The advisor task id does not exist")
        if pid not in self.analysis_process_resp:
            return pid_not_exist_response

        response = self.analysis_process_resp.get(pid)
        if response.get("status") not in [AsyncAnalysisStatus.FAILED,
                                          AsyncAnalysisStatus.SUCCESS] and not _is_pid_exists(pid):
            return pid_not_exist_response
        return response

    def single_rank_analysis(self, profiling_path, benchmark_profiling_path=None):
        job_list = []

        profiling_path = self._get_profiling_path_by_rank(profiling_path)
        benchmark_profiling_path = self._get_profiling_path_by_rank(benchmark_profiling_path)

        # 单卡场景无集群分析
        for dim in [Interface.CLUSTER]:
            if dim in self.dimensions:
                self.dimensions.remove(dim)

        for dimension in self.dimensions:
            dimension_analysis_func_name = f"{dimension}_analysis"
            if not hasattr(self, dimension_analysis_func_name):
                continue
            logger.info("Start %s analysis", dimension)
            job_list += getattr(self, dimension_analysis_func_name)(profiling_path)

        if benchmark_profiling_path:
            # kernel/api 比对
            compare_profiling_list = [
                dict(profiling_path=profiling_path, benchmark_profiling_path=benchmark_profiling_path,
                     compare_mode=Constant.KERNEL_COMPARE),
                dict(profiling_path=profiling_path, benchmark_profiling_path=benchmark_profiling_path,
                     compare_mode=Constant.API_COMPARE)
            ]

            job_list += self._profiling_comparison(compare_profiling_list)
        else:
            self.overall(profiling_path)

        return job_list

    def do_cluster_analysis(self, profiling_path, benchmark_profiling_path=None):
        job_list = []

        # 单集群profiling分析：下发、通信、计算、显存/内存
        for dimension in self.dimensions:
            dimension_analysis_func_name = f"cluster_{dimension}_analysis"
            if not hasattr(self, dimension_analysis_func_name):
                continue
            logger.info("Start cluster %s analysis", dimension)
            job_list += getattr(self, dimension_analysis_func_name)(profiling_path)

        self.overall(profiling_path)

        if benchmark_profiling_path:
            # 两个集群profiling比对分析
            job_list += self._cluster_profiling_comparison(profiling_path, benchmark_profiling_path)
        return job_list

    def overall(self, profiling_path):
        from msprof_analyze.advisor.analyzer.overall.environment_variable_analyzer import EnvironmentVariableAnalyzer
        env_analyzer = EnvironmentVariableAnalyzer(profiling_path)
        env_analyzer.optimize()

        if self._is_cluster:
            self.slow_rank_analyzer.optimize(template_key=Interface.OVERALL)
            self.slow_link_analyzer.optimize(template_key=Interface.OVERALL)
        else:
            overall_analyzer = OverallSummaryAnalyzer(profiling_path)
            overall_analyzer.optimize()

    def schedule_analysis(self, profiling_path, benchmark_profiling_path=None, step=None, benchmark_step=None,
                          **kwargs):
        # 任意单卡的下发分析

        input_kwargs = copy.deepcopy(self.kwargs)
        job_list = []

        input_kwargs["profiling_path"] = profiling_path
        input_kwargs["benchmark_profiling_path"] = benchmark_profiling_path
        input_kwargs["step"] = step
        input_kwargs["benchmark_step"] = benchmark_step
        input_kwargs["rank"] = kwargs.get("rank")
        input_kwargs["step_duration"] = kwargs.get("step_duration")

        for dimension in [Interface.SCHEDULE]:
            for scope in Interface.get_scope(dimension):
                interface = Interface(**input_kwargs)
                job_list.append((dimension, scope, interface, input_kwargs))
        return job_list

    def computation_analysis(self, profiling_path, benchmark_profiling_path=None, step=None,
                             benchmark_step=None, stage=None, **kwargs):
        # 任意单卡的计算分析

        input_kwargs = copy.deepcopy(self.kwargs)
        input_kwargs["profiling_path"] = profiling_path
        input_kwargs["benchmark_profiling_path"] = benchmark_profiling_path
        input_kwargs["step"] = step
        input_kwargs["benchmark_step"] = benchmark_step
        input_kwargs["stage"] = stage
        input_kwargs["rank"] = kwargs.get("rank")
        input_kwargs["step_duration"] = kwargs.get("step_duration")
        job_list = []

        for dimension in [Interface.COMPUTATION]:
            for scope in Interface.get_scope(dimension):
                if scope == SupportedScopes.STAGE_COMPUTE:
                    continue
                interface = Interface(**input_kwargs)
                job_list.append((dimension, scope, interface, input_kwargs))
        return job_list

    def memory_analysis(self, profiling_path, benchmark_profiling_path=None, step=None, benchmark_step=None, **kwargs):
        # 任意单卡的内存分析

        input_kwargs = copy.deepcopy(self.kwargs)
        job_list = []

        input_kwargs["profiling_path"] = profiling_path
        input_kwargs["benchmark_profiling_path"] = benchmark_profiling_path
        input_kwargs["step"] = step
        input_kwargs["benchmark_step"] = benchmark_step
        input_kwargs["rank"] = kwargs.get("rank")
        input_kwargs["step_duration"] = kwargs.get("step_duration")

        for dimension in [Interface.MEMORY]:
            for scope in Interface.get_scope(dimension):
                interface = Interface(**input_kwargs)
                job_list.append((dimension, scope, interface, input_kwargs))
        return job_list

    def communication_analysis(self, profiling_path, benchmark_profiling_path=None, **kwargs):

        job_list = []
        supported_trans_type = [SlowLinkAnalyzer.SDMA, SlowLinkAnalyzer.RDMA]
        step = kwargs.get("step", None)
        benchmark_step = kwargs.get("benchmark_step", None)
        bandwidth_type = kwargs.get("bandwidth_type", None)
        scope = kwargs.get("scope", None)
        if bandwidth_type is not None and bandwidth_type not in supported_trans_type:
            logger.error("Error transit type %s, optionals are %s", bandwidth_type, supported_trans_type)
            return job_list

        job_list += self._communication_analysis(profiling_path=profiling_path,
                                                 benchmark_profiling_path=benchmark_profiling_path,
                                                 step=step, benchmark_step=benchmark_step,
                                                 scope=scope, bandwidth_type=bandwidth_type)

        return job_list

    def cluster_schedule_analysis(self, profiling_path):
        # 目标集群profiling数据下发分析，不包含两个集群profiling数据的比对分析

        job_list = []
        global_step_rank = self.slow_rank_analyzer.get_global_step_rank(SlowRankAnalyzer.FREE)

        info_msg = "For cluster schedule analysis, "
        slow_rank_id = global_step_rank.get("maximum", {}).get("rank_id")
        if slow_rank_id is not None:
            info_msg += f"maximum free for rank {slow_rank_id}"
        else:
            slow_rank_id = self.default_rank_id
            info_msg += f"no slow rank with free time, analysis for default rank {slow_rank_id}"

        fast_rank_id = global_step_rank.get("minimum", {}).get("rank_id")

        slow_step = global_step_rank.get("maximum", {}).get("step")
        fast_step = global_step_rank.get("minimum", {}).get("step")

        if slow_step is not None:
            info_msg += f" and step {slow_step}"
        logger.info(info_msg)

        kwargs = dict(profiling_path=self._get_profiling_path_by_rank(profiling_path, slow_rank_id),
                      benchmark_profiling_path=self._get_profiling_path_by_rank(profiling_path, fast_rank_id),
                      step=slow_step, benchmark_step=fast_step,
                      rank=slow_rank_id, benchmark_rank=fast_rank_id,
                      compare_mode=Constant.API_COMPARE,
                      step_duration=self.slow_rank_analyzer.get_step_duration(slow_rank_id, slow_step))

        job_list += self.schedule_analysis(**kwargs)

        rank_id_valid = slow_rank_id is not None and fast_rank_id is not None and fast_rank_id != slow_rank_id
        if not self.kwargs.get("benchmark_profiling_path") and rank_id_valid:
            # 当用户指定benchmark profiling path时，不进行目标集群profiling的内部快慢卡对比
            logger.info("Enable schedule comparison of fast and slow rank/step")
            job_list += self._profiling_comparison([kwargs])
        return job_list

    def cluster_communication_analysis(self, profiling_path):
        job_list = []

        for dimension in [Interface.COMMUNICATION]:
            for scope in Interface.get_scope(dimension):
                analyzer_class = Interface.get_analyzer(dimension, scope)
                if hasattr(analyzer_class, "requires_cluster_dataset") and getattr(analyzer_class,
                                                                                   "requires_cluster_dataset"):

                    # 如果不依赖数据集，或者依赖的是ClusterDataset，则不用根据带宽确定需要分析的特定rank
                    kwargs = copy.deepcopy(self.kwargs)
                    kwargs["profiling_path"] = profiling_path
                    interface = Interface(**kwargs)
                    job_list.append((dimension, scope, interface, kwargs))
                else:
                    # 非ClusterDataset场景，需要根据带宽大小分析特定的rank
                    for bandwidth_type in [SlowLinkAnalyzer.SDMA, SlowLinkAnalyzer.RDMA]:
                        global_step_rank = self.slow_link_analyzer.get_global_step_rank(bandwidth_type)
                        # 获取带宽最小的卡进行分析
                        target_rank_id = global_step_rank.get("minimum", {}).get("rank_id")
                        if target_rank_id is None:
                            target_rank_id = self.default_rank_id
                        step = global_step_rank.get("minimum", {}).get("step")
                        analysis_profiling_path = self._get_profiling_path_by_rank(profiling_path, target_rank_id)

                        info_msg = f"Minimum {bandwidth_type} bandwidth for rank {target_rank_id} "
                        if step:
                            info_msg += f"and step {step}"
                        logger.info(info_msg)

                        job_list += self.communication_analysis(analysis_profiling_path, step=step,
                                                                bandwidth_type=bandwidth_type, scope=scope)

        return job_list

    def cluster_computation_analysis(self, profiling_path):
        # 目标集群profiling数据计算分析，不包含两个集群profiling数据的比对分析；如果有pp stage，则对不同stage进行计算分析

        job_list = []
        global_step_rank = self.slow_rank_analyzer.get_global_step_rank(SlowRankAnalyzer.COMPUTE)
        stage_step_rank = self.slow_rank_analyzer.get_stage_step_rank(SlowRankAnalyzer.COMPUTE)

        if stage_step_rank:
            job_list = self._stage_computation_analysis(profiling_path, stage_step_rank, job_list)
        else:
            job_list = self._global_computation_analysis(profiling_path, global_step_rank, job_list)
        return job_list

    def cluster_memory_analysis(self, profiling_path):
        # 目标集群profiling数据内存分析，当前memory识别的两个算子，导致的问题都是大的free，因此选择FREE最慢的卡进行分析

        job_list = []
        global_step_rank = self.slow_rank_analyzer.get_global_step_rank(SlowRankAnalyzer.FREE)

        info_msg = "For cluster memory analysis, "
        slow_rank_id = global_step_rank.get("maximum", {}).get("rank_id")
        if slow_rank_id is not None:
            info_msg += f"maximum free for rank {slow_rank_id}"
        else:
            slow_rank_id = self.default_rank_id
            info_msg += f"no slow rank with free time, analysis for default rank {slow_rank_id}"

        slow_step = global_step_rank.get("maximum", {}).get("step")
        if slow_step is not None:
            info_msg += f" and step {slow_step}"
        logger.info(info_msg)

        analysis_profiling_path = self._get_profiling_path_by_rank(profiling_path, slow_rank_id)
        step_duration = self.slow_rank_analyzer.get_step_duration(slow_rank_id, slow_step)
        job_list += self.memory_analysis(analysis_profiling_path, step=slow_step, rank=slow_rank_id,
                                         step_duration=step_duration)
        return job_list

    def _do_analysis(self, dimensions, pid=0, async_resp=None, **kwargs):
        self.dimensions = dimensions
        self.kwargs = kwargs
        result_list = []
        profiling_path = PathManager.get_realpath(self.kwargs.get("profiling_path"))
        benchmark_profiling_path = self.kwargs.get("benchmark_profiling_path")
        PathManager.check_input_directory_path(profiling_path)
        if benchmark_profiling_path:  # 前段传入空字符串视为正常场景，这里不能用is not None判断
            benchmark_profiling_path = PathManager.get_realpath(benchmark_profiling_path)
            PathManager.check_input_directory_path(benchmark_profiling_path)

        if not self._check_profiling_path_valid(profiling_path):
            error_msg = f"Got invalid argument '-d/--profiling_path' {profiling_path}, skip analysis"
            self._update_analysis_process_resp(pid, async_resp, error_msg=error_msg,
                                               status_code=AsyncAnalysisStatus.BAD_REQUEST_STATUS_CODE,
                                               status=AsyncAnalysisStatus.FAILED)
            logger.error(error_msg)
            return


        if benchmark_profiling_path and not self._check_profiling_path_valid(benchmark_profiling_path):
            error_msg = (f"Got invalid argument '-bp/--benchmark_profiling_path' {benchmark_profiling_path}, "
                         f"skip analysis")
            self._update_analysis_process_resp(pid, async_resp, error_msg=error_msg,
                                               status_code=AsyncAnalysisStatus.BAD_REQUEST_STATUS_CODE,
                                               status=AsyncAnalysisStatus.FAILED)
            logger.error(error_msg)
            return

        self._is_cluster = self._is_cluster_profiling(profiling_path)
        if benchmark_profiling_path:
            # 构建benchmark profiling的map，用于根据rank获取profiling路径，否则无法进行比对
            is_benchmark_cluster = self._is_cluster_profiling(benchmark_profiling_path)
            is_comparison_path_valid = (self._is_cluster and is_benchmark_cluster) or (
                    not self._is_cluster and not is_benchmark_cluster)
            if not is_comparison_path_valid:
                error_msg = f"Only support profiling comparison for '1 npu vs 1 gpu/npu' and 'multi npus vs multi npus'"
                self._update_analysis_process_resp(pid, async_resp, error_msg=error_msg,
                                                   status_code=AsyncAnalysisStatus.BAD_REQUEST_STATUS_CODE,
                                                   status=AsyncAnalysisStatus.FAILED)
                logger.error(error_msg)
                return

        if not self._is_cluster:
            job_list = self.single_rank_analysis(profiling_path, benchmark_profiling_path)
        else:
            self.slow_rank_analyzer = SlowRankAnalyzer(profiling_path, output_path=self.kwargs.get("output_path"))
            self.slow_link_analyzer = SlowLinkAnalyzer(profiling_path, output_path=self.kwargs.get("output_path"))
            job_list = self.do_cluster_analysis(profiling_path, benchmark_profiling_path)

        for i, (dimension, scope, interface, kwargs) in enumerate(job_list[::-1]):
            result_list.append(
                interface.get_result(dimension, scope, render_html=i == len(job_list) - 1, output_dict=False,
                                     **kwargs)
            )

        for result in result_list[::-1]:
            if result and hasattr(result, "show"):
                result.show()
                break
        self._get_analysis_finished_resp(pid, async_resp)

    def _get_scopes(self, scope=None, bandwidth_type=SlowLinkAnalyzer.SDMA):
        """
        Args:
            scope: analyzer type
            bandwidth_type: analysis standard
        Returns:
            scope lists
        """
        scopes = []
        if scope:
            if scope in self.COMMUNICATION_MAPPING.get(bandwidth_type, self.SDMA_SUPPORT_SCOPES):
                scopes.append(scope)
            return scopes
        for dimension in [Interface.COMMUNICATION]:
            for scope_ in Interface.get_scope(dimension):
                if scope_ in self.SDMA_SUPPORT_SCOPES or scope_ in self.RDMA_SUPPORT_SCOPES:
                    scopes.append(scope_)
        return scopes

    def _communication_analysis(self, **child_kwargs):
        kwargs = copy.deepcopy(self.kwargs)
        job_list = []

        kwargs["profiling_path"] = child_kwargs.get("profiling_path", "")
        kwargs["benchmark_profiling_path"] = child_kwargs.get("benchmark_profiling_path", "")
        kwargs["step"] = child_kwargs.get("step", -1)
        kwargs["benchmark_step"] = child_kwargs.get("benchmark_step", -1)
        bandwidth_type = child_kwargs.get("bandwidth_type", SlowLinkAnalyzer.SDMA)
        scope = child_kwargs.get("scope", None)

        for scope_ in self._get_scopes(scope, bandwidth_type):
            interface = Interface(**kwargs)
            job_list.append((Interface.COMMUNICATION, scope_, interface, kwargs))

        return job_list

    def _profiling_comparison(self, compare_profiling_list):
        job_list = []
        disable_profiling_comparison = os.getenv(Constant.DISABLE_PROFILING_COMPARISON)
        if disable_profiling_comparison is not None and disable_profiling_comparison.lower() == "true":
            logger.info(
                "Skip profiling comparison due to longer processing time due to env 'DISABLE_PROFILING_COMPARISON'")
            return job_list
        kwargs = {}
        for index, _kwargs in enumerate(compare_profiling_list):
            kwargs = copy.deepcopy(self.kwargs)
            kwargs.update(_kwargs)
            compare_profiling_list[index] = kwargs
        compare_kwargs = {
            "profiling_path": kwargs.get("profiling_path"),
            "compare_profiling_list": compare_profiling_list,
        }

        interface = Interface(**compare_kwargs)
        job_list.append((Interface.COMPARISON, SupportedScopes.COMPARISON, interface, compare_kwargs))

        return job_list

    def _cluster_profiling_comparison(self, profiling_path, benchmark_profiling_path):
        # 从计算、下发和通信三个维度对集群profiling数据进行对比

        job_list = []
        benchmark_profiling_path = self._get_profiling_path_by_rank(benchmark_profiling_path)
        benchmark_slow_rank_analyzer = SlowRankAnalyzer(benchmark_profiling_path)
        benchmark_slow_link_analyzer = SlowLinkAnalyzer(benchmark_profiling_path)

        # 计算和下发分析
        job_list += self._cluster_data_comparison(profiling_path,
                                                  benchmark_profiling_path,
                                                  self.slow_rank_analyzer,
                                                  benchmark_slow_rank_analyzer,
                                                  get_max=True)

        # 通信分析
        job_list += self._cluster_data_comparison(profiling_path,
                                                  benchmark_profiling_path,
                                                  self.slow_link_analyzer,
                                                  benchmark_slow_link_analyzer,
                                                  get_max=False)
        return job_list

    def _cluster_data_comparison(self, profiling_path, benchmark_profiling_path, target_cluster_analyzer,
                                 benchmark_cluster_analyzer, get_max=False):
        # #low rank/slow link结果逐行对比获取差值最大的rank和step进行单卡分析
        job_list = []

        if isinstance(target_cluster_analyzer, SlowRankAnalyzer):
            comparison_dims = [SlowRankAnalyzer.COMPUTE, SlowRankAnalyzer.FREE]
            comparison_modes = [Constant.KERNEL_COMPARE, Constant.API_COMPARE]
        elif isinstance(target_cluster_analyzer, SlowLinkAnalyzer):
            comparison_dims = [SlowLinkAnalyzer.SDMA_BANDWIDTH, SlowLinkAnalyzer.RDMA_BANDWIDTH]
            comparison_modes = [None, None]
        else:
            return job_list

        target_data = target_cluster_analyzer.format_datas.get("data", [])
        benchmark_data = benchmark_cluster_analyzer.format_datas.get("data", [])
        headers = benchmark_cluster_analyzer.format_datas.get("headers", [])

        if len(target_data) != len(benchmark_data):
            logger.warning(
                "The product of ranks and steps of Benchmark profiling is not equals to target profiling, "
                "skip cluster comparison.")
            return job_list

        compare_profiling_list = []
        for dimension, compare_mode in zip(comparison_dims, comparison_modes):
            step, benchmark_step, rank_id_for_comparison = AnalyzerController._get_step_rank_for_cluster_statistic_diff(
                target_data,
                benchmark_data,
                headers,
                dimension,
                get_max=get_max
            )

            rank_profiling_path = self._get_profiling_path_by_rank(profiling_path, rank_id_for_comparison)
            rank_benchmark_profiling_path = self._get_profiling_path_by_rank(
                benchmark_profiling_path,
                rank_id_for_comparison
            )

            if rank_id_for_comparison is None:
                # rank id为空则无法获取对应rank的profiling路径，无法进行比较
                continue

            compare_profiling_list.append(
                dict(profiling_path=rank_profiling_path, benchmark_profiling_path=rank_benchmark_profiling_path,
                     step=step, benchmark_step=benchmark_step,
                     rank=rank_id_for_comparison, benchmark_rank=rank_id_for_comparison, compare_mode=compare_mode)
            )

        if not compare_profiling_list:
            return job_list

        job_list += self._profiling_comparison(compare_profiling_list)
        return job_list

    def _is_cluster_profiling(self, profiling_path):
        if os.path.isfile(profiling_path):
            return False
        path_list = [os.path.join(profiling_path, dir_name) for dir_name in os.listdir(profiling_path)]
        ascend_pt_dirs = [path for path in path_list if os.path.isdir(path) and path.endswith("ascend_pt")]
        ascend_ms_dirs = [path for path in path_list if os.path.isdir(path) and path.endswith("ascend_ms")]
        if ascend_ms_dirs and ascend_pt_dirs:
            logger.error("Cannot analyze pytorch and mindspore meantime.")
            return False
        if not ascend_pt_dirs and not ascend_ms_dirs:
            return False
        if ascend_ms_dirs and not ascend_pt_dirs:
            data_processor = MindsporeDataPreprocessor(ascend_ms_dirs)
        elif ascend_pt_dirs and not ascend_ms_dirs:
            data_processor = PytorchDataPreprocessor(ascend_pt_dirs)

        self.cluster_local_data_map[profiling_path] = data_processor.get_data_map()

        if not self.cluster_local_data_map or not self.cluster_local_data_map.get(profiling_path):
            return False

        self.default_rank_id = list(self.cluster_local_data_map[profiling_path].keys())[0]

        return len(self.cluster_local_data_map[profiling_path]) >= self.CLUSTER_RANK_THRESHOLD

    def _get_profiling_path_by_rank(self, profiling_path, rank_id=None):

        if not profiling_path:
            return profiling_path

        return self._get_target_profiling_path_for_local(profiling_path, rank_id)

    def _get_target_profiling_path_for_local(self, profiling_path, rank_id):
        rank_id_map = self.cluster_local_data_map.get(profiling_path, {})
        if rank_id is None or not rank_id_map:
            return profiling_path

        if rank_id in rank_id_map:
            return rank_id_map.get(rank_id)

        local_first_rank_id = sorted(list(map(int, rank_id_map.keys())))[0]
        logger.warning("Target rank id %s does not exist in local profiling data %s, use rank %s for analysis",
                       rank_id, profiling_path, local_first_rank_id)
        return rank_id_map.get(local_first_rank_id)

    def _update_analysis_process_resp(self, pid, resp, **kwargs):
        if kwargs:
            resp.update(kwargs)
        self.analysis_process_resp[pid] = resp

    def _get_analysis_finished_resp(self, pid, resp):
        advisor_output_file_prefix = f"mstt_advisor_{Timer().strftime}"
        html_path = os.path.join(Config().work_path, f"{advisor_output_file_prefix}.html")
        xlsx_path = os.path.join(Config().work_path, "log", f"{advisor_output_file_prefix}.xlsx")
        if os.path.exists(html_path) and os.path.exists(xlsx_path):
            result_files = {"html": html_path, "xlsx": xlsx_path}
            self._update_analysis_process_resp(pid, resp, status_code=AsyncAnalysisStatus.NON_FAILED_STATUS_CODE,
                                               status=AsyncAnalysisStatus.SUCCESS, result_files=result_files)
        else:
            self._update_analysis_process_resp(pid, resp, status_code=AsyncAnalysisStatus.BAD_REQUEST_STATUS_CODE,
                                               status=AsyncAnalysisStatus.FAILED,
                                               error_msg="No optimization suggestions, please check your input path.")

    def _stage_computation_analysis(self, profiling_path, stage_step_rank, job_list):
        # 对不同pp stage取min max进行分析
        logger.info("Steps and ranks to be analyzed of different pipeline parallel stages are %s",
                    json.dumps(stage_step_rank))

        stages_profiling_path = []
        for stage, step_rank_info in stage_step_rank.items():
            rank_id = step_rank_info.get("maximum", {}).get("rank_id")
            step = step_rank_info.get("maximum", {}).get("step")
            benchmark_rank_id = step_rank_info.get("minimum", {}).get("rank_id")
            benchmark_step = step_rank_info.get("minimum", {}).get("step")

            info_msg = f"For {stage}, slow rank is {rank_id}"
            if step:
                info_msg += f", step is {step}"
            logger.info(info_msg)

            stages_profiling_path.append(
                dict(
                    stage=stage, rank=rank_id, step=step, benchmark_rank=benchmark_rank_id,
                    benchmark_step=benchmark_step,
                    profiling_path=self._get_profiling_path_by_rank(profiling_path, rank_id),
                    benchmark_profiling_path=self._get_profiling_path_by_rank(profiling_path, benchmark_rank_id),
                    compare_mode=Constant.KERNEL_COMPARE,
                    step_duration=self.slow_rank_analyzer.get_step_duration(rank_id, step)
                )
            )
        Interface.add_analyzer(Interface.COMPUTATION, SupportedScopes.STAGE_COMPUTE, PPStageComputationAnalyzer)
        compute_analysis_kwargs = {"stages_profiling_path": stages_profiling_path, "profiling_path": profiling_path}

        job_list.append((Interface.COMPUTATION, SupportedScopes.STAGE_COMPUTE, Interface(**compute_analysis_kwargs),
                         compute_analysis_kwargs))
        if not self.kwargs.get("benchmark_profiling_path"):
            logger.info("Enable computation comparison of fast and slow rank/step in different pp stages")
            job_list += self._profiling_comparison(stages_profiling_path)
        return job_list

    def _global_computation_analysis(self, profiling_path, global_step_rank, job_list):
        # 不区分stage，对所有卡取Min max进行分析
        logger.info("Without pipeline parallel stage, steps and ranks to be analyzed are %s",
                    json.dumps(global_step_rank))
        slow_rank_id = global_step_rank.get("maximum", {}).get("rank_id")
        if slow_rank_id is not None:
            info_msg = f"Maximum computation time for rank {slow_rank_id}"
        else:
            slow_rank_id = self.default_rank_id
            info_msg = f"No slow rank with computation time, analysis for default rank {slow_rank_id}"
        slow_step = global_step_rank.get("maximum", {}).get("step")
        # 如果没有标杆profiling数据的rank id，说明没有快慢卡问题，直接对默认rank id进行分析，因此这里取值为None
        fast_rank_id = global_step_rank.get("minimum", {}).get("rank_id")
        fast_step = global_step_rank.get("minimum", {}).get("step")

        if slow_step is not None:
            info_msg += f" and step {slow_step}, "
        if fast_rank_id is not None:
            info_msg += f"minimum computation time for rank {fast_rank_id}"
        if fast_step is not None:
            info_msg += f" and step {fast_step}"
        logger.info(info_msg)

        kwargs = dict(profiling_path=self._get_profiling_path_by_rank(profiling_path, slow_rank_id),
                      benchmark_profiling_path=self._get_profiling_path_by_rank(profiling_path, fast_rank_id),
                      step=slow_step, benchmark_step=fast_step, rank=slow_rank_id, benchmark_rank=fast_rank_id,
                      compare_mode=Constant.KERNEL_COMPARE,
                      step_duration=self.slow_rank_analyzer.get_step_duration(slow_rank_id, slow_step))

        job_list += self.computation_analysis(**kwargs)

        rank_id_valid = slow_rank_id is not None and fast_rank_id is not None and fast_rank_id != slow_rank_id
        if not self.kwargs.get("benchmark_profiling_path") and rank_id_valid:
            # 当用户指定benchmark profiling path时，不进行目标集群profiling的内部快慢卡对比
            logger.info("Enable computation comparison of fast and slow rank/step")
            job_list += self._profiling_comparison([kwargs])
        return job_list
