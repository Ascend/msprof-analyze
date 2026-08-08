# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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
import copy
from decimal import Decimal

from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.framework_api_bean import (
    FrameworkApiBean,
)
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.db_data_bean.kernel_bean import (
    KernelBean,
)
from msprof_analyze.prof_common.constant import Constant

from msprof_analyze.prof_common.utils import convert_to_float


class Event:
    def __init__(self, start_time, end_time):
        self.start_time = start_time
        self.end_time = end_time


class OverallMetricsParser:
    FILTER_TASK_TYPE = [
        "KERNEL_AICORE",
        "KERNEL_AIVEC",
        "FFTS_PLUS",
        "KERNEL_MIX_AIC",
        "KERNEL_MIX_AIV",
        "PROFILING_ENABLE",
        "PROFILING_DISABLE",
    ]

    def __init__(self, npu_db_parser):
        self.npu_db_parser = npu_db_parser
        self.cpu_cube_op = [op for op in self.npu_db_parser.result_data.torch_op_data if op.is_cpu_cube_op()]
        self.cpu_cube_op.sort(key=lambda x: x.start_time)
        self.cpu_cube_op_index = 0
        self.connect_map = {
            op.cann_connection_id: op.start_time
            for op in self.npu_db_parser.result_data.torch_op_data
            if op.cann_connection_id
        }
        self.not_overlapped_comm = []
        self.pmu_data = {}
        self._c_core_sqe_list = None
        self._c_core_sqe_index = 0

    @property
    def c_core_sqe_list(self):
        if self._c_core_sqe_list is not None:
            return self._c_core_sqe_list
        sql = """
        SELECT
            round(TASK.endNs - TASK.startNs) AS "Duration",
            TASK.startNs AS "startNs",
            TASK.endNs AS "endNs"
        FROM
            TASK LEFT JOIN STRING_IDS ON TASK.taskType == STRING_IDS.id
        WHERE STRING_IDS.value == 'C_CORE_SQE'{}
        ORDER BY TASK.startNs
        """
        sql = (
            sql.format(" AND TASK.startNs>=? AND TASK.startNs<=?") if self.npu_db_parser.step_range else sql.format("")
        )
        if self.npu_db_parser.step_range:
            all_data = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql, param=self.npu_db_parser.step_range)
        else:
            all_data = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql)
        self._c_core_sqe_list = [KernelBean(data) for data in all_data]
        return self._c_core_sqe_list

    @staticmethod
    def merge_intervals(intervals):
        """
        合并重叠的区间
        :param intervals: 区间列表，每个区间是一个包含两个整数的列表 [start, end]
        :return: 合并后的区间列表
        """
        if not intervals:
            return []

        intervals.sort(key=lambda x: x[0])
        merged = [copy.deepcopy(intervals[0])]
        for current in intervals[1:]:
            # 获取合并列表中最后一个区间的结束位置
            last_merged_end = merged[-1][1]
            # 如果当前区间的起始位置小于等于最后一个合并区间的结束位置，则合并
            if current[0] <= last_merged_end:
                merged[-1][1] = max(last_merged_end, current[1])
            else:
                # 否则，将当前区间添加到合并列表中
                merged.append(copy.deepcopy(current))

        return merged

    @staticmethod
    def __calculate_overlap_time_with_uncovered_communication(uncovered_communication_events: list, events: list):
        overlap_time = 0
        events.sort(key=lambda x: x.start_time)
        index = 0
        for comm_event in uncovered_communication_events:
            pre_overlap_ts = comm_event.start_time
            while index < len(events):
                event = events[index]
                if event.end_time <= comm_event.start_time:
                    index += 1
                    continue
                if event.start_time >= comm_event.end_time:
                    break
                if event.end_time >= comm_event.end_time:
                    overlap_time += comm_event.end_time - max(event.start_time, pre_overlap_ts)
                    break
                overlap_time += event.end_time - max(event.start_time, pre_overlap_ts)
                index += 1
        return convert_to_float(overlap_time)

    @staticmethod
    def __calculate_uncovered_comm_range(comm_events, uncovered_comm_events):
        uncovered_comm_range = []
        index = 0
        for comm_event in comm_events:
            while index < len(uncovered_comm_events):
                if uncovered_comm_events[index].end_time < comm_event.start_time:
                    index += 1
                    continue
                if uncovered_comm_events[index].start_time > comm_event.end_time:
                    break
                if uncovered_comm_events[index].end_time < comm_event.end_time:
                    uncovered_comm_range.append(
                        Event(
                            max(comm_event.start_time, uncovered_comm_events[index].start_time),
                            uncovered_comm_events[index].end_time,
                        )
                    )
                    index += 1
                    continue
                uncovered_comm_range.append(
                    Event(
                        max(comm_event.start_time, uncovered_comm_events[index].start_time),
                        min(comm_event.end_time, uncovered_comm_events[index].end_time),
                    )
                )
                break
        return uncovered_comm_range

    def update_overall_metrics(self):
        self.calculate_memory_usage_peak()
        self.calculate_computing_time()
        self.calculate_lccl_time()
        self.calculate_sdma_time()
        self.calculate_overlap_analysis_time()
        self.calculate_communication_wait_time()
        self.calculate_uncovered_communication_overlap_time()
        self.npu_db_parser.result_data.overall_metrics.calculate_schedule_time()
        self.npu_db_parser.result_data.overall_metrics.trans_time_to_s()
        self.npu_db_parser.result_data.overall_metrics.calculate_other_time()

    def calculate_memory_usage_peak(self):
        if not DBManager.judge_table_exists(self.npu_db_parser.cursor, Constant.TABLE_MEMORY_RECORD):
            return
        sql = "SELECT max(totalReserved) AS 'totalReserved' FROM MEMORY_RECORD {}"
        sql = sql.format("WHERE timestamp>=? AND timestamp<=?") if self.npu_db_parser.step_range else sql.format("")
        if self.npu_db_parser.step_range:
            all_data = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql, param=self.npu_db_parser.step_range)
        else:
            all_data = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql)
        if all_data:
            self.npu_db_parser.result_data.overall_metrics.set_memory_used(
                all_data[0].get('totalReserved', 0) / 1024 / 1024 / 1024
            )

    def calculate_computing_time(self):
        if DBManager.judge_table_exists(self.npu_db_parser.cursor, Constant.TABLE_TASK_PMU_INFO):
            sql = """
            SELECT
                TASK_PMU_INFO.globalTaskId AS "globalTaskId",
                STRING_IDS.value AS "pmuName",
                TASK_PMU_INFO.value AS "value"
            FROM
                TASK_PMU_INFO LEFT JOIN STRING_IDS ON TASK_PMU_INFO.name == STRING_IDS.id
            """
            all_data = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql)
            for data in all_data:
                self.pmu_data.setdefault(data.get("globalTaskId"), {})[data.get("pmuName")] = data.get("value")
        kernel_list = sorted(self.npu_db_parser.compute_op_data, key=lambda x: x.connection_id)
        for kernel in kernel_list:
            self.categorize_computing_performance_data(kernel)

    def categorize_computing_performance_data(self, kernel: KernelBean):
        if kernel.is_page_attention():
            self.npu_db_parser.result_data.overall_metrics.update_page_attention_info(kernel.dur)
            return
        if kernel.is_sdma():
            self.npu_db_parser.result_data.overall_metrics.update_sdma_tensor_move_info(kernel.dur)
            return
        if kernel.is_mc2():
            communication_time = self.calculate_mc2_communication_time(kernel)
            computing_time = kernel.mc2_computing_time(self.pmu_data)
            self.npu_db_parser.result_data.overall_metrics.update_mc2_info(
                kernel.name, kernel.dur, computing_time, communication_time
            )
            return
        flow_start_time = self.connect_map.get(kernel.connection_id)
        if flow_start_time:
            while self.cpu_cube_op_index < len(self.cpu_cube_op):
                cur_op = self.cpu_cube_op[self.cpu_cube_op_index]
                if cur_op.end_time < flow_start_time:
                    self.cpu_cube_op_index += 1
                    continue
                if cur_op.start_time <= flow_start_time:
                    self.categorize_cube_performance_data(cur_op, kernel)
                    return
                break

        # 缺失torch至npu连线的算子，判断fa/conv/matmul使用kernel_details.csv的op_type字段
        if kernel.is_flash_attention():
            if kernel.is_fa_bwd():
                self.npu_db_parser.result_data.overall_metrics.update_fa_bwd_cube_info(kernel.dur)
            else:
                self.npu_db_parser.result_data.overall_metrics.update_fa_fwd_cube_info(kernel.dur)
            return
        elif kernel.is_conv():
            if kernel.is_conv_bwd():
                self.npu_db_parser.result_data.overall_metrics.update_conv_bwd_cube_info(kernel.dur)
            else:
                self.npu_db_parser.result_data.overall_metrics.update_conv_fwd_cube_info(kernel.dur)
            return
        elif kernel.is_matmul():
            self.npu_db_parser.result_data.overall_metrics.update_matmul_cube_info(kernel.dur)
            return

        if kernel.is_cube_kernel_cat(self.pmu_data):
            self.npu_db_parser.result_data.overall_metrics.update_other_cube_info(kernel.dur)
        elif kernel.is_trans():
            self.npu_db_parser.result_data.overall_metrics.update_vector_trans_info(kernel.dur)
        else:
            self.npu_db_parser.result_data.overall_metrics.update_vector_notrans_info(kernel.dur)

    def categorize_cube_performance_data(self, cpu_op: FrameworkApiBean, kernel: KernelBean):
        """
        判断fa/conv/matmul/vector使用cpu_op
        """
        if cpu_op.is_fa_for_cpu_op():
            if cpu_op.is_bwd_for_cpu_op():
                if kernel.is_cube_kernel_cat(self.pmu_data):
                    self.npu_db_parser.result_data.overall_metrics.update_fa_bwd_cube_info(kernel.dur)
                else:
                    self.npu_db_parser.result_data.overall_metrics.update_fa_bwd_vector_info(kernel.dur)
            else:
                if kernel.is_cube_kernel_cat(self.pmu_data):
                    self.npu_db_parser.result_data.overall_metrics.update_fa_fwd_cube_info(kernel.dur)
                else:
                    self.npu_db_parser.result_data.overall_metrics.update_fa_fwd_vector_info(kernel.dur)
        elif cpu_op.is_conv_for_cpu_op():
            if cpu_op.is_bwd_for_cpu_op():
                if kernel.is_cube_kernel_cat(self.pmu_data):
                    self.npu_db_parser.result_data.overall_metrics.update_conv_bwd_cube_info(kernel.dur)
                else:
                    self.npu_db_parser.result_data.overall_metrics.update_conv_bwd_vector_info(kernel.dur)
            else:
                if kernel.is_cube_kernel_cat(self.pmu_data):
                    self.npu_db_parser.result_data.overall_metrics.update_conv_fwd_cube_info(kernel.dur)
                else:
                    self.npu_db_parser.result_data.overall_metrics.update_conv_fwd_vector_info(kernel.dur)
        elif cpu_op.is_matmul_for_cpu_op():  # matmul
            if kernel.is_cube_kernel_cat(self.pmu_data):
                self.npu_db_parser.result_data.overall_metrics.update_matmul_cube_info(kernel.dur)
            else:
                self.npu_db_parser.result_data.overall_metrics.update_matmul_vector_info(kernel.dur)

    def calculate_mc2_communication_time(self, kernel: KernelBean):
        sqe_data = []
        while self._c_core_sqe_index < len(self.c_core_sqe_list):
            end_time = self.c_core_sqe_list[self._c_core_sqe_index].end_time
            if end_time < kernel.start_time:
                self._c_core_sqe_index += 1
                continue
            if end_time <= kernel.end_time:
                sqe_data.append(self.c_core_sqe_list[self._c_core_sqe_index])
                self._c_core_sqe_index += 1
                continue
            break
        communication_time = 0
        for i in range(0, len(sqe_data), 2):
            if i + 1 < len(sqe_data):
                communication_time += sqe_data[i + 1].end_time - sqe_data[i].end_time
        return float(communication_time)

    def calculate_communication_wait_time(self):
        """
        按group统计uncovered communication time的卡间等待时间、传输时间。选择传输时间最长的plane作为该group的卡间等待时间、传输时间。
        卡间等待时间用Notify_Wait任务（部分做rdma传输的Notify_Wait任务除外）计算，传输时间=通信时间-卡间等待时间。
        rdma传输有两种范式，一种是RDMASend、RDMASend、Notify_Wait、RDMASend、Notify_Wait，里面的notify wait都是传输时间；
        还有一种是RDMASend、RDMASend、Notify_Wait, 这个notify wait也是传输时间。
        因此，满足前2个task为RDMASend、RDMASend的Notify_Wait不计入卡间等待时间，
        满足前4个task为RDMASend、RDMASend、Notify_Wait、RDMASend的Notify_Wait不计入卡间等待时间。
        """
        notify_wait_task_group_by_plane_id = {}
        self.npu_db_parser.comm_task_data.sort(key=lambda x: x.start_time)
        last_4_task_mode_dict = {}  # 前4个task的类型，R代表RDMASend/N代表Notify_Wait/O代表Other
        for task_event in self.npu_db_parser.comm_task_data:
            last_4_task_mode = last_4_task_mode_dict.get((task_event.group_name, task_event.plane_id))
            if task_event.name == 'RDMASend':
                last_4_task_mode_dict[(task_event.group_name, task_event.plane_id)] = (
                    f"{last_4_task_mode[1:]}R" if last_4_task_mode else "OOOR"
                )
            elif task_event.name == 'Notify_Wait':
                if not last_4_task_mode or last_4_task_mode != "RRNR" and last_4_task_mode[2:] != "RR":
                    notify_wait_task_group_by_plane_id.setdefault(task_event.group_name, {}).setdefault(
                        task_event.plane_id, []
                    ).append(task_event)
                last_4_task_mode_dict[(task_event.group_name, task_event.plane_id)] = (
                    f"{last_4_task_mode[1:]}N" if last_4_task_mode else "OOON"
                )
            else:
                last_4_task_mode_dict[(task_event.group_name, task_event.plane_id)] = (
                    f"{last_4_task_mode[1:]}O" if last_4_task_mode else "OOOO"
                )

        group_comm_time_dict = {}
        for group_name, notify_wait_task_dict in notify_wait_task_group_by_plane_id.items():
            min_wait_time = float("inf")
            notify_wait_tasks = []
            for tasks in notify_wait_task_dict.values():
                notify_wait_time = sum((task.dur for task in tasks))
                if notify_wait_time < min_wait_time:
                    min_wait_time = notify_wait_time
                    notify_wait_tasks = tasks
            comm_ops = [comm_op for comm_op in self.npu_db_parser.comm_op_data if comm_op.group_name == group_name]
            wait_time = self.__calculate_overlap_time_with_uncovered_communication(
                self.not_overlapped_comm, notify_wait_tasks
            )
            uncovered_communication_time = self.__calculate_overlap_time_with_uncovered_communication(
                self.not_overlapped_comm, comm_ops
            )
            group_comm_time_dict[group_name] = {
                Constant.WAIT_TIME: wait_time,
                Constant.TRANSMIT_TIME: uncovered_communication_time - wait_time,
            }

        group_name_list = set(notify_wait_task_group_by_plane_id.keys())
        comm_op_dict = {}
        for comm_op in self.npu_db_parser.comm_op_data:
            if comm_op.group_name in group_name_list:
                continue
            comm_op_dict.setdefault(comm_op.group_name, []).append(comm_op)
        for group_name, comm_ops in comm_op_dict.items():
            uncovered_communication_time = self.__calculate_overlap_time_with_uncovered_communication(
                self.not_overlapped_comm, comm_ops
            )
            group_comm_time_dict[group_name] = {
                Constant.WAIT_TIME: 0,
                Constant.TRANSMIT_TIME: uncovered_communication_time,
            }

        self.npu_db_parser.result_data.overall_metrics.update_communication_group_time(group_comm_time_dict)

    def calculate_uncovered_communication_overlap_time(self):
        comm_overlap_time_dict = {}
        comm_data_dict = {}
        for comm_op in self.npu_db_parser.comm_op_data:
            comm_data_dict.setdefault(comm_op.group_name, []).append(comm_op)
        group_name_list = list(comm_data_dict.keys())
        for index, group_name in enumerate(group_name_list):
            if index == len(group_name_list) - 1:
                continue
            for index_2 in range(index + 1, len(group_name_list)):
                comm_op_events_1 = comm_data_dict.get(group_name)
                comm_op_events_1.sort(key=lambda x: x.start_time)
                uncovered_comm_op_events_1 = self.__calculate_uncovered_comm_range(
                    comm_op_events_1, self.not_overlapped_comm
                )
                comm_op_events_2 = comm_data_dict.get(group_name_list[index_2])
                comm_op_events_2.sort(key=lambda x: x.start_time)
                uncovered_comm_op_events_2 = self.__calculate_uncovered_comm_range(
                    comm_op_events_2, self.not_overlapped_comm
                )
                overlap_time = self.__calculate_overlap_time_with_uncovered_communication(
                    uncovered_comm_op_events_1, uncovered_comm_op_events_2
                )
                if overlap_time:
                    comm_overlap_time_dict[(group_name, group_name_list[index_2])] = (
                        overlap_time / Constant.MILLISECONDS_TO_MICROSECONDS
                    )
        self.npu_db_parser.result_data.overall_metrics.update_communication_overlap_time(comm_overlap_time_dict)

    def calculate_lccl_time(self):
        for event in self.npu_db_parser.comm_op_data:
            if event.is_lccl():
                self.npu_db_parser.result_data.overall_metrics.update_lccl_info(event.dur)

    def calculate_sdma_time(self) -> (float, int):
        sql = """
        SELECT
            STRING_IDS.value AS "task_type",
            round(TASK.endNs - TASK.startNs) AS "Duration",
            TASK.streamId AS "streamId"
        FROM
            TASK LEFT JOIN STRING_IDS ON TASK.taskType == STRING_IDS.id {}
        """
        sql = (
            sql.format("WHERE TASK.startNs>=? AND TASK.startNs<=?") if self.npu_db_parser.step_range else sql.format("")
        )
        if self.npu_db_parser.step_range:
            all_data = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql, param=self.npu_db_parser.step_range)
        else:
            all_data = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql)

        event_wait_stream, ai_core_stream = set(), set()
        sdma_dict = {}
        for op in all_data:
            if op.get("task_type", "") == "EVENT_WAIT_SQE":
                event_wait_stream.add(op.get("streamId"))
            elif op.get("task_type", "") in frozenset({'SDMA_SQE', 'PCIE_DMA_SQE'}):
                sdma_dict.setdefault(op.get("streamId"), []).append(op.get("Duration", 0) / Constant.NS_TO_US)
        for compute_op in self.npu_db_parser.compute_op_data:
            ai_core_stream.add(compute_op.stream_id)
        compute_stream = event_wait_stream & ai_core_stream if event_wait_stream else ai_core_stream
        for stream in compute_stream:
            dur_list = sdma_dict.get(stream, [])
            self.npu_db_parser.result_data.overall_metrics.update_sdma_stream_info(sum(dur_list), len(dur_list))

    def calculate_overlap_analysis_time(self):
        compute_op = [[op.start_time, op.end_time] for op in self.npu_db_parser.compute_op_data]
        merged_compute_op = self.merge_intervals(compute_op)
        compute_time = sum((convert_to_float(op[1] - op[0]) for op in merged_compute_op))

        comm_op = [[op.start_time, op.end_time] for op in self.npu_db_parser.comm_op_data]
        merged_op = self.merge_intervals(compute_op + comm_op)

        not_free_time = sum((convert_to_float(op[1] - op[0]) for op in merged_op))
        self.npu_db_parser.result_data.overall_metrics.update_compute_time(compute_time)
        self.npu_db_parser.result_data.overall_metrics.update_comm_not_overlap(not_free_time - compute_time)
        self.calculate_ascend_task_e2e_time(merged_op[0][0], merged_op[-1][1])

        compute_index = 0
        for op in merged_op:
            start_time = op[0]
            end_time = op[1]
            while compute_index < len(merged_compute_op):
                compute_op = merged_compute_op[compute_index]
                if compute_op[0] <= end_time:
                    self.not_overlapped_comm.append(Event(start_time, compute_op[0]))
                    start_time = compute_op[1]
                    compute_index += 1
                    continue
                break
            self.not_overlapped_comm.append(Event(start_time, end_time))

    def calculate_ascend_task_e2e_time(self, merged_op_earliest_start: float, merged_op_latest_end: float) -> None:
        """
        设备上的端到端(E2E)执行时间。

        通过查询任务表中非计算类、Profiling Enable/Disable类Tasks的最早开始时间和最晚结束时间，结合传入的计算/通信大算子时间边界，
        计算出真实的端到端执行时间并设置到结果数据中。

        Args:
            merged_op_earliest_start (float): 通信/计算算子的最早开始时间（微秒）
            merged_op_latest_end (float): 通信/计算算子的最晚结束时间（微秒）
        """
        # 检查任务表是否存在
        if not DBManager.judge_table_exists(self.npu_db_parser.cursor, Constant.TABLE_TASK):
            return

        # SQL查询模板
        first_task_time_sql_template = """
        SELECT
            TASK.startNs
        FROM TASK
        LEFT JOIN STRING_IDS as str_task ON str_task.id = TASK.taskType
        WHERE {condition}
        ORDER BY TASK.startNs ASC
        LIMIT 1
        """

        last_task_time_sql_template = """
        SELECT
            TASK.endNs
        FROM TASK
        LEFT JOIN STRING_IDS as str_task ON str_task.id = TASK.taskType
        WHERE {condition}
        ORDER BY TASK.endNs DESC
        LIMIT 1
        """

        quoted_task_types = [f"'{task_type}'" for task_type in self.FILTER_TASK_TYPE]
        task_type_condition = f"str_task.value NOT IN ({','.join(quoted_task_types)})"

        # 添加时间范围条件（如果存在step_range）
        if self.npu_db_parser.step_range:
            time_range_condition = "TASK.startNs >= ? AND TASK.startNs <= ?"
            condition = task_type_condition + " AND " + time_range_condition
            params = self.npu_db_parser.step_range
        else:
            condition = task_type_condition
            params = None

        first_task_sql = first_task_time_sql_template.format(condition=condition)
        last_task_sql = last_task_time_sql_template.format(condition=condition)

        first_task_result = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql=first_task_sql, param=params)
        last_task_result = DBManager.fetch_all_data(self.npu_db_parser.cursor, sql=last_task_sql, param=params)

        e2e_start_time = merged_op_earliest_start
        e2e_end_time = merged_op_latest_end

        # 更新最早开始时间
        if first_task_result and first_task_result[0].get("startNs"):
            first_task_start = Decimal(first_task_result[0].get("startNs")) / Constant.NS_TO_US
            e2e_start_time = min(first_task_start, e2e_start_time)

        # 更新最晚结束时间
        if last_task_result and last_task_result[0].get("endNs"):
            last_task_end = Decimal(last_task_result[0].get("endNs")) / Constant.NS_TO_US
            e2e_end_time = max(last_task_end, e2e_end_time)

        # 计算并设置E2E时间
        e2e_duration_us = e2e_end_time - e2e_start_time
        self.npu_db_parser.result_data.overall_metrics.set_e2e_time(convert_to_float(e2e_duration_us))
