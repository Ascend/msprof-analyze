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

"""
profiling info
"""
import decimal
from msprof_analyze.prof_common.logger import get_logger
from typing import List
from msprof_analyze.advisor.utils.utils import lazy_property

logger = get_logger()


class Info:
    """
    op info
    """
    _attr_pre_fix_list = [""]
    FFTS_TYPE = "ffts_type"

    def add_attr(self, key: str, value: str):
        """
        add attr to op info
        :param key: op info key
        :param value: op info value
        :return: None
        """
        if not key or hasattr(self, key):
            return
        setattr(self, key, value)

    def has_attr(self, key: str, strict_mode=False):
        """
        check if op info has attr key
        :param key: attr key
        :return: true or false
        """
        if strict_mode:
            return hasattr(self, key)
        for prefix in self._attr_pre_fix_list:
            attr = prefix + key
            if hasattr(self, attr):
                return True
        return False

    def get_attr(self, key, strict_mode=False):
        """
        get attr value by key
        :param key: attr key
        :return: attr value
        """
        if strict_mode:
            if hasattr(self, key):
                return getattr(self, key)
        else:
            for prefix in self._attr_pre_fix_list:
                attr = prefix + key
                if key.startswith("mac") and prefix == "aiv_":
                    # e.g mac_ratio must match aic_mac_ratio, not aiv_mac_ratio
                    continue
                if key.startswith("vec") and prefix == "aic_":
                    # e.g vec_ratio must match aiv_vec_ratio, not aic_vec_ratio
                    continue
                if hasattr(self, attr):
                    return getattr(self, attr)
        return ""

    def get_float_attr(self, attr, strict_mode=False):
        """
        get attr value by key
        :param key: attr key
        :return: attr value
        """
        try:
            return float((self.get_attr(attr, strict_mode)))
        except (ValueError, FloatingPointError):
            pass
        return 0

    def get_decimal_attr(self, attr, strict_mode=False):
        """
        get attr value by key
        :param key: attr key
        :return: attr value
        """
        try:
            return decimal.Decimal((self.get_attr(attr, strict_mode)))
        except (ValueError, decimal.InvalidOperation):
            pass
        return decimal.Decimal(0)

    def get_attrs(self) -> dict:
        """
        get attr list
        :return: attr list
        """
        return self.__dict__


class OpInfo(Info):
    """
    summary info
    """

    _attr_pre_fix_list = ["", "aic_", "aiv_"]
    _mac_ratio_attrs = ["mac_ratio", "mac_fp16_ratio", "mac_int8_ratio", "aic_mac_ratio"]
    _aicore_time_key = ["aicore_time", "aiv_time"]
    _total_cycles_key = ["total_cycles", "aic_total_cycles", "aiv_total_cycles"]

    def __lt__(self, other):
        return self.get_float_attr("task_start_time") < other.get_float_attr("task_start_time")

    @lazy_property
    def is_cube_op(self) -> bool:
        """
        check type of operator if cube or not
        """
        for attr in self._mac_ratio_attrs:
            if hasattr(self, attr):
                try:
                    if float(getattr(self, attr)) > 0:
                        if hasattr(self, self.FFTS_TYPE) and getattr(self, self.FFTS_TYPE) == "1":
                            logger.warning(
                                "ffts type of op %s is vector buf mac ratio is not 0", getattr(self, "op_name")
                            )
                        return True
                except ValueError:
                    pass
        # not cube op
        if hasattr(self, self.FFTS_TYPE) and getattr(self, self.FFTS_TYPE) == "0":
            logger.warning("ffts type of op %s is cube but mac ratio is 0", getattr(self, "op_name"))
        return False

    @lazy_property
    def has_mac_ratio(self) -> bool:
        """
        check if op_info has mac ratio
        """
        for attr in self._mac_ratio_attrs:
            if attr in self.__dict__:
                return True
        return False

    def attr_sum(self, attr_list):
        """sum of a list attrs"""
        total = 0
        for attr in attr_list:
            total += self.get_float_attr(attr, strict_mode=True)
        return total

    def get_aicore_time(self):
        """
        get sum of aicore time and ai vector core time
        """
        return self.attr_sum(self._aicore_time_key)

    def get_total_cycles(self):
        """
        get sum of total cycle for aicore and ai vector core
        """
        return self.attr_sum(self._total_cycles_key)


class TaskInfo:
    """
    task info
    """
    EVENT_TYPE = {"metadata": ['M'], "duration": ['B', 'E'], "complete": ['X'], 'flow': ['s', 't', 'f']}

    def __init__(self, content: dict) -> None:
        self._name = content.get("name", "")
        self._pid = content.get("pid", 0)
        self._tid = content.get("tid", 0)
        self._start_time = float(content.get("ts", 0.0))
        self._dur = float(content.get("dur", 0.0))
        self._args = content.get("args", {})
        self._cat = content.get("cat", "")
        self._id = content.get("id", "")

    @property
    def pk_id(self):
        """
        get id
        :return: id
        """
        return self._id

    @property
    def pid(self):
        """
        get pid
        :return: pid
        """
        return self._pid

    @property
    def tid(self):
        """
        get tid
        :return: tid
        """
        return self._tid

    @property
    def task_type(self):
        """
        get pid
        :return: pid
        """
        return self._args.get("task type", "NA")

    @property
    def start_time(self):
        """
        get starttime
        :return: starttime
        """
        return self._start_time

    @property
    def end_time(self):
        """
        get endtime
        :return: endtime
        """
        return self._start_time + self._dur

    @property
    def dur(self):
        """
        get duration
        :return: duration
        """
        return self._dur

    @property
    def name(self):
        """
        get task name
        :return: task name
        """
        return self._name

    @property
    def stream_id(self):
        """
        get stream_id
        :return: steram id
        """
        return self._args.get("stream id", "NA")

    @property
    def task_id(self):
        """
        get task id
        :return: task_id
        """
        return self._args.get("task id", "NA")

    @property
    def transport_type(self):
        """
        get transport type
        :return: transport_type
        """
        return self._args.get("transport type", "NA")

    @property
    def link_type(self):
        """
        get link type
        :return: link_type
        """
        return self._args.get("link type", "NA")

    @property
    def args(self):
        """
        get args of task
        :return: args
        """
        return self._args

    @property
    def cat(self):
        """
        get category of task
        """
        return self._cat


class HcclOp:
    MIN_SIZE = 512

    def __init__(self, task: TaskInfo):
        self.op_name = task.name
        self.start = task.start_time
        self.end = task.end_time
        self.sdma_size = 0
        self.sdma_duration = 0
        self.rdma_size = 0
        self.rdma_duration = 0
        self.reduce_inline_tasks: List[HcclTask] = []
        self.memcpy_tasks: List[HcclTask] = []


class HcclTask:
    def __init__(self, task: TaskInfo):
        self._start = task.start_time
        self._end = task.end_time
        self._duration = task.dur
        self._size = task.args.get("size(Byte)", 0)
        self._transport_type = task.transport_type
        self._link_type = task.link_type

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._end

    @property
    def duration(self):
        return self._duration

    @property
    def size(self):
        return self._size

    @property
    def transport_type(self):
        return self._transport_type

    @property
    def link_type(self):
        return self._link_type
