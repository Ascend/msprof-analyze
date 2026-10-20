# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2023 Huawei Technologies Co.,Ltd.
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

from abc import abstractmethod
from collections import defaultdict
import os
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.advisor.advisor_backend.advice_base import AdviceBase
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class ComputeAdviceBase(AdviceBase):
    ASCEND_PT = 'ascend_pt'
    ASCEND_PROFILER_OUTPUT = 'ASCEND_PROFILER_OUTPUT'
    KERNEL_DETAIL_FILE = "kernel_details.csv"
    TRACE_VIEW_FILE = "trace_view.json"

    def __init__(self, collection_path: str):
        super().__init__(collection_path)
        self.kernel_details_path = ""
        self.has_preparse = False
        self.preparse_data = defaultdict(list)
        self.call_stack = False
        self.trace_view_path = ""
        self.cur_data = None
        self.cur_bottleneck = None
        self.cur_advice = None

    def path_check(self):
        """
        check whether input path is valid
        """
        if not os.path.exists(self.collection_path):
            logger.error("Path: %s is not exist.", self.collection_path)
            return False
        if os.path.isdir(self.collection_path) and (
            self.collection_path.endswith("ascend_pt") or self.collection_path.endswith("ascend_ms")
        ):
            self.kernel_details_path = os.path.join(
                self.collection_path, "ASCEND_PROFILER_OUTPUT", "kernel_details.csv"
            )
            if not os.path.exists(self.kernel_details_path):
                logger.error(
                    "kernel_details.csv is not exist in the Path: %s.",
                    os.path.join(self.collection_path, "ASCEND_PROFILER_OUTPUT"),
                )
                return False
        elif os.path.isfile(self.collection_path) and os.path.basename(self.collection_path) == "kernel_details.csv":
            self.kernel_details_path = self.collection_path
        else:
            logger.error("Please input ascend_pt or kernel_details.csv")
            return False
        logger.info("Start to analyse the target file: %s", self.kernel_details_path)
        self.preparse()
        return True

    def has_callstack(self):
        profiler_info_json_path = ""
        for file in os.listdir(self.collection_path):
            if file.startswith("profiler_info"):
                profiler_info_json_path = os.path.join(self.collection_path, file)
                break
        if not profiler_info_json_path:
            return self.call_stack
        self.trace_view_path = os.path.join(self.collection_path, self.ASCEND_PROFILER_OUTPUT, "trace_view.json")
        if not os.path.exists(profiler_info_json_path) or not os.path.exists(self.trace_view_path):
            return self.call_stack
        info = FileManager.read_json_file(profiler_info_json_path)
        if (
            not info.get("config")
            or not info.get("config").get("common_config")
            or not info.get("config").get("common_config").get("with_stack")
        ):
            return self.call_stack
        activities = info.get("config").get("common_config").get("activities")
        if not activities or "ProfilerActivity.CPU" not in activities:
            return self.call_stack
        self.call_stack = info.get("config").get("common_config").get("with_stack")
        return self.call_stack

    @abstractmethod
    def run(self):
        """
        analyze profiling data and advice
        """

    @abstractmethod
    def output(self):
        """
        output relevant data
        """
        self.output_format_data[self.DATA] = self.cur_data
        self.output_format_data[self.BOTTLENECK] = self.cur_bottleneck
        self.output_format_data[self.ADVICE] = self.cur_advice

    def preparse(self):
        if self.has_preparse:
            pass
