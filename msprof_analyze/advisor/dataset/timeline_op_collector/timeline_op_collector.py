# Copyright (C) 2024-2024. Huawei Technologies Co., Ltd. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
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
import math
import os
from abc import abstractmethod, ABCMeta

from msprof_analyze.advisor.dataset.timeline_op_collector.timeline_op_sql import TimelineEventType, TimelineDBHelper
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from msprof_analyze.advisor.utils.utils import convert_to_float
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class BaseOpCollector(metaclass=ABCMeta):

    def __init__(self):
        self.attribute_to_dataset = {}
        self.op_list = []
        self.require_filter_by_step = True
        self.framework_table = ""
        self.related_table_list = []
        self.event_type = []


    @abstractmethod
    def add_op(self, event):
        """ add timeline event into self.op_list, and then will filter event in self.op_list by specific step
        """
        pass

    @abstractmethod
    def post_process(self, target_op_list, **kwargs):
        """ convert self.op_list to required format like dict, set and so on and then record the final object into
            self.attribute_to_dataset which used to set property of timeline event dataset
        """
        pass

    def add_op_from_db(self, df):
        logger.debug("Skip add_op_from_db for collector %s", self.__class__.__name__)
        return

    def get_event_type(self):
        return self.event_type



class StepCollector(BaseOpCollector):
    KEY_WORD = "ProfilerStep"

    def __init__(self):
        super().__init__()
        self.require_filter_by_step = False
        self.event_type = [TimelineEventType.FRAMEWORK_API]

    def add_op(self, event):
        if event.name.startswith(self.KEY_WORD):
            self.op_list.append(event)

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        filtered_df = df[df['name'].str.startswith(self.KEY_WORD, na=False)]
        self.op_list = [TimelineEvent(record) for record in filtered_df.to_dict('records')]

    def post_process(self, *args, **kwargs):
        self.attribute_to_dataset["profiler_step"] = self.op_list



class OpCompileCollector(BaseOpCollector):

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.CANN_API]
        self._total_op_compile_counter = 0
        self._total_op_compile_time = 0.0

    @property
    def total_time(self):
        return self._total_op_compile_time

    @property
    def total_count(self):
        return self._total_op_compile_counter

    def is_empty(self):
        return self._total_op_compile_counter == 0

    def update(self, event: TimelineEvent):
        self._total_op_compile_time += float(event.dur)
        self._total_op_compile_counter += 1

    def unset(self):
        self._total_op_compile_counter = 0
        self._total_op_compile_time = 0.0

    def add_op(self, event):
        if event.name == Constant.OP_COMPILE_NAME or event.args.get("id") == Constant.OP_COMPILE_ID:
            self.op_list.append(event)

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        filtered_df = df[df['name'] == Constant.OP_COMPILE_NAME]
        self.op_list = [TimelineEvent(record) for record in filtered_df.to_dict('records')]

    def post_process(self, target_op_list, **kwargs):
        for op in target_op_list:
            self.update(op)

        self.attribute_to_dataset["ops_compile"] = self



class SynchronizeStreamCollector(BaseOpCollector):

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.CANN_API]
        self.require_filter_by_step = False

    def add_op(self, event):
        if event.name.startswith(Constant.SYNC_STREAM) or event.name.startswith(Constant.NODE_LAUNCH):
            self.op_list.append(event)

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        filtered_df = df[
            df['name'].str.startswith(Constant.SYNC_STREAM) |
            df['name'].str.startswith(Constant.NODE_LAUNCH)
            ]
        self.op_list = [TimelineEvent(record) for record in filtered_df.to_dict('records')]

    def post_process(self, *args, **kwargs):
        self.op_list.sort(key=lambda x: x.ts)

        self.attribute_to_dataset["synchronize_stream"] = self.op_list



class MemCollector(BaseOpCollector):
    MEMORY_OP_NAME = ["AscendCL@aclMallocMemInner", "AscendCL@aclrtFreePhysical", "AscendCL@aclrtFree"]

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.CANN_API]
        self.mem_op_info = {}
        self.rule = self._load_rule()

    @staticmethod
    def _load_rule():
        language = AdditionalArgsManager().language
        memory_rule_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
                                        "rules",
                                        language,
                                        "memory.yaml")

        memory_rule = FileManager.read_yaml_file(memory_rule_path)
        return memory_rule

    def add_op(self, event):
        if event.name not in self.MEMORY_OP_NAME:
            return
        self.op_list.append(event)

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        filtered_df = df[df['name'].isin(self.MEMORY_OP_NAME)]
        self.op_list = [TimelineEvent(record) for record in filtered_df.to_dict('records')]

    def post_process(self, target_op_list, **kwargs):
        for op in target_op_list:
            if op.name not in self.mem_op_info:
                self.mem_op_info[op.name] = dict(count=0, total_dur=0)
            self.mem_op_info[op.name]["count"] += 1
            self.mem_op_info[op.name]["total_dur"] += float(op.dur)

        self.attribute_to_dataset["memory_ops"] = self



class DataloaderCollector(BaseOpCollector):
    KEY_WORD = "dataloader"

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.FRAMEWORK_API]

    def add_op(self, event):
        if self.KEY_WORD in event.name.lower():
            self.op_list.append(TimelineEvent({
                "name": event.name, "dataset_index": event.dataset_index, "ts": event.ts, "dur": event.dur,
                "stack": event.args.get("Call stack")
            }))

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        filtered_df = df[df['name'].str.contains(self.KEY_WORD, case=False)]
        self.op_list = [TimelineEvent(record) for record in filtered_df.to_dict('records')]


    def post_process(self, *args, **kwargs):
        self.attribute_to_dataset["dataloader"] = self.op_list



class SyncBNCollector(BaseOpCollector):
    KEY_WORD = "syncbatchnorm"

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.FRAMEWORK_API]

    def add_op(self, event):
        if event.name.lower() == self.KEY_WORD:
            self.op_list.append(TimelineEvent({
                "name": event.name, "dataset_index": event.dataset_index, "ts": event.ts, "dur": event.dur
            }))

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        filtered_df = df[df['name'].astype(str).str.lower() == self.KEY_WORD]
        self.op_list = [TimelineEvent(record) for record in filtered_df.to_dict('records')]

    def post_process(self, target_op_list, **kwargs):
        self.attribute_to_dataset["sync_batchnorm"] = target_op_list



class AtenCollector(BaseOpCollector):

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.FRAMEWORK_API, TimelineEventType.CANN_API]

    def add_op(self, event):
        if event.name.lower().startswith(f"{Constant.ATEN}{Constant.ATEN_SEP}") or event.name.lower().startswith(
                f"{Constant.NPU_LOWER}{Constant.ATEN_SEP}") or event.name.startswith(Constant.SYNC_STREAM):
            self._add_aten(event)
            return

        # 检查cann层同步操作，根据时间窗口索引到host侧的aten算子并给出堆栈
        if event.name.startswith(Constant.SYNC_STREAM):
            self._add_aten(event)

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        name_series = df['name'].astype(str)

        # 条件1：name 以 aten:: 开头（不区分大小写）
        aten_prefix = f"{Constant.ATEN}{Constant.ATEN_SEP}"
        aten_condition = name_series.str.lower().str.startswith(aten_prefix)
        # 条件2：name 以 npu:: 开头（不区分大小写）
        npu_prefix = f"{Constant.NPU_LOWER}{Constant.ATEN_SEP}"
        npu_condition = name_series.str.lower().str.startswith(npu_prefix)
        # 条件3：name 以 SYNC_STREAM 开头（区分大小写）
        sync_condition = name_series.str.startswith(Constant.SYNC_STREAM)
        # 组合条件
        filtered_df = df[aten_condition | npu_condition | sync_condition]

        self.op_list.extend(
            TimelineEvent(record)
            for record in filtered_df.to_dict('records')
        )

    def post_process(self, target_op_list, **kwargs):
        self.attribute_to_dataset["aten"] = target_op_list

    def _add_aten(self, event: TimelineEvent):
        self.op_list.append(TimelineEvent({
            "name": event.name, "dataset_index": event.dataset_index, "ts": event.ts, "dur": event.dur
        }))


class OptimizerCollector(BaseOpCollector):
    KEY_WORD = f"{Constant.OPTIMIZER}.{Constant.OPTIMIZER_STEP}{Constant.OPTIMIZER_SEP}"

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.FRAMEWORK_API]

    def add_op(self, event):
        if event.name.startswith(self.KEY_WORD):
            self.op_list.append(TimelineEvent(
                {"name": event.name, "dataset_index": event.dataset_index, "ts": event.ts, "dur": event.dur}))

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        filtered_df = df[df['name'].str.startswith(self.KEY_WORD, na=False)]
        self.op_list = [TimelineEvent(record) for record in filtered_df.to_dict('records')]

    def post_process(self, target_op_list, **kwargs):
        self.attribute_to_dataset["optimizer"] = target_op_list




class FrequencyCollector(BaseOpCollector):
    KEY_WORD = "AI Core Freq"

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.AICORE_FREQ]
        self._previous_freq_index = -1

    @staticmethod
    def get_op_frequency(ai_core_ops, ai_core_freq):
        ai_core_freq.sort(key=lambda x: float(x.ts))
        op_freq_record = {}

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
                    if op_event.name not in op_freq_record:
                        op_freq_record[op_event.name] = {"count": 0, "dur": 0, "freq_list": []}
                    op_freq_record[op_event.name]["count"] += 1
                    op_freq_record[op_event.name]["dur"] += convert_to_float(op_event.dur)
                    op_freq_list.append(convert_to_float(freq_event.args.MHz))
                    op_freq_record[op_event.name]["freq_list"].append(min(op_freq_list))
                    break
                else:
                    break

            op_index += 1
        return op_freq_record

    def add_op(self, event):
        if event.name == self.KEY_WORD:
            if self._previous_freq_index != -1:
                self.op_list[self._previous_freq_index]["end"] = event.get("ts", float(math.inf))
            self._previous_freq_index += 1
            event.setdefault("end", float(math.inf))
            self.op_list.append(event)

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        df.fillna(math.inf, inplace=True)
        self.op_list = [TimelineEvent(record) for record in df.to_dict('records')]

    def post_process(self, target_op_list, **kwargs):
        ai_core_ops = kwargs.get("ai_core_ops", [])
        if not ai_core_ops:
            return
        ai_core_ops.sort(key=lambda x: float(x.ts))
        op_freq = FrequencyCollector.get_op_frequency(ai_core_ops, target_op_list)
        self.attribute_to_dataset["op_freq"] = op_freq




class SpecificTaskTypeOpCollector(BaseOpCollector):

    def __init__(self, op_type_list=None):
        super().__init__()
        self.op_type_list = op_type_list if op_type_list else [Constant.AI_CPU, Constant.AI_CORE, Constant.MIX_AIC]

    def add_op(self, event):
        if event.args.get(Constant.TASK_TYPE) and event.args.get(Constant.TASK_TYPE) in self.op_type_list:
            self.op_list.append(
                TimelineEvent(
                    {
                        Constant.TASK_TYPE: event.args.get(Constant.TASK_TYPE),
                        "task_id": event.args.get("Task Id"),
                        "tid": event.tid,
                        "name": event.name,
                        "ts": str(event.ts),
                        "dur": str(event.dur)
                    }
                )
            )

    def post_process(self, target_op_list, **kwargs):
        op_map = dict()
        for op in target_op_list:
            key = f"{op.name}-{op.ts}"
            op_map[key] = op

        self.attribute_to_dataset["ops_with_task_type"] = op_map
        self.attribute_to_dataset["task_op_names"] = list(
            set([event_key.split("-")[0] for event_key in op_map.keys()]))


class TorchToNpuCollector(BaseOpCollector):
    def __init__(self):
        super().__init__()

    def add_op(self, event):
        if event.name.lower() == Constant.TORCH_TO_NPU:
            self.op_list.append(TimelineEvent({"tid": event.tid, "ts": str(event.ts), "ph": event.ph, "id": event.id}))

    def post_process(self, target_op_list, **kwargs):
        op_map = dict()
        for op in target_op_list:
            key = f"{op.ph}-{op.id}"
            op_map[key] = op

        self.attribute_to_dataset["torch_to_npu"] = op_map


class AclToNpuCollector(BaseOpCollector):
    def __init__(self):
        super().__init__()

    def add_op(self, event):
        if event.name and event.ts and event.name == Constant.ACL_TO_NPU:
            self.op_list.append(TimelineEvent({"ts": event.ts}))

    def post_process(self, target_op_list, **kwargs):
        op_record = set(str(op.ts) for op in target_op_list)
        self.attribute_to_dataset["acl_to_npu"] = op_record


class OpStackCollector(BaseOpCollector):

    def __init__(self):
        super().__init__()

    def add_op(self, event):
        if event.args.get(Constant.CALL_STACKS):
            self.op_list.append(
                TimelineEvent({"name": event.name, "dataset_index": event.dataset_index, "ts": event.ts}))

    def post_process(self, target_op_list, **kwargs):
        op_map = dict()
        for op in target_op_list:
            op_map[str(op.ts)] = op

        self.attribute_to_dataset["ops_with_stack"] = op_map


class GcCollector(BaseOpCollector):

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.GC_RECORD]

    def add_op(self, event):
        if event.cat and isinstance(event.cat, str) and event.cat.lower() == "gc":
            self.op_list.append(TimelineEvent(
                {"name": event.name, "dataset_index": event.dataset_index, "ts": event.ts, "dur": event.dur}))

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        self.op_list = [TimelineEvent(record) for record in df.to_dict('records')]

    def post_process(self, target_op_list, **kwargs):
        self.attribute_to_dataset["gc_events"] = self.op_list


class FreeEventsCollector(BaseOpCollector):

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.OVERLAP_ANALYSIS]

    @staticmethod
    def _load_rule():
        language = AdditionalArgsManager().language
        sync_stream_rule_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
            "rules",
            language,
            "conjectured_gc.yaml")

        gc_rule = FileManager.read_yaml_file(sync_stream_rule_path)
        return gc_rule

    def add_op(self, event):
        if event.name.lower() == Constant.FREE:
            self.op_list.append(event)

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        df = df.sort_values('startNs').reset_index(drop=True)
        # 计算空闲时间
        prev_end = df.iloc[0]['endNs']  # 第一个事件的开始时间作为基准
        for i in range(1, len(df)):
            current_start = df.iloc[i]['startNs']
            idle_dur = current_start - prev_end
            if idle_dur > 0.0:
                self.op_list.append(TimelineEvent({'name': Constant.FREE, 'ts': prev_end / 1000.0,
                                                   'dur': idle_dur / 1000.0}))
            prev_end = max(prev_end, df.iloc[i]['endNs'])

    def post_process(self, target_op_list, **kwargs):
        gc_rule = self._load_rule()
        if os.getenv(Constant.FREE_DURATION_FOR_GC_ANALYSIS):
            max_free_threshold = convert_to_float(os.getenv(Constant.FREE_DURATION_FOR_GC_ANALYSIS))
        else:
            max_free_threshold = gc_rule.get("max_free_threshold")

        large_free_events = []

        for op in target_op_list:
            if convert_to_float(op.dur) > max_free_threshold:
                large_free_events.append(op)

        large_free_events.sort(key=lambda x: convert_to_float(x.ts))
        self.attribute_to_dataset["large_free_events"] = large_free_events



class AclEventsCollector(BaseOpCollector):
    ACL_EVENT_PREFIX = "AscendCL@"

    def __init__(self):
        super().__init__()
        self.event_type = [TimelineEventType.CANN_API]

    def add_op(self, event):
        if event.name.startswith(self.ACL_EVENT_PREFIX):
            self.op_list.append(event)

    def add_op_from_db(self, df):
        if df is None or df.empty:
            return
        filtered_df = df[df['name'].str.startswith(self.ACL_EVENT_PREFIX, na=False)]
        self.op_list = [TimelineEvent(record) for record in filtered_df.to_dict('records')]

    def post_process(self, target_op_list, **kwargs):
        target_op_list.sort(key=lambda x: convert_to_float(x.ts))
        self.attribute_to_dataset["acl_events"] = target_op_list
