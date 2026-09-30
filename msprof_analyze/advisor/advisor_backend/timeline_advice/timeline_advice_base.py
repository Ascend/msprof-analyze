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

from msprof_analyze.prof_common.logger import get_logger
import os
from abc import abstractmethod
from collections import defaultdict

from msprof_analyze.advisor.advisor_backend.advice_base import AdviceBase
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class TimelineAdviceBase(AdviceBase):
    class PreParseType:
        OPTIMIZER = 0
        STEP = 1
        OVERLAP_CPT = 2
        OVERLAP_FREE = 3
        OVERLAP_CMU = 4
        ENQUEUE = 5
        DEQUEUE = 6
        HOST_TO_DEVICE = 7
        SYNCHRONIZE = 8

    def __init__(self, collection_path: str):
        super().__init__(collection_path)
        self.trace_view_path = ""
        self.has_preparse = False
        self.preparse_data = defaultdict(list)
        self.cur_data = None
        self.cur_bottleneck = None
        self.cur_advice = None
        self.entry_map = {
            'Computing': self.PreParseType.OVERLAP_CPT,
            'Free': self.PreParseType.OVERLAP_FREE,
            'AscendCL@aclrtSynchronizeDevice': self.PreParseType.SYNCHRONIZE,
        }

    def path_check(self):
        """
        check whether input path is valid
        """
        if not os.path.exists(self.collection_path):
            logger.error("Path: %s is not exist.", str(self.collection_path))
            return False
        if os.path.isdir(self.collection_path) and (
            self.collection_path.endswith("ascend_pt") or self.collection_path.endswith("ascend_ms")
        ):
            self.trace_view_path = os.path.join(self.collection_path, "ASCEND_PROFILER_OUTPUT", "trace_view.json")
            if not os.path.exists(self.trace_view_path):
                logger.error(
                    "trace_view.json is not exist in the Path: %s.",
                    str(os.path.join(self.collection_path, "ASCEND_PROFILER_OUTPUT")),
                )
                return False
        elif os.path.isfile(self.collection_path) and os.path.basename(self.collection_path) == "trace_view.json":
            self.trace_view_path = self.collection_path
        else:
            logger.error("Please input ascend_pt or trace_view.json.")
            return False
        logger.info("Start to analyse the target file: %s", str(self.trace_view_path))
        return True

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
            return
        json_reader = FileManager.read_json_file(self.trace_view_path)
        if not isinstance(json_reader, list):
            return
        for entry in json_reader:
            name = entry.get("name", None)
            if not name:
                continue
            if name.startswith("Optimizer.step#") and name.endswith(".step"):
                self.preparse_data[self.PreParseType.OPTIMIZER].append(entry)
            elif name.startswith("ProfilerStep#"):
                self.preparse_data[self.PreParseType.STEP].append(entry)
            elif name in self.entry_map:
                self.preparse_data[self.entry_map[name]].append(entry)
        self.has_preparse = True
