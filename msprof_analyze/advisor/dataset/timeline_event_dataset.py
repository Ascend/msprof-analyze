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
import re
import traceback
from collections import OrderedDict
from tqdm import tqdm
import ijson

from msprof_analyze.advisor.dataset.timeline_op_collector.timeline_op_sql import TimelineDBHelper
from msprof_analyze.advisor.dataset.dataset import Dataset

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.timeline.event import TimelineEvent
from msprof_analyze.advisor.utils.utils import get_file_path_from_directory, check_path_valid, singleton, \
    convert_to_float
from msprof_analyze.advisor.dataset.timeline_op_collector.timeline_op_collector import (
    OpCompileCollector,
    SynchronizeStreamCollector,
    MemCollector,
    DataloaderCollector,
    SyncBNCollector,
    AtenCollector,
    OptimizerCollector,
    FrequencyCollector,
    SpecificTaskTypeOpCollector,
    TorchToNpuCollector,
    AclToNpuCollector,
    OpStackCollector,
    StepCollector,
    GcCollector,
    FreeEventsCollector,
    AclEventsCollector
)

logger = get_logger()


class BaseTimelineEventDataset(Dataset):
    PROFILER_STEP_PREFIX = "ProfilerStep"
    collector_map = {}
    TRACE_VIEW_PATTERN = re.compile(r'trace_view\.json$')

    def __init__(self, collection_path, data: dict, build_dataset=True, **kwargs) -> None:
        super().__init__(collection_path, data, **kwargs)
        self.collection_path = collection_path
        self.profiler_step = []
        self.timeline_file = ""
        self.dataset_len = None
        self.step = kwargs.get("step")
        self.step_duration = kwargs.get("step_duration", 0.0)
        self.data_type = self.get_data_type()

        if not build_dataset or not self.get_timeline_file_list():
            return
        if self.parse():
            key = self.get_key()
            if key not in data:
                data[key] = []
            data[key].append(self)

    @classmethod
    def get_key(cls):
        """
        get key of dataset
        :return: key
        """
        return cls.__module__.rsplit('.', maxsplit=1)[-1]

    def get_post_process_kwargs(self, func_name):
        kwargs = {}
        if func_name == FrequencyCollector.__name__:
            ops_with_task_type = getattr(self, "ops_with_task_type", {}).values()
            kwargs["ai_core_ops"] = [op
                                     for op in ops_with_task_type if
                                     op.get(Constant.TASK_TYPE) in [Constant.AI_CORE, Constant.MIX_AIC]
                                     ]
        return kwargs

    def add_event(self, index, event):
        event["dataset_index"] = index
        if not isinstance(event, TimelineEvent):
            event = TimelineEvent(event)

        for _, collector in self.collector_map.items():
            collector.add_op(event)
        return True

    def parse(self):
        return self.parse_from_db() if self.data_type == Constant.DB else self.parse_from_text()

    def get_timeline_file_list(self):
        if self.data_type == Constant.TEXT:
            timeline_file_list = get_file_path_from_directory(
                self.collection_path,
                lambda file: self.TRACE_VIEW_PATTERN.match(file)
            )
        elif self.data_type == Constant.DB:
            # 尝试匹配 PyTorch 和 MindSpore 两种 DB 文件
            pytorch_files = get_file_path_from_directory(
                self.collection_path,
                lambda file: self.PYTORCH_DB_PATTERN.match(file)
            )
            mindspore_files = get_file_path_from_directory(
                self.collection_path,
                lambda file: self.MINDSPORE_DB_PATTERN.match(file)
            )
            if pytorch_files and mindspore_files:
                logger.error("Both PyTorch and MindSpore DB files found, ambiguous!")
                return False
            elif pytorch_files:
                timeline_file_list = pytorch_files
            elif mindspore_files:
                timeline_file_list = mindspore_files
            else:
                logger.error("No valid PyTorch/MindSpore DB files found!")
                return False
        else:
            logger.error("Invalid data_type: %s", self.data_type)
            return False

        if len(timeline_file_list) == 0:
            logger.warning(f"Please ensure timeline file in {self.collection_path}, skip timeline analysis.")
            return False
        if len(timeline_file_list) > 1:
            logger.warning(f"Found multiple timeline files in {self.collection_path}, "
                           f"load the file of device 0 for analysis.")
        self.timeline_file = sorted(timeline_file_list)[0]
        return True

    def parse_from_text(self):
        result = self.parse_data_with_generator(self.add_event)
        if not self.dataset_len:
            self.dataset_len = len(result)
        return True

    def parse_from_db(self):
        db_helper = None
        try:
            db_helper = TimelineDBHelper(self.timeline_file)
            if not db_helper.init_timeline_db_helper():
                return False
            for _, collector in tqdm(self.collector_map.items(), leave=False,
                                    desc="Building dataset for timeline analysis"):
                for event_type in collector.get_event_type():
                    df = db_helper.query_timeline_event(event_type)
                    collector.add_op_from_db(df)
        except Exception:
            logger.warning("Error %s while parsing from db, file %s", traceback.format_exc(),
                           self.timeline_file)
            return False
        finally:
            if db_helper:
                db_helper.destroy_db_connection()
        return True

    def parse_data_with_generator(self, func):
        result = []
        if not check_path_valid(self.timeline_file) or self.data_type == Constant.DB:
            return result

        try:
            with open(self.timeline_file, "r") as f:
                for i, event in tqdm(enumerate(ijson.items(f, "item")),
                                     leave=False, ncols=100, desc="Building dataset for timeline analysis",
                                     total=self.dataset_len):
                    func_res = func(index=i, event=event)
                    if func_res is not None:
                        result.append(func_res)

        except Exception:
            logger.warning("Error %s while parsing file %s, continue to timeline analysis", traceback.format_exc(),
                           self.timeline_file)
        return result

    def _get_target_ops_by_step(self, op_list):
        target_ops = []
        if not self.profiler_step:
            return op_list
        if not self.step or f"ProfilerStep#{self.step}" not in [event.name for event in self.profiler_step]:
            target_ops = op_list
            if self.profiler_step:
                self.step_duration = convert_to_float(self.profiler_step[-1].dur)
        else:
            for step_event in self.profiler_step:
                if step_event.name != f"ProfilerStep#{self.step}":
                    continue
                self.step_duration = convert_to_float(step_event.dur)
                for op_event in op_list:
                    if step_event.ts_include(op_event):
                        target_ops.append(op_event)
        target_ops.sort(key=lambda x: convert_to_float(x.ts))
        return target_ops

    def _collector_post_process(self):
        # 按step过滤collector中的算子，并将过滤后的算子设置为当前dataset的property，与原始TimelineEventDataset的property保持一致
        for collector_name, collector in self.collector_map.items():
            logger.debug("Start post process for operator collector: %s", collector_name)
            if collector.require_filter_by_step:
                logger.debug("Operator Collector %s requires filter ops by step %s", collector_name, self.step)
                target_op_list = self._get_target_ops_by_step(collector.op_list)
            else:
                logger.debug("Operator Collector %s use operators of all step for analysis", collector_name)
                target_op_list = collector.op_list

            logger.debug("Source number of ops is %s, number of ops after filtered by rank is %s",
                         len(collector.op_list), len(target_op_list))

            collector_kwargs = self.get_post_process_kwargs(collector_name)
            collector.post_process(target_op_list, **collector_kwargs)
            for property_name, property_value in collector.attribute_to_dataset.items():
                setattr(self, property_name, property_value)



@singleton
class ScheduleAnalysisDataset(BaseTimelineEventDataset):
    collector_map = OrderedDict(
        StepCollector=StepCollector(),
        MemCollector=MemCollector(),
        OpCompileCollector=OpCompileCollector(),
        SynchronizeStreamCollector=SynchronizeStreamCollector(),
        DataloaderCollector=DataloaderCollector(),
        SyncBNCollector=SyncBNCollector(),
        AtenCollector=AtenCollector(),
        OptimizerCollector=OptimizerCollector(),
        GcCollector=GcCollector(),
        FreeEventsCollector=FreeEventsCollector(),
        AclEventsCollector=AclEventsCollector()
    )

    def __init__(self, collection_path, data: dict, build_dataset=True, **kwargs) -> None:
        super().__init__(collection_path, data, build_dataset, **kwargs)
        self.aten = None
        self.synchronize_stream = None
        self._collector_post_process()
        self._post_process()

    def _post_process(self):
        # eliminate sub aten operator of the first level aten operator by 'ts' and 'dur',
        # keep the first level aten operator contiguous
        formated_atens = []
        if not hasattr(self, "aten"):
            return

        for event in sorted(self.aten, key=lambda x: x.get("ts", -1)):
            if event.name.startswith(Constant.ATEN):
                if not formated_atens or not formated_atens[-1].ts_include(event):
                    formated_atens.append(event)

        self.aten = formated_atens


@singleton
class ComputationAnalysisDataset(BaseTimelineEventDataset):
    collector_map = OrderedDict(
        StepCollector=StepCollector(),
        SpecificTaskTypeOpCollector=SpecificTaskTypeOpCollector(),
        TorchToNpuCollector=TorchToNpuCollector(),
        AclToNpuCollector=AclToNpuCollector(),
        OpStackCollector=OpStackCollector(),
        FrequencyCollector=FrequencyCollector(),
    )

    def __init__(self, collection_path, data: dict, build_dataset=True, **kwargs) -> None:
        super().__init__(collection_path, data, build_dataset, **kwargs)
        self._collector_post_process()
