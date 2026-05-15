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

import json
from msprof_analyze.prof_common.logger import get_logger
import math

from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from msprof_analyze.advisor.utils.utils import get_file_path_from_directory
from msprof_analyze.advisor.utils.utils import convert_to_float, parse_json_with_generator
from msprof_analyze.advisor.dataset.profiling.device_info import DeviceInfoParser
from msprof_analyze.advisor.config.config import Config

logger = get_logger()


class AICoreFreqDataset:

    def __init__(self, collection_path, data: dict, build_dataset=True, **kwargs) -> None:

        self._profiler_step = []
        self._ai_core_ops = []
        self._ai_core_freq: [TimelineEvent] = []
        self._previous_freq_index = -1

        self.timeline_dir = collection_path
        self.timeline_data_list = get_file_path_from_directory(collection_path,
                                                               lambda file: file.endswith("trace_view.json"))

        self.step = kwargs.get("step")
        self.op_freq = {}
        info = DeviceInfoParser(collection_path)
        info.parse_data()
        if not Config().get_config("aic_frequency"):
            return
        if self.parse():
            key = self.get_key()
            if key not in data:
                data[key] = []
            data[key].append(self)

    @property
    def profiler_step(self):
        return self._profiler_step

    @property
    def ai_core_freq(self):
        return self._ai_core_freq

    @property
    def ai_core_ops(self):
        return self._ai_core_ops

    @classmethod
    def get_key(cls):
        """
        get key of dataset
        :return: key
        """
        return cls.__module__.rsplit('.', maxsplit=1)[-1]

    def parse(self):

        if len(self.timeline_data_list) == 0:
            logger.warning("Please ensure trace_view.json in %s, skip timeline analysis.", self.timeline_dir)
            return False

        if len(self.timeline_data_list) > 1:
            logger.warning("Found multiple trace_view.json in %s, load the file of device 0 for analysis.",
                           self.timeline_dir)

        _ = parse_json_with_generator(sorted(self.timeline_data_list)[0], self._add_event)

        target_ai_core_ops = self._get_target_ai_core_ops()
        self._get_op_frequency(target_ai_core_ops)
        return True

    def _add_profiler_step(self, event):
        if event.name.startswith("ProfilerStep"):
            self._profiler_step.append(event)

    def _add_ai_core_ops(self, event):
        if event.args.get("Task Type") in ["MIX_AIC", "AI_CORE"]:
            self._ai_core_ops.append(event)

    def _add_ai_core_freq(self, event):
        if event.name == "AI Core Freq":
            if self._previous_freq_index != -1:
                self._ai_core_freq[self._previous_freq_index]["end"] = event.get("ts", float(math.inf))
            self._previous_freq_index += 1
            event.setdefault("end", float(math.inf))
            self._ai_core_freq.append(event)

    def _add_event(self, index, event):
        event["dataset_index"] = index
        if not isinstance(event, TimelineEvent):
            event = TimelineEvent(event)

        self._add_profiler_step(event)
        self._add_ai_core_ops(event)
        self._add_ai_core_freq(event)

        return True

    def _get_target_ai_core_ops(self):
        target_ai_core_ops = []
        if not self.step or f"ProfilerStep#{self.step}" not in [event.name for event in self._profiler_step]:
            target_ai_core_ops = self._ai_core_ops
        else:
            for step_event in self._profiler_step:
                if step_event.name != f"ProfilerStep#{self.step}":
                    continue

                for ai_core_op_event in self._ai_core_ops:
                    if step_event.ts_include(ai_core_op_event):
                        target_ai_core_ops.append(ai_core_op_event)
        target_ai_core_ops = sorted(target_ai_core_ops, key=lambda x: float(x.ts))
        return target_ai_core_ops

    def _get_op_frequency(self, ai_core_ops):
        ai_core_freq = sorted(self._ai_core_freq, key=lambda x: float(x.ts))

        op_index, freq_index = 0, 0
        while op_index < len(ai_core_ops) and freq_index < len(ai_core_freq):
            op_event = ai_core_ops[op_index]
            op_end_time = convert_to_float(op_event.ts) + convert_to_float(op_event.dur)
            op_freq_list = []
            while freq_index < len(ai_core_freq):
                freq_event = ai_core_freq[freq_index]
                if convert_to_float(freq_event.end) < op_end_time:
                    op_freq_list.append(convert_to_float(freq_event.args.MHz))
                    freq_index += 1
                    continue
                elif convert_to_float(freq_event.ts) < op_end_time:
                    if op_event.name not in self.op_freq:
                        self.op_freq[op_event.name] = {"count": 0, "dur": 0, "freq_list": []}
                    self.op_freq[op_event.name]["count"] += 1
                    self.op_freq[op_event.name]["dur"] += convert_to_float(op_event.dur)
                    op_freq_list.append(convert_to_float(freq_event.args.MHz))
                    self.op_freq[op_event.name]["freq_list"].append(min(op_freq_list))
                    break
                else:
                    break

            op_index += 1
