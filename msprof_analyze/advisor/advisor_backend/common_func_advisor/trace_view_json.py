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

from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field
from typing import Dict
from typing import List

import pandas as pd

from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


@dataclass
class TraceObj:
    ph: str = ""
    bp: str = ""
    cat: str = ""
    name: str = ""
    pid: int = 0
    tid: int = 0
    id: int = 0
    ts: str = ""
    dur: float = 0.0
    args: dict = field(default_factory=dict)

    @abstractmethod
    def hash(self):
        raise Exception("To be implemented")

    def valid(self):
        return self.name != ""

    def check_hashable(self):
        if not self.valid():
            raise Exception("Illegal {} to hash".format(self.__class__.name))


@dataclass
class Process(TraceObj):
    def hash(self):
        self.check_hashable()
        # msprof 保证name唯一性
        return self.args.get("name")


@dataclass
class Thread(TraceObj):
    def hash(self):
        self.check_hashable()
        # msprof 保证name唯一性
        return self.args.get("name")


@dataclass
class DurationEvent(TraceObj):
    def hash(self):
        self.check_hashable()
        return self.ts


@dataclass
class FlowEvent(TraceObj):
    s_point_ts: str = ""
    e_point_ts: str = ""

    def hash(self):
        self.check_hashable()
        return self.e_point_ts


class TraceViewJson:

    def __init__(self, path):
        self.processes: Dict[str, Process] = dict()
        self.threads: Dict[str, Thread] = dict()
        self.python_dur_events: Dict[str, DurationEvent] = dict()
        self.cann_dur_events: Dict[str, DurationEvent] = dict()
        self.ascend_hardware_dur_events: Dict[str, DurationEvent] = dict()
        self.torch_2_npu_flow_events: Dict[str, FlowEvent] = dict()
        traces = FileManager.read_json_file(path)
        self._load_obj(traces)

    def get_call_stack(self, data: pd.DataFrame, index_id: int, ts_col: str) -> str:
        if ts_col not in data.columns.tolist():
            logger.error("No %s col found in data columns.", str(ts_col))
            return ""
        row = data.loc[index_id]
        timestamp = row[ts_col]
        flow_event = self.get_torch_2_npu_flow_event(timestamp)
        if not flow_event.valid():
            logger.error("Get flow event failed for pattern %s.", str(row['pattern']))
            return ""
        flow_event_s_key = flow_event.s_point_ts
        python_dur_events = self.get_python_dur_events_contain_ts(flow_event_s_key)
        if not python_dur_events:
            logger.error("No python dur event found for pattern %s.", str(row['pattern']))
            return ""
        # 保持新老版本callstack兼容性
        if python_dur_events[0].args.get("Call stack"):
            # 旧版本
            call_stack_list = python_dur_events[0].args.get("Call stack").split(";")
        else:
            python_dur_events.sort(key=lambda e: e.ts)
            # 新版本
            call_stack_list = [event.name for event in python_dur_events if event.cat == "python_function"]
        call_stack = "\n".join(call_stack_list)
        return call_stack

    def get_torch_2_npu_flow_event(self, end_time) -> FlowEvent:
        if not self.torch_2_npu_flow_events or not self.torch_2_npu_flow_events.get(end_time):
            logger.error("Find flow event failed for ts: %s", str(end_time))
            return FlowEvent()
        return self.torch_2_npu_flow_events.get(end_time)

    def get_python_dur_events_contain_ts(self, ts) -> List[DurationEvent]:
        res = []
        for event in self.python_dur_events.values():
            if float(event.ts) <= float(ts) <= float(event.ts) + event.dur:
                res.append(event)
        return res

    def _load_obj(self, traces):
        self._load_format(traces)
        if not self._check_format():
            logger.error("parse json failed for error format")
            return
        self._load_duration_events(traces)
        self._load_torch_to_npu_flow_events(traces)

    def _check_format(self):
        # 当前功能只需要这两个process，可扩展
        check_processes = ['Python', 'Ascend Hardware']
        for check_process in check_processes:
            if check_process in self.processes:
                continue
            logger.error("%s process not found in json.", str(check_process))
            return False
        return True

    # 加载pid, tid头
    def _load_format(self, traces: List[Dict]):
        for _, trace in enumerate(traces):
            if trace.get('name') == 'process_name':
                if not trace.get('args') or not trace.get('args').get('name') or not trace.get('pid'):
                    continue
                process = Process(**trace)
                self.processes[process.hash()] = process
            if trace.get('name') == 'thread_name':
                if not trace.get('args') or not trace.get('args').get('name') or not trace.get('tid'):
                    continue
                thread = Thread(**trace)
                self.threads[thread.hash()] = thread

    def _load_duration_events(self, traces: List[Dict]):
        def check_events(_trace):
            return _trace.get('name') and _trace.get("ts") and _trace.get("dur")

        python_pid = self.processes.get("Python").pid
        cann_pid = self.processes.get("CANN").pid
        ascend_hardware_pid = self.processes.get("Ascend Hardware").pid
        for _, trace in enumerate(traces):
            if trace.get('ph') != 'X':
                continue
            if not check_events(trace):
                continue
            event = DurationEvent(**trace)
            if trace.get('pid') == python_pid:
                self.python_dur_events[event.hash()] = event
            elif trace.get('pid') == cann_pid:
                self.cann_dur_events[event.hash()] = event
            elif trace.get("pid") == ascend_hardware_pid:
                self.ascend_hardware_dur_events[event.hash()] = event

    def _load_torch_to_npu_flow_events(self, traces: List[Dict]):
        def check_events(_trace):
            return _trace.get('name') and _trace.get("id") and _trace.get("ts")

        flow_events_table_by_id = dict()

        python_pid = self.processes.get("Python")
        for _, trace in enumerate(traces):
            if trace.get('ph') != 's' and trace.get('ph') != 'f' and trace.get('pid') != python_pid:
                continue
            if not check_events(trace):
                continue
            event = flow_events_table_by_id.get(trace.get("id"))
            if not event:
                event = FlowEvent(**trace)
            if trace.get('ph') == 's':
                event.s_point_ts = trace.get('ts')
            else:
                event.e_point_ts = trace.get('ts')
            flow_events_table_by_id[event.id] = event

        self.torch_2_npu_flow_events = {eve.hash(): eve for eve in flow_events_table_by_id.values()}
