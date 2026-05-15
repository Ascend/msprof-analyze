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


import re
import sys
from typing import Optional
from dataclasses import dataclass

from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


@dataclass
class FineTraceViewData:
    py_pid: int = -1
    fp_tid: int = -1
    bp_tid: int = -1
    ascend_pid: int = -1
    min_ts: str = str(sys.maxsize)
    max_ts: str = "0"
    hcom_tids: list = None
    fp_ops: list = None
    bp_ops: list = None
    hcom_ops: list = None
    npu_ops_ts_dur: dict = None
    torch_to_npu_links: list = None

    def __post_init__(self):
        self.hcom_tids = self.hcom_tids or []
        self.fp_ops = self.fp_ops or []
        self.bp_ops = self.bp_ops or []
        self.hcom_ops = self.hcom_ops or []
        self.npu_ops_ts_dur = self.npu_ops_ts_dur or {}
        self.torch_to_npu_links = self.torch_to_npu_links or []

    def sort(self):
        self.fp_ops.sort(key=lambda x: x[Constant.TS])
        self.bp_ops.sort(key=lambda x: x[Constant.TS])
        self.hcom_ops.sort(key=lambda x: x[Constant.TS])
        self.torch_to_npu_links.sort(key=lambda x: x[Constant.TS])


class TraceViewPreProcessor:
    """
    Trace view data preprocess
    """

    @staticmethod
    def _is_fp_op(op_name: str) -> bool:
        """
        check whether op is fp op
        """
        return op_name.startswith(Constant.FP_ATEN_OP) or op_name.startswith(Constant.FP_C10D_OP)

    @staticmethod
    def _is_fp_data(data: dict, fp_tid: int, py_pid: int) -> bool:
        """
        check whether data is valid fp data
        """
        return data[Constant.OP_TID] == fp_tid and \
            Constant.TS in data and Constant.DUR in data and \
            not data[Constant.OP_NAME].startswith(Constant.STEP_PREFIX) and \
            data[Constant.PID] == py_pid

    @staticmethod
    def _is_bp_op(op_name: str) -> bool:
        """
        check whether op is bp op
        """
        return op_name.startswith(Constant.BP_AUTOGRAD_OP)

    @staticmethod
    def _is_bp_data(data: dict, bp_tid: int, py_pid: int) -> bool:
        """
        check whether data is valid bp data
        """
        return data[Constant.OP_TID] == bp_tid and \
            Constant.TS in data and Constant.DUR in data and \
            data[Constant.PID] == py_pid

    @staticmethod
    def _is_torch_to_npu_link(data: dict, fp_tid: int) -> bool:
        """
        check whether data is torch to npu link
        """
        return Constant.CAT in data and data[Constant.CAT] == Constant.ASYNC_NPU and \
            data[Constant.PH] == Constant.PH_START and \
            data[Constant.PID] == fp_tid

    @staticmethod
    def _is_send_recv_op(op_name: str) -> bool:
        """
        check whether op is hcom send or recv op
        """
        # for example, hcom_BatchSendRecv__101_0_1
        p1 = re.compile(r'^hcom_\w+SendRecv__\d+')
        # for example, hcom_send__101_0_1
        p2 = re.compile(r'hcom_send__\d+')
        # for example, hcom_receive__101_0_1
        p3 = re.compile(r'hcom_receive__\d+')
        return bool(p1.match(op_name)) or bool(p2.match(op_name)) or bool(p3.match(op_name))

    @staticmethod
    def _is_hcom_op(op_name: str) -> bool:
        """
        check whether data is hcom data
        """
        return op_name.startswith(Constant.HCOM_OP_PREFIX)

    @staticmethod
    def _is_python_process(data: dict) -> bool:
        """
        check whether data is python process
        """
        return Constant.PH in data and data[Constant.PH] == Constant.PH_META and \
            data[Constant.OP_NAME] == Constant.PROCESS_NAME and \
            data[Constant.ARGS][Constant.OP_NAME] == Constant.FRAMEWORK_NAME

    @staticmethod
    def _is_step_op(data: dict) -> bool:
        """
        check whether data is step data
        """
        return data[Constant.OP_NAME].startswith(Constant.STEP_PREFIX)

    @staticmethod
    def _is_ascend_process(data: dict) -> bool:
        """
        check whether data is ascend process data
        """
        return Constant.PH in data and data[Constant.PH] == Constant.PH_META and \
            data[Constant.OP_NAME] == Constant.PROCESS_NAME and \
            data[Constant.ARGS][Constant.OP_NAME] == Constant.ASCEND_HARDWARE_NAME

    @staticmethod
    def _is_npu_op(data: dict, ascend_pid: int) -> bool:
        """
        check whether data is npu op
        """
        return Constant.PH in data and data[Constant.PH] == Constant.PH_X and \
            not data[Constant.OP_NAME].isupper() and \
            data[Constant.PID] == ascend_pid

    def process(self, raw_data: list) -> Optional[FineTraceViewData]:
        """
        preprocess raw data
        """
        if not raw_data:
            logger.error("No raw data found in trace view data.")
            return None

        raw_fp_tids, raw_bp_tids, raw_hcom_tids = set(), set(), set()
        fine_data = FineTraceViewData()

        # counting fp ops and bp ops tid and ascend pid
        for data in raw_data:
            if self._is_fp_op(data[Constant.OP_NAME]):
                raw_fp_tids.add(data[Constant.OP_TID])
            elif self._is_bp_op(data[Constant.OP_NAME]):
                raw_bp_tids.add(data[Constant.OP_TID])
            elif self._is_send_recv_op(data[Constant.OP_NAME]):
                fine_data.hcom_ops.append(data)
                raw_hcom_tids.add(data[Constant.OP_TID])
            elif self._is_python_process(data):
                fine_data.py_pid = data[Constant.PID]
            elif self._is_ascend_process(data):
                fine_data.ascend_pid = data[Constant.PID]

            # find max and min ts in hcom ops
            if self._is_hcom_op(data[Constant.OP_NAME]):
                # for compatibility with old data (ts is float type)
                ts = data[Constant.TS] if not isinstance(data[Constant.TS], float) else str(data[Constant.TS])
                fine_data.min_ts = min(fine_data.min_ts, ts)
                fine_data.max_ts = max(fine_data.max_ts, ts)

        unique_fp_tid = list(raw_fp_tids - raw_bp_tids)
        unique_bp_tid = list(raw_bp_tids)
        fine_data.hcom_tids = list(raw_hcom_tids)

        if not unique_fp_tid or not unique_bp_tid:
            logger.info("No fp or bp tid found in trace view data.")
        else:
            fine_data.fp_tid, fine_data.bp_tid = unique_fp_tid[0], unique_bp_tid[0]

        # filter fp ops and bp ops and torch_to_npu_links
        for data in raw_data:
            if self._is_fp_data(data, fine_data.fp_tid, fine_data.py_pid):
                fine_data.fp_ops.append(data)
            elif self._is_bp_data(data, fine_data.bp_tid, fine_data.py_pid):
                fine_data.bp_ops.append(data)
            elif self._is_torch_to_npu_link(data, fine_data.fp_tid):
                fine_data.torch_to_npu_links.append(data)
            elif self._is_npu_op(data, fine_data.ascend_pid):
                fine_data.npu_ops_ts_dur[data[Constant.TS]] = data[Constant.DUR]

        fine_data.sort()
        return fine_data
