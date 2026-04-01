# Copyright (c) 2026, Huawei Technologies Co., Ltd.
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
import os
import json

import pandas as pd

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.communication_bottleneck_export import CannTaskExport, PytorchTaskExport, \
    DeviceMemoryTaskExport, ComputeTaskExport, CommunicationTaskExport, AllDeviceNodeLaunchPytorchTaskExport, \
    TargetCommunicationOpWithNameExport, CommunicationOpExport
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.utils import convert_ns_to_us_str, convert_ns_to_us

logger = get_logger()


class TaskDiffSummary:
    """任务在快慢卡之间的差异摘要信息"""

    def __init__(self, level, max_start_diff_task, max_duration_task):
        self.level = level
        self.max_start_diff_task = max_start_diff_task
        self.max_duration_task = max_duration_task

    def to_reason_string(self):
        if self.max_start_diff_task is None or self.max_duration_task is None:
            return None

        return (
            f"{self.level}: max duration-diff op {self.max_duration_task['task_name']}, "
            f"diff {convert_ns_to_us(self.max_duration_task['diff_duration'])} us, "
            f"max start-time-diff op {self.max_start_diff_task['task_name']}, "
            f"diff {convert_ns_to_us(self.max_start_diff_task['diff_start_ns'])} us."
        )


class BottleneckReason:
    """封装通信瓶颈分析结果"""

    def __init__(self):
        self.start_ns = None
        self.end_ns = None
        self.duration = None
        self.comm_name = None
        self.slow_rank_id = None
        self.fast_rank_id = None
        self.reason = None  # 原因描述
    
    def to_dict(self):
        return {
            "startTime(us)": convert_ns_to_us_str(self.start_ns),
            "endTime(us)": convert_ns_to_us_str(self.end_ns),
            "duration(us)": convert_ns_to_us(self.duration),
            "communicationOp": self.comm_name,
            "slowRankId": self.slow_rank_id,
            "fastRankId": self.fast_rank_id,
            "reason": self.reason
        }


class CommunicatonBottleneckAnalysis(BaseRecipeAnalysis):

    # Database and file names
    TABLE_DB_NAME = "CommunicationBottleneck"
    EVENT_SUMMARY_FILE = "communication_bottleneck.csv"
    CONFIG_FILE_NAME = "config.json"
    
    # Default configuration values
    DEFAULT_SLOW_NPU_HAPPEN_THRESHOLD = 0.05
    DEFAULT_DIFF_WAITING_TIME_THRESHOLD = 100000  # 100us
    DEFAULT_START_NS_SHIFTED_THRESHOLD = 1000000  # 1ms
    DEFAULT_DEVICE_BOUND_PROPORTION_THRESHOLD = 0.5
    DEFAULT_TARGET_RANK_ID = 0
    DEFAULT_MAX_ANALYSIS_NUM = 10

    def __init__(self, params):
        super().__init__(params)
        logger.info("CommunicationAnalysis init")
        self.device_bound_proportion_threshold = None
        self.start_ns_shifted_threshold = None
        self.diff_waiting_time_threshold = None
        self.slow_npu_happen_threshold = None
        self.comm_reasons = None
        self.target_comm_name = ""

        if "rank_id" in self._extra_args:
            self.target_rank_id = int(self._extra_args["rank_id"])
        if "top_num" in self._extra_args:
            self.max_analysis_num = int(self._extra_args["top_num"])
        self.parse_config()

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    @classmethod
    def add_parser_argument(cls, parser):
        parser.add_argument("--rank_id", type=int, help="Target rank for analysis", default=cls.DEFAULT_TARGET_RANK_ID)
        parser.add_argument("--top_num", type=int, help="Duration cost top count", default=cls.DEFAULT_MAX_ANALYSIS_NUM)

    @staticmethod
    def compute_diff_from_fast_and_slow_npu(slow_info_df, fast_info_df, clock_shift, shift_threshold):
        if slow_info_df is None or slow_info_df.empty or fast_info_df is None or fast_info_df.empty:
            return pd.DataFrame(
                columns=["start_ns", "duration", "task_name", "diff_start_ns", "diff_duration"]
            ), True
        
        sorted_slow_df = slow_info_df.sort_values(by=["start_ns"], ascending=False)
        sorted_fast_df = fast_info_df.sort_values(by=["start_ns"], ascending=False)
        
        fast_tasks_list = sorted_fast_df.to_dict('records')
        slow_tasks_list = sorted_slow_df.to_dict('records')
        
        # Process slow tasks and find matching fast tasks
        records = []
        is_unaligned = True
        fast_idx = 0
        
        for slow_task in slow_tasks_list:
            task_name = slow_task["task_name"]
            
            for i in range(fast_idx, len(fast_tasks_list)):
                if fast_tasks_list[i]["task_name"] == task_name:
                    fast_task = fast_tasks_list[i]
                    fast_idx = i + 1
                    
                    diff_start_ns = int(slow_task["start_ns"]) - int(fast_task["start_ns"]) + clock_shift
                    diff_duration = slow_task["duration"] - fast_task["duration"]
                    
                    records.append({
                        "start_ns": int(slow_task["start_ns"]),
                        "duration": int(slow_task["duration"]),
                        "task_name": task_name,
                        "diff_start_ns": diff_start_ns,
                        "diff_duration": diff_duration
                    })
                    
                    # Check alignment
                    if diff_start_ns < shift_threshold:
                        is_unaligned = False
                        break
                    
                    break
            
            if not is_unaligned:
                break
        
        if records:
            device_task_record_df = pd.DataFrame(records)
        else:
            device_task_record_df = pd.DataFrame(
                columns=["start_ns", "duration", "task_name", "diff_start_ns", "diff_duration"]
            )
        
        return device_task_record_df, is_unaligned


    def parse_config(self):
        config_path = os.path.join(os.path.dirname(__file__), self.CONFIG_FILE_NAME)
        json_config = FileManager.read_json_file(config_path)
        self.slow_npu_happen_threshold = json_config.get(
            'threshold', {}).get('slow_npu_happen', self.DEFAULT_SLOW_NPU_HAPPEN_THRESHOLD)
        self.diff_waiting_time_threshold = json_config.get(
            'threshold', {}).get('diff_waiting_time', self.DEFAULT_DIFF_WAITING_TIME_THRESHOLD)
        self.start_ns_shifted_threshold = json_config.get(
            'threshold', {}).get('start_ns_shifted', self.DEFAULT_START_NS_SHIFTED_THRESHOLD)
        self.device_bound_proportion_threshold = json_config.get(
            'threshold', {}).get('device_bound_proportion', self.DEFAULT_DEVICE_BOUND_PROPORTION_THRESHOLD)

    def run(self, context):
        if self.target_rank_id not in self._data_map.keys():
            logger.error(f"Target rank_id {self.target_rank_id} not found in profiling path.")
            return
        comm_df = self.obtain_top_communication_ops(self.target_rank_id)
        self.comm_reasons = self.locate_anomaly_reasons(context, comm_df)

        if self._export_type == Constant.DB:
            self.save_db()
        elif self._export_type == Constant.TEXT:
            self.save_csv()
        else:
            logger.error(f"Unknown export type: {self._export_type}")

    def get_rank_profile_db_path(self, rank_id: int):
        return os.path.join(self._data_map[rank_id], Constant.SINGLE_OUTPUT, f"ascend_pytorch_profiler_{rank_id}.db")

    def obtain_top_communication_ops(self, rank_id):
        target_profile_db_path = self.get_rank_profile_db_path(rank_id)
        step_range = self._get_step_range(target_profile_db_path)
        comm_df = CommunicationOpExport(target_profile_db_path, self._recipe_name, step_range).read_export_db()
        
        if comm_df is None or comm_df.empty:
            logger.warning(f"No communication time data found for rank {rank_id}.")
            return None
        return comm_df.head(self.max_analysis_num)

    def locate_anomaly_reasons(self, context, comm_df):
        if comm_df is None or comm_df.empty:
            return None
        reason_list = []
        for idx, row in comm_df.iterrows():
            res = self.analyze_single_comm_op(context, row)
            reason_list.append(res)
        return reason_list

    def analyze_single_comm_op(self, context, comm_row):
        # 创建BottleneckReason实例
        reason = BottleneckReason()
        reason.start_ns = comm_row['start_ns']
        reason.end_ns = comm_row['end_ns']
        reason.duration = comm_row['duration']
        reason.comm_name = comm_row['comm_name']
        self.target_comm_name = comm_row['comm_name']

        # Get data from all NPUs
        mapper_res = self.mapper_func(context)
        valid_res = [res for res in mapper_res if res is not None and not res.empty]
        if not valid_res:
            reason.reason = "[Failed] No data found for the communication operator"
            return reason

        # Get quickest and slowest NPU
        concat_df = pd.concat(valid_res, ignore_index=True).sort_values(by=["duration"], ascending=False)
        quick_npu_info = concat_df.iloc[0]
        slow_npu_info = concat_df.iloc[-1]
        
        # Check if time difference is small
        time_diff_ratio = (quick_npu_info["duration"] - slow_npu_info["duration"]) / quick_npu_info["duration"]
        if time_diff_ratio < self.slow_npu_happen_threshold:
            reason.reason = (f"[Completed] No slow NPU detected: execution time difference is less than "
                             f"{self.slow_npu_happen_threshold}%")
            return reason
        
        # Calculate clock shift and analyze slow NPU
        clock_shift = quick_npu_info["end_ns"] - slow_npu_info["end_ns"]
        reason.slow_rank_id = slow_npu_info["rank_id"]
        reason.fast_rank_id = quick_npu_info["rank_id"]
        
        # 分析慢NPU，结果会更新到reason实例中
        self.analyze_slow_npu(reason, clock_shift, quick_npu_info["start_ns"], slow_npu_info["start_ns"],
                             slow_npu_info["end_ns"])
        
        return reason

    def query_device_task_before_time(self, rank_id, start_ns, end_ns):
        profile_db_path = self.get_rank_profile_db_path(rank_id)
        query_params = {Constant.START_NS: start_ns, Constant.END_NS: end_ns}
        computing_task_df = ComputeTaskExport(profile_db_path, self._recipe_name, query_params).read_export_db()
        communication_task_df = (CommunicationTaskExport(profile_db_path, self._recipe_name, query_params).
                                 read_export_db())
        memory_task_df = DeviceMemoryTaskExport(profile_db_path, self._recipe_name, query_params).read_export_db()
        
        # Merge and sort device task dataframes
        dataframes = []
        if computing_task_df is not None and not computing_task_df.empty:
            dataframes.append(computing_task_df)
        if communication_task_df is not None and not communication_task_df.empty:
            dataframes.append(communication_task_df)
        if memory_task_df is not None and not memory_task_df.empty:
            dataframes.append(memory_task_df)
        
        if not dataframes:
            return None
        
        merged_df = pd.concat(dataframes, ignore_index=True)
        return merged_df.sort_values(by=["start_ns"], ascending=False)

    def query_host_task_before_time(self, rank_id, start_ns, end_ns):
        profile_db_path = self.get_rank_profile_db_path(rank_id)
        param_dict = {Constant.START_NS: str(start_ns), Constant.END_NS: str(end_ns)}

        pytorch_task_df = PytorchTaskExport(profile_db_path, self._recipe_name, param_dict).read_export_db()
        cann_task_df = CannTaskExport(profile_db_path, self._recipe_name, param_dict).read_export_db()
        
        return pytorch_task_df, cann_task_df

    def analyze_slow_npu(self, reason, clock_shift, fast_start_ns, slow_start_ns, slow_end_ns):
        bottleneck, has_data = self._judge_bottleneck_type(reason, fast_start_ns - clock_shift, slow_end_ns)
        if not has_data:
            reason.reason = "[Failed] Insufficient data for analyzing slow NPU bottleneck"
            return
        
        if bottleneck == "Device":
            self._analyze_device_bound(reason, fast_start_ns, slow_start_ns, clock_shift)
        else:
            self._analyze_host_bound(reason, fast_start_ns, slow_start_ns, clock_shift)

    def save_db(self):
        comm_reason_df = self._build_comm_reason_df()
        if comm_reason_df is None:
            return
        self.dump_data(comm_reason_df, Constant.DB_CLUSTER_COMMUNICATION_ANALYZER, self.TABLE_DB_NAME, index=False)

    def save_csv(self):
        comm_reason_df = self._build_comm_reason_df()
        if comm_reason_df is None:
            return
        csv_columns = {
            "startTime(us)": "Start Time(us)",
            "endTime(us)": "End Time(us)",
            "duration(us)": "Duration(us)",
            "communicationOp": "Communication Op",
            "slowRankId": "Slow Rank ID",
            "fastRankId": "Fast Rank ID",
            "reason": "Reason",
        }
        csv_df = comm_reason_df.rename(columns=csv_columns)
        self.dump_data(csv_df, self.EVENT_SUMMARY_FILE, index=False)

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        rank_id = data_map.get(Constant.RANK_ID)
        query_params = {"comm_op_name": self.target_comm_name}
        df = TargetCommunicationOpWithNameExport(profiler_db_path, analysis_class, query_params).read_export_db()
        df["rank_id"] = rank_id
        return df

    def _judge_bottleneck_type(self, reason, start_ns, end_ns):
        """判断瓶颈位置（Device或Host）"""
        slow_profile_db_path = self.get_rank_profile_db_path(reason.slow_rank_id)

        # Get all device node@launch tasks
        query_params = {Constant.START_NS: str(start_ns), Constant.END_NS: str(end_ns)}
        slow_task_df = AllDeviceNodeLaunchPytorchTaskExport(slow_profile_db_path,
                                                            self._recipe_name, query_params).read_export_db()

        if slow_task_df is None or slow_task_df.empty:
            return None, False

        # Calculate waiting times using vectorized operations
        host_waiting_time = (slow_task_df["cann_start_ns"].astype("int64") -
                             slow_task_df["pytorch_end_ns"].astype("int64"))
        device_waiting_time = (slow_task_df["device_start_ns"].astype("int64") -
                               slow_task_df["cann_end_ns"].astype("int64"))
        diff_waiting_time = device_waiting_time - host_waiting_time

        device_problem_cnt = (diff_waiting_time > self.diff_waiting_time_threshold).sum()
        total_cnt = len(slow_task_df)
        is_device_bound = (device_problem_cnt / total_cnt) > self.device_bound_proportion_threshold

        return "Device" if is_device_bound else "Host", True


    def _analyze_device_bound(self, reason, fast_start_ns, slow_start_ns, clock_shift):
        slow_task_before_df = self.query_device_task_before_time(reason.slow_rank_id, 0, slow_start_ns)
        fast_task_before_df = self.query_device_task_before_time(reason.fast_rank_id, 0, fast_start_ns)
        device_summary = self._build_task_diff_summary(slow_task_before_df, fast_task_before_df,
                                                       clock_shift, level="Device")
        if not device_summary:
            reason.reason = "[Device-bound] Tasks are not aligned between slow and fast NPU from the beginning"
            return

        reason_string = device_summary.to_reason_string()
        if reason_string is None:
            reason.reason = "[Device-bound] Failed to find device task differences"
            return
        reason.reason = "[Device-bound]" + reason_string

    def _analyze_host_bound(self, reason, fast_start_ns, slow_start_ns, clock_shift):
        slow_pytorch_df, slow_cann_df = self.query_host_task_before_time(reason.slow_rank_id, 0, slow_start_ns)
        fast_pytorch_df, fast_cann_df = self.query_host_task_before_time(reason.fast_rank_id, 0, fast_start_ns)

        pytorch_summary = self._build_task_diff_summary(slow_pytorch_df, fast_pytorch_df, clock_shift, level="PyTorch")
        cann_summary = self._build_task_diff_summary(slow_cann_df, fast_cann_df, clock_shift, level="CANN")

        if not pytorch_summary:
            reason.reason = "[Host-bound] Tasks are not aligned between slow and fast NPU from the beginning"
            return

        reason_strings = []
        pytorch_reason = pytorch_summary.to_reason_string()
        if pytorch_reason is not None:
            reason_strings.append(pytorch_reason)

        if cann_summary is not None:
            cann_reason = cann_summary.to_reason_string()
            if cann_reason is not None:
                reason_strings.append(cann_reason)

        if reason_strings:
            reason.reason = "[Host-bound] " + " | ".join(reason_strings)
        else:
            reason.reason = "[Host-bound] Failed to find host task differences"

    def _build_task_diff_summary(self, slow_df, fast_df, clock_shift, level):
        task_record_df, is_unalign = self.compute_diff_from_fast_and_slow_npu(
            slow_df, fast_df, clock_shift, self.start_ns_shifted_threshold
        )
        if is_unalign or (task_record_df is None or task_record_df.empty):
            return None
        max_diff_duration_task = task_record_df.sort_values(by=["diff_duration"], ascending=False).iloc[0]
        max_diff_start_task = task_record_df.sort_values(by=["diff_start_ns"], ascending=False).iloc[0]
        return TaskDiffSummary(level, max_diff_start_task, max_diff_duration_task)

    def _build_comm_reason_df(self):
        if self.comm_reasons is None or not self.comm_reasons:
            logger.warning("No communication reasons to save.")
            return None
        reason_dicts = [reason.to_dict() for reason in self.comm_reasons]
        return pd.DataFrame(reason_dicts)