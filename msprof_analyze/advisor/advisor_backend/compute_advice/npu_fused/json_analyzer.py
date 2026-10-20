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

import pandas as pd

from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.advisor.advisor_backend.common_func_advisor.trace_view_json import TraceViewJson

logger = get_logger()


class JSONAnalyzer:
    def __init__(self, path):
        self._path = path

    def get_custom_code(self, data: pd.DataFrame, ts_col: str, output_col: str):
        trace_json = TraceViewJson(self._path)
        callstacks = pd.DataFrame(columns=[output_col])

        for i, row in data.iterrows():
            if ts_col not in data.columns.tolist():
                logger.error("No %s col found in data columns.", ts_col)
                return callstacks
            timestamp = row[ts_col]
            flow_event = trace_json.get_torch_2_npu_flow_event(timestamp)
            if not flow_event.valid():
                logger.error("Get flow event failed for pattern %s.", row['pattern'])
                callstacks.loc[i] = ""
                continue
            flow_event_s_key = flow_event.s_point_ts
            python_dur_events = trace_json.get_python_dur_events_contain_ts(flow_event_s_key)
            if not python_dur_events:
                logger.error("No python dur event found for pattern %s.", row['pattern'])
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
