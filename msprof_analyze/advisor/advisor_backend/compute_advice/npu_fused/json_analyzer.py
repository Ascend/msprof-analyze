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

from msprof_analyze.prof_common.logger import get_logger

import pandas as pd

from msprof_analyze.advisor.advisor_backend.common_func_advisor.trace_view_json import TraceViewJson

logger = get_logger()


class JSONAnalyzer(object):
    def __init__(self, path):
        self._path = path

    def get_custom_code(self, data: pd.DataFrame, ts_col: str, output_col: str):
        trace_json = TraceViewJson(self._path)
        callstacks = pd.DataFrame(columns=[output_col])

        for i, row in data.iterrows():
            if ts_col not in data.columns.tolist():
                logger.error("No {} col found in data columns.".format(ts_col))
                return callstacks
            timestamp = row[ts_col]
            flow_event = trace_json.get_torch_2_npu_flow_event(timestamp)
            if not flow_event.valid():
                logger.error("Get flow event failed for pattern {}.".format(row['pattern']))
                callstacks.loc[i] = ""
                continue
            flow_event_s_key = flow_event.s_point_ts
            python_dur_events = trace_json.get_python_dur_events_contain_ts(flow_event_s_key)
            if not python_dur_events:
                logger.error("No python dur event found for pattern {}.".format(row['pattern']))
                callstacks.loc[i] = ""
                continue
            # 保持新老版本callstack兼容性
            if python_dur_events[0].args.get("Call stack"):
                # 旧版本
                callstack = python_dur_events[0].args.get("Call stack").split(";")
            else:
                python_dur_events.sort(key=lambda e: e.ts)
                # 新版本
                callstack = [event.name for event in python_dur_events if event.cat == "python_function"]
            callstack_str = "\n".join(callstack)
            callstacks.loc[i] = callstack_str
        return callstacks
