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
import os.path
import re

from msprof_analyze.compare_tools.compare_backend.utils.singleton import Singleton
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


@Singleton
class ArgsManager:
    __slots__ = ['_args', '_base_path_dict', '_comparison_path_dict', '_base_step', '_comparison_step']

    def __init__(self, args: any):
        self._args = args
        self._base_path_dict = {}
        self._comparison_path_dict = {}
        self._base_step = Constant.VOID_STEP
        self._comparison_step = Constant.VOID_STEP

    @property
    def args(self):
        return self._args

    @property
    def base_profiling_type(self):
        return self._base_path_dict.get(Constant.PROFILING_TYPE)

    @property
    def comparison_profiling_type(self):
        return self._comparison_path_dict.get(Constant.PROFILING_TYPE)

    @property
    def base_profiling_path(self):
        return self._args.base_profiling_path

    @property
    def comparison_profiling_path(self):
        return self._args.comparison_profiling_path

    @property
    def base_path_dict(self):
        return self._base_path_dict

    @property
    def comparison_path_dict(self):
        return self._comparison_path_dict

    @property
    def base_step(self):
        return self._base_step

    @property
    def comparison_step(self):
        return self._comparison_step

    @property
    def enable_profiling_compare(self):
        return self._args.enable_profiling_compare

    @property
    def enable_operator_compare(self):
        return self._args.enable_operator_compare

    @property
    def enable_memory_compare(self):
        return self._args.enable_memory_compare

    @property
    def enable_communication_compare(self):
        return self._args.enable_communication_compare

    @property
    def enable_api_compare(self):
        return self._args.enable_api_compare

    @property
    def enable_kernel_compare(self):
        return self._args.enable_kernel_compare

    @property
    def use_kernel_type(self):
        return self._args.use_kernel_type

    @classmethod
    def check_profiling_path(cls, path_dict: dict):
        path_list = (
            [path_dict.get(Constant.PROFILING_PATH, "")]
            if path_dict.get(Constant.PROFILING_TYPE) == Constant.GPU
            else [
                path_dict.get(Constant.PROFILING_PATH, ""),
                path_dict.get(Constant.TRACE_PATH, ""),
                path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""),
                path_dict.get(Constant.INFO_JSON_PATH, ""),
                os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "operator_memory.csv"),
                os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "memory_record.csv"),
                os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "kernel_details.csv"),
                os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "communication.json"),
            ]
        )
        for path in path_list:
            if path and os.path.exists(path):
                if os.path.isfile(path):
                    PathManager.check_input_file_path(path)
                else:
                    PathManager.check_input_directory_path(path)

    @classmethod
    def check_output_path(cls, output_path: str):
        if os.path.exists(output_path):
            PathManager.check_output_directory_path(output_path)
        else:
            PathManager.make_dir_safety(output_path)

    @classmethod
    def parse_profiling_path(cls, file_path: str):
        # 处理输入为单个文件的情况
        if os.path.isfile(file_path):
            PathManager.check_input_file_path(file_path)
            (split_file_path, split_file_name) = os.path.split(file_path)
            (shot_name, extension) = os.path.splitext(split_file_name)
            if extension == ".json":
                json_type = FileManager.check_json_type(file_path)
                return {
                    Constant.PROFILING_TYPE: json_type,
                    Constant.PROFILING_PATH: file_path,
                    Constant.TRACE_PATH: file_path,
                }
            elif extension == ".db":
                if shot_name.startswith(("ascend_pytorch_profiler", "ascend_mindspore_profiler", "msmonitor")):
                    return {
                        Constant.PROFILING_TYPE: Constant.NPU,
                        Constant.PROFILING_PATH: file_path,
                        Constant.PROFILER_DB_PATH: file_path,
                    }
            else:
                msg = f"Invalid profiling path suffix: {file_path}"
                raise RuntimeError(msg)
        PathManager.check_input_directory_path(file_path)
        path_dict = {}
        sub_dirs = os.listdir(file_path)
        for dir_name in sub_dirs:
            if dir_name == "profiler_info.json" or re.match(r"profiler_info_[0-9]+\.json", dir_name):
                path_dict[Constant.INFO_JSON_PATH] = os.path.join(file_path, dir_name)
                break

        ascend_output = os.path.join(file_path, "ASCEND_PROFILER_OUTPUT")
        profiler_output = ascend_output if os.path.isdir(ascend_output) else file_path
        sub_dirs = os.listdir(profiler_output)
        for sub_dir in sub_dirs:
            if sub_dir.startswith(
                ("ascend_pytorch_profiler", "ascend_mindspore_profiler", "msmonitor")
            ) and sub_dir.endswith(".db"):
                db_path = os.path.join(profiler_output, sub_dir)
                path_dict.update(
                    {
                        Constant.PROFILING_TYPE: Constant.NPU,
                        Constant.PROFILING_PATH: file_path,
                        Constant.PROFILER_DB_PATH: db_path,
                        Constant.ASCEND_OUTPUT_PATH: profiler_output,
                    }
                )
                return path_dict

        json_path = os.path.join(profiler_output, "trace_view.json")
        if not os.path.isfile(json_path):
            msg = (
                f"The data is not collected by PyTorch or Mindspore mode or the data is not parsed. "
                f"Invalid profiling path: {profiler_output}"
            )
            raise RuntimeError(msg)
        path_dict.update(
            {
                Constant.PROFILING_TYPE: Constant.NPU,
                Constant.PROFILING_PATH: file_path,
                Constant.TRACE_PATH: json_path,
                Constant.ASCEND_OUTPUT_PATH: profiler_output,
            }
        )
        return path_dict

    def get_step_args_with_validating(self):
        if self._args.base_step and self._args.comparison_step:
            if all([self._args.base_step.isdigit(), self._args.comparison_step.isdigit()]):
                self._base_step = int(self._args.base_step)
                self._comparison_step = int(self._args.comparison_step)
            else:
                msg = "Invalid param, base_step and comparison_step must be a number."
                raise RuntimeError(msg)
        elif any([self._args.base_step, self._args.comparison_step]):
            msg = "Invalid param, base_step and comparison_step must be set at the same time."
            raise RuntimeError(msg)

    def init(self):
        if self._args.max_kernel_num is not None and self._args.max_kernel_num <= Constant.LIMIT_KERNEL:
            msg = f"Invalid param, --max_kernel_num has to be greater than {Constant.LIMIT_KERNEL}"
            raise RuntimeError(msg)
        if not isinstance(self._args.op_name_map, dict):
            raise RuntimeError(
                "Invalid param, --op_name_map must be dict, for example: --op_name_map={'name1':'name2'}"
            )
        op_names = list(self._args.op_name_map.keys()) + list(self._args.op_name_map.values())
        if any(not isinstance(op_name, str) for op_name in op_names):
            raise RuntimeError("Invalid param, key/value in --op_name_map must be string")
        if any(len(op_name) > Constant.MAX_OP_NAME_LEN for op_name in op_names):
            msg = (
                f"Invalid param, the length of key/value in --op_name_map exceeded the maximum value"
                f" {Constant.MAX_OP_NAME_LEN}"
            )
            raise RuntimeError(msg)
        if self._args.gpu_flow_cat and len(self._args.gpu_flow_cat) > Constant.MAX_FLOW_CAT_LEN:
            msg = f"Invalid param, --gpu_flow_cat exceeded the maximum value {Constant.MAX_FLOW_CAT_LEN}"
            raise RuntimeError(msg)

        if not any(
            [
                self._args.enable_profiling_compare,
                self._args.enable_operator_compare,
                self._args.enable_memory_compare,
                self._args.enable_communication_compare,
                self._args.enable_api_compare,
                self._args.enable_kernel_compare,
            ]
        ):
            self._args.enable_profiling_compare = True
            self._args.enable_operator_compare = True
            self._args.enable_memory_compare = True
            self._args.enable_communication_compare = True
            self._args.enable_api_compare = True
            self._args.enable_kernel_compare = True
        if not self._args.enable_kernel_compare and self._args.use_kernel_type:
            logger.warning(
                "The use_kernel_type parameter is invalid because it only takes effect "
                "when enable_kernel_compare is enabled."
            )
        self.get_step_args_with_validating()
        self._base_path_dict = self.parse_profiling_path(PathManager.get_realpath(self._args.base_profiling_path))
        self.check_profiling_path(self._base_path_dict)
        self._comparison_path_dict = self.parse_profiling_path(
            PathManager.get_realpath(self._args.comparison_profiling_path)
        )
        self.check_profiling_path(self._comparison_path_dict)
        if self._args.output_path:
            self.check_output_path(PathManager.get_realpath(self._args.output_path))

    def set_compare_type(self, compare_type: str):
        self._args.enable_profiling_compare = False
        self._args.enable_operator_compare = False
        self._args.enable_api_compare = False
        self._args.enable_kernel_compare = False
        self._args.enable_memory_compare = False
        self._args.enable_communication_compare = False
        if compare_type == Constant.OVERALL_COMPARE:
            self._args.enable_profiling_compare = True
        elif compare_type == Constant.OPERATOR_COMPARE:
            self._args.enable_operator_compare = True
        elif compare_type == Constant.API_COMPARE:
            self._args.enable_api_compare = True
        elif compare_type == Constant.KERNEL_COMPARE:
            self._args.enable_kernel_compare = True
        else:
            msg = f"Invalid compare_type: {compare_type}, please check it."
            raise RuntimeError(msg)
