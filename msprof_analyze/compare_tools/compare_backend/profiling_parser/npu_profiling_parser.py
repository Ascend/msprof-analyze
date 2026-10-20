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
import os
import sys
from math import ceil

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.kernel_details_bean import (
    KernelDetailsBean,
)
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.memory_record_bean import (
    MemoryRecordBean,
)
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.operator_memory_bean import (
    OperatorMemoryBean,
)
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.profiling_parser.base_profiling_parser import BaseProfilingParser
from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.op_stastic_bean import OpStatisticBean
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class NPUProfilingParser(BaseProfilingParser):
    FLOW_CAT = "async_npu"
    TORCH_OP_CAT = "cpu_op"
    ACTIVE_CPU = "ProfilerActivity.CPU"
    LEVEL_0 = "Level0"

    def __init__(self, args: any, path_dict: dict, step_id: int = Constant.VOID_STEP):
        super().__init__(args, path_dict, step_id)
        self._path_level = NPUProfilingParser._get_path_level(path_dict)
        self._operator_memory_path = os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "operator_memory.csv")
        self._memory_record_path = os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "memory_record.csv")
        self._kernel_detail_path = os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "kernel_details.csv")
        self._op_statistic_path = os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "op_statistic.csv")
        self._communication_path = os.path.join(path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""), "communication.json")
        self._info_json_path = path_dict.get(Constant.INFO_JSON_PATH, "")
        self._hccl_pid = None
        self._hccl_op_tid_list = []
        self._kernel_pid = None
        self._overlap_pid = None
        self._enqueue_dict = {}
        self._dequeue_data = []
        self._overlap_analysis = []
        self._group_comm_tid_dict = {}
        self._hccl_tid_name_dict = {}
        self._c_core_sqe_list = []
        self._c_core_sqe_index = 0
        if any(
            (
                self._enable_profiling_compare,
                self._enable_operator_compare,
                self._enable_memory_compare,
                self._enable_api_compare,
                self._enable_communication_compare,
            )
        ):
            self._filter_meta_id()

    @staticmethod
    def _get_path_level(path_dict):
        if not path_dict.get(Constant.PROFILING_PATH, ""):
            return Constant.PROFILING_PATH
        if path_dict.get(Constant.PROFILING_PATH, "") == path_dict.get(Constant.TRACE_PATH, ""):
            return Constant.TRACE_PATH
        if path_dict.get(Constant.PROFILING_PATH, "") == path_dict.get(Constant.ASCEND_OUTPUT_PATH, ""):
            return Constant.ASCEND_OUTPUT_PATH
        return Constant.PROFILING_PATH

    @staticmethod
    def __calculate_uncovered_comm_range(comm_events, uncovered_comm_events):
        class Event:
            def __init__(self, start_time, end_time):
                self.start_time = start_time
                self.end_time = end_time

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
        return float(overlap_time)

    @classmethod
    def _read_csv_data(cls, file_path, bean):
        data = []
        file_name = os.path.basename(file_path)
        try:
            data = FileManager.read_csv_file(file_path, bean)
        except FileNotFoundError:
            logger.warning("The file %s does not exist.", file_name)
        except Exception:
            logger.error("Failed to read %s.", file_name)
        return data

    def _get_dispatch_func(self):
        func_list = set()
        if self._enable_memory_compare or self._enable_operator_compare or self._enable_profiling_compare:
            func_list.add(self._picking_torch_op_event)
        if self._enable_operator_compare or self._args.max_kernel_num:
            func_list.add(self._picking_kernel_event)
            func_list.add(self._picking_flow_event)
        if self._enable_operator_compare:
            func_list.add(self._picking_python_function_event)
            func_list.add(self._picking_fwdbwd_flow_event)
        if self._enable_memory_compare:
            func_list.add(self._picking_task_queue_data)
        if self._enable_communication_compare:
            func_list.add(self._picking_hccl_event)
        if self._enable_profiling_compare:
            func_list.add(self._picking_overlap_analysis_data)
            func_list.add(self._picking_kernel_event)
            func_list.add(self._picking_hccl_event)
            func_list.add(self._picking_flow_event)
        if self._enable_api_compare:
            func_list.add(self._picking_torch_op_event)
        if self._step_id != Constant.VOID_STEP:
            func_list.add(self._picking_torch_op_event)
        return list(func_list)

    def _update_kernel_details(self):
        if self._path_level == Constant.TRACE_PATH:
            return
        if self._args.use_kernel_type:
            op_statistics = self._read_csv_data(self._op_statistic_path, OpStatisticBean)
            if not op_statistics:
                return
            self._result_data.update_kernel_details(
                {f"{kernel.kernel_type}-{kernel.core_type}": kernel for kernel in op_statistics}
            )
            return

        kernel_details = self._read_csv_data(self._kernel_detail_path, KernelDetailsBean)
        if not kernel_details:
            return
        kernels_dict = {}
        for kernel in kernel_details:
            if kernel.is_invalid_op_type():
                continue
            if self._step_id not in (Constant.VOID_STEP, kernel.step_id):
                continue
            input_shapes = kernel.input_shapes if kernel.input_shapes else 'N/A'
            kernels_dict.setdefault(kernel.op_type, {}).setdefault(input_shapes, []).append(
                [kernel.name, kernel.duration]
            )
        if not kernels_dict:
            if self._step_id != Constant.VOID_STEP:
                msg = (
                    f"There is no kernel details information for step {self._step_id},"
                    " please check whether the data contains this step."
                )
                raise RuntimeError(msg)
            else:
                logger.warning("Failed to enable enable_kernel_compare,kernel_details.csv lacks duration.")
            return
        self._result_data.update_kernel_details(kernels_dict)

    def _update_memory_list(self):
        if self._path_level == Constant.TRACE_PATH:
            return
        memory_data = self._read_csv_data(self._operator_memory_path, OperatorMemoryBean)
        if memory_data:
            self._dequeue_data.sort(key=lambda x: x.start_time)
        for data in memory_data:
            if not data.allocation_time:
                continue
            if data.is_cann_op():
                matched_corr_id = self.__match_dequeue_data(data.allocation_time)
                if matched_corr_id == Constant.INVALID_VALUE:
                    continue
                self._result_data.update_memory_list(
                    {
                        Constant.SIZE: data.size,
                        Constant.TS: self._enqueue_dict.get(matched_corr_id, 0),
                        Constant.NAME: data.name,
                        Constant.ALLOCATION_TIME: data.allocation_time,
                        Constant.RELEASE_TIME: data.release_time,
                    }
                )
            else:
                self._result_data.update_memory_list(
                    {
                        Constant.SIZE: data.size,
                        Constant.TS: data.allocation_time,
                        Constant.ALLOCATION_TIME: data.allocation_time,
                        Constant.RELEASE_TIME: data.release_time,
                    }
                )

    def _update_kernel_dict(self):
        kernel_details = []
        if self._path_level != Constant.TRACE_PATH:
            kernel_details = self._read_csv_data(self._kernel_detail_path, KernelDetailsBean)
        input_shape_dict = {kernel.start_time: kernel.input_shapes for kernel in kernel_details}
        for kernel in self._all_kernels.values():
            input_shape = input_shape_dict.get(kernel.start_time, "")
            kernel.input_shapes = input_shape
        super()._update_kernel_dict()

    def __match_dequeue_data(self, ts_time: float) -> int:
        if not self._dequeue_data:
            return Constant.INVALID_VALUE
        left, right = 0, len(self._dequeue_data) - 1
        while right > left:
            mid = left + ceil((right - left) / 2)
            if ts_time >= self._dequeue_data[mid].start_time:
                left = mid
            else:
                right = mid - 1
        return (
            self._dequeue_data[left].corr_id
            if self._dequeue_data[left].start_time <= ts_time <= self._dequeue_data[left].end_time
            else Constant.INVALID_VALUE
        )

    def _update_bandwidth(self):
        if self._path_level == Constant.TRACE_PATH:
            return
        try:
            communication_json = FileManager.read_json_file(self._communication_path)
        except FileNotFoundError:
            logger.warning("The file communication.json does not exist.")
            return
        except Exception:
            logger.error("Failed to read communication.json.")
            return
        if not communication_json:
            logger.warning("The communication.json file is empty.")
            return
        rdma_bandwidth = sdma_bandwidth = 0
        for _, group_dict in communication_json.items():
            step_dict = group_dict.get("collective", {})
            total_op_info = step_dict.get("Total Op Info", {})
            rdma_size_mb = rdma_time_ms = sdma_size_mb = sdma_time_ms = 0
            if "Communication Bandwidth Info" in total_op_info:
                bandwidth_info = total_op_info["Communication Bandwidth Info"]
                if "RDMA" in bandwidth_info:
                    rdma_info = bandwidth_info["RDMA"]
                    rdma_size_mb += rdma_info.get("Transit Size(MB)", 0)  # 单位为 MB
                    rdma_time_ms += rdma_info.get("Transit Time(ms)", 0)  # 单位为 MS
                if "SDMA" in bandwidth_info:
                    sdma_info = bandwidth_info["SDMA"]
                    sdma_size_mb += sdma_info.get("Transit Size(MB)", 0)  # 单位为 MB
                    sdma_time_ms += sdma_info.get("Transit Time(ms)", 0)  # 单位为 MS
                rdma_bandwidth = rdma_size_mb / rdma_time_ms if rdma_time_ms > 0 else 0
                sdma_bandwidth = sdma_size_mb / sdma_time_ms if sdma_time_ms > 0 else 0
        self._result_data.overall_metrics.set_rdma_bandwidth(rdma_bandwidth)
        self._result_data.overall_metrics.set_sdma_bandwidth(sdma_bandwidth)

    def _update_overall_metrics(self):
        if self._path_level == Constant.PROFILING_PATH:
            self.__parse_info_json()
        self.__parse_mem_csv()
        self.__parse_kernel_csv()
        self.__add_lccl_time()
        self.__add_sdma_time()
        self.__add_overlap_analysis_time()
        self.__add_communication_wait_time()
        self.__add_uncovered_communication_overlap_time()
        self._result_data.overall_metrics.calculate_schedule_time()
        self._result_data.overall_metrics.trans_time_to_s()
        self._result_data.overall_metrics.calculate_other_time()
        self._update_bandwidth()

    def __add_uncovered_communication_overlap_time(self):
        comm_overlap_time_dict = {}
        comm_tid_list = list(self._group_comm_tid_dict.keys())
        if not comm_tid_list:
            return
        uncovered_communication_events = list(filter(lambda x: x.is_comm_not_overlap(), self._overlap_analysis))
        uncovered_communication_events.sort(key=lambda x: x.start_time)
        for index, comm_tid in enumerate(comm_tid_list):
            if index == len(comm_tid_list) - 1:
                continue
            for index_2 in range(index + 1, len(comm_tid_list)):
                comm_op_events_1 = list(filter(lambda x: x.tid == comm_tid, self._comm_list))  # pylint: disable=cell-var-from-loop
                comm_op_events_1.sort(key=lambda x: x.start_time)
                uncovered_comm_op_events_1 = self.__calculate_uncovered_comm_range(
                    comm_op_events_1, uncovered_communication_events
                )
                comm_op_events_2 = list(filter(lambda x: x.tid == comm_tid_list[index_2], self._comm_list))  # pylint: disable=cell-var-from-loop
                comm_op_events_2.sort(key=lambda x: x.start_time)
                uncovered_comm_op_events_2 = self.__calculate_uncovered_comm_range(
                    comm_op_events_2, uncovered_communication_events
                )
                overlap_time = self.__calculate_overlap_time_with_uncovered_communication(
                    uncovered_comm_op_events_1, uncovered_comm_op_events_2
                )
                if overlap_time:
                    comm_overlap_time_dict[
                        (self._hccl_tid_name_dict.get(comm_tid), self._hccl_tid_name_dict.get(comm_tid_list[index_2]))
                    ] = overlap_time / Constant.MILLISECONDS_TO_MICROSECONDS
        self._result_data.overall_metrics.update_communication_overlap_time(comm_overlap_time_dict)

    def __add_communication_wait_time(self):
        """
        按group统计uncovered communication time的卡间等待时间、传输时间。选择传输时间最长的plane作为该group的卡间等待时间、传输时间。
        卡间等待时间用Notify_Wait任务（部分做rdma传输的Notify_Wait任务除外）计算，传输时间=通信时间-卡间等待时间。
        rdma传输有两种范式，一种是RDMASend、RDMASend、Notify_Wait、RDMASend、Notify_Wait，里面的notify wait都是传输时间；
        还有一种是RDMASend、RDMASend、Notify_Wait, 这个notify wait也是传输时间。
        因此，满足前2个task为RDMASend、RDMASend的Notify_Wait不计入卡间等待时间，
        满足前4个task为RDMASend、RDMASend、Notify_Wait、RDMASend的Notify_Wait不计入卡间等待时间。
        """
        notify_wait_task_group_by_tid = {}
        self._comm_task_list.sort(key=lambda x: x.start_time)
        last_4_task_mode_dict = {}  # 前4个task的类型，R代表RDMASend/N代表Notify_Wait/O代表Other
        for task_event in self._comm_task_list:
            last_4_task_mode = last_4_task_mode_dict.get(task_event.tid)
            if task_event.name == 'RDMASend':
                last_4_task_mode_dict[task_event.tid] = f"{last_4_task_mode[1:]}R" if last_4_task_mode else "OOOR"
            elif task_event.name == 'Notify_Wait':
                if not last_4_task_mode or last_4_task_mode != "RRNR" and last_4_task_mode[2:] != "RR":
                    notify_wait_task_group_by_tid.setdefault(task_event.tid, []).append(task_event)
                last_4_task_mode_dict[task_event.tid] = f"{last_4_task_mode[1:]}N" if last_4_task_mode else "OOON"
            else:
                last_4_task_mode_dict[task_event.tid] = f"{last_4_task_mode[1:]}O" if last_4_task_mode else "OOOO"
        uncovered_communication_events = list(filter(lambda x: x.is_comm_not_overlap(), self._overlap_analysis))
        uncovered_communication_events.sort(key=lambda x: x.start_time)
        group_comm_time_dict = {}
        for comm_tid, tid_list in self._group_comm_tid_dict.items():
            min_wait_time = float("inf")
            min_wait_tid = None
            for tid in tid_list:
                notify_wait_time = sum((event.dur for event in notify_wait_task_group_by_tid.get(tid, [])))
                if notify_wait_time < min_wait_time:
                    min_wait_time = notify_wait_time
                    min_wait_tid = tid
            notify_wait_events = notify_wait_task_group_by_tid.get(min_wait_tid, [])
            communication_op_events = list(filter(lambda x: x.tid == comm_tid, self._comm_list))  # pylint: disable=cell-var-from-loop
            wait_time = self.__calculate_overlap_time_with_uncovered_communication(
                uncovered_communication_events, notify_wait_events
            )
            uncovered_communication_time = self.__calculate_overlap_time_with_uncovered_communication(
                uncovered_communication_events, communication_op_events
            )
            group_comm_time_dict[self._hccl_tid_name_dict.get(comm_tid)] = {
                Constant.WAIT_TIME: wait_time,
                Constant.TRANSMIT_TIME: uncovered_communication_time - wait_time,
            }
        self._result_data.overall_metrics.update_communication_group_time(group_comm_time_dict)

    def _picking_hccl_event(self, event: TraceEventBean):
        if event.pid != self._hccl_pid or not event.is_x_mode():
            return False
        if event.tid in self._hccl_op_tid_list:
            self._comm_list.append(event)
        else:
            self._comm_task_list.append(event)
        return True

    def _picking_task_queue_data(self, event: TraceEventBean):
        if event.is_enqueue():
            self._enqueue_dict[event.corr_id] = event.start_time
            return True
        elif event.is_dequeue():
            self._dequeue_data.append(event)
            return True
        return False

    def _picking_overlap_analysis_data(self, event: TraceEventBean):
        if event.pid == self._overlap_pid and event.is_x_mode():
            self._overlap_analysis.append(event)
            return True
        return False

    def _calculate_mc2_communication_time(self, kernel: KernelDetailsBean):
        sqe_data = []
        while self._c_core_sqe_index < len(self._c_core_sqe_list):
            end_time = self._c_core_sqe_list[self._c_core_sqe_index].end_time
            if end_time < kernel.start_time:
                self._c_core_sqe_index += 1
                continue
            if end_time <= kernel.end_time:
                sqe_data.append(self._c_core_sqe_list[self._c_core_sqe_index])
                self._c_core_sqe_index += 1
                continue
            break
        communication_time = 0
        for i in range(0, len(sqe_data), 2):
            if i + 1 < len(sqe_data):
                communication_time += sqe_data[i + 1].end_time - sqe_data[i].end_time
        return float(communication_time)

    def _is_kernel_event(self, event: TraceEventBean):
        return event.pid == self._kernel_pid and event.is_x_mode()

    def _is_flow_event(self, event: TraceEventBean):
        return event.lower_cat == self.FLOW_CAT

    def _is_torch_op_event(self, event: TraceEventBean):
        return event.lower_cat == self.TORCH_OP_CAT

    def _filter_meta_id(self):
        thread_events, thread_sort_events = [], []
        for event in self._trace_event_generator(Constant.NPU):
            if event.is_fwdbwd() and event.is_flow_end():
                self._bwd_tid = event.tid
            if not event.is_m_mode():
                continue
            if event.is_process_meta():
                if event.is_hccl_process_name():
                    self._hccl_pid = event.pid
                elif event.is_npu_process_name():
                    self._kernel_pid = event.pid
                elif event.is_overlap_process_name():
                    self._overlap_pid = event.pid
            if event.is_thread_meta():
                thread_events.append(event)
            if event.is_thread_sort_meta():
                thread_sort_events.append(event)

        if not self._enable_communication_compare and not self._enable_profiling_compare:
            return
        # 获取hccl bar的所有thread信息
        tid_index_dict = {}
        for event in thread_events:
            if event.pid == self._hccl_pid:
                self._hccl_tid_name_dict[event.tid] = event.args.get("name", "")
        for event in thread_sort_events:
            if event.pid == self._hccl_pid:
                tid_index_dict[event.args.get("sort_index", 0)] = event.tid
        ordered_index = sorted(tid_index_dict.keys())
        cur_tid = None
        for index in ordered_index:
            tid = tid_index_dict.get(index)
            tid_name = self._hccl_tid_name_dict.get(tid, "")
            if "Communication" in tid_name:
                self._hccl_op_tid_list.append(tid)
                self._group_comm_tid_dict.setdefault(tid, [])
                cur_tid = tid
                continue
            if tid_name:
                self._group_comm_tid_dict.setdefault(cur_tid, []).append(tid)

    def __parse_info_json(self):
        try:
            json_data = FileManager.read_json_file(self._info_json_path)
        except Exception:
            logger.error('Failed to read profiler_info.json.')
            return
        if not isinstance(json_data, dict) or not json_data:
            logger.warning('Invalid profiler info.')
            return
        level = json_data.get('config', {}).get('experimental_config', {}).get('_profiler_level', '')
        if self.LEVEL_0 != level:
            return

    def __add_lccl_time(self):
        for event in self._all_kernels.values():
            if event.is_lccl():
                self._result_data.overall_metrics.update_lccl_info(event.dur)

    def __parse_kernel_csv(self):
        if self._path_level == Constant.TRACE_PATH:
            return
        try:
            kernel_details = self._read_csv_data(self._kernel_detail_path, KernelDetailsBean)
        except Exception:
            logger.error('Npu kernel details csv file is not available.')
            return
        if not kernel_details or kernel_details[0].is_hide_op_pmu():
            self._result_data.overall_metrics.hide_op_details = True
            return
        flow_dict_new = self._get_flow_time_dict()
        ordered_computing_events = sorted(
            ((flow_dict_new.get(kernel.start_time, 0), kernel) for kernel in kernel_details if not kernel.is_invalid()),
            key=lambda x: x[0],
        )
        self._c_core_sqe_list = list(filter(lambda x: x.is_c_core_sqe(), self._all_kernels.values()))
        self._c_core_sqe_list.sort(key=lambda x: x.start_time)
        for flow_start_time, event in ordered_computing_events:
            self.categorize_computing_performance_data(event, flow_start_time)

    def __parse_mem_csv(self):
        if self._path_level == Constant.TRACE_PATH:
            return
        try:
            memory_record = self._read_csv_data(self._memory_record_path, MemoryRecordBean)
        except FileNotFoundError:
            logger.warning('Npu memory record csv file is not available.')
            return
        except Exception:
            logger.error('Load memory info failed.')
            return
        if memory_record:
            memory_used = max(memory.total_reserved_mb for memory in memory_record) / 1024
            self._result_data.overall_metrics.set_memory_used(memory_used)

    def __add_overlap_analysis_time(self):
        if not self._overlap_analysis:
            logger.warning('Failed to get overlap analysis data.')
            return
        min_ts = sys.float_info.max
        max_ts = sys.float_info.min
        for event in self._overlap_analysis:
            if event.is_computing_event():
                self._result_data.overall_metrics.update_compute_time(event.dur)
                min_ts = min(event.start_time, min_ts)
                max_ts = max(event.end_time, max_ts)
            elif event.is_comm_not_overlap():
                self._result_data.overall_metrics.update_comm_not_overlap(event.dur)
                min_ts = min(event.start_time, min_ts)
                max_ts = max(event.end_time, max_ts)
            else:
                min_ts = min(event.start_time, min_ts)
                max_ts = max(event.end_time, max_ts)
        self._result_data.overall_metrics.set_e2e_time(float(max_ts - min_ts))

    def __add_sdma_time(self) -> (float, int):
        event_wait_stream, ai_core_stream = set(), set()
        sdma_dict = {}
        for event in self._all_kernels.values():
            stream_id = event.stream_id
            if not stream_id:
                continue
            if event.is_event_wait():
                event_wait_stream.add(stream_id)
            elif event.is_sdma_event():
                sdma_dict.setdefault(stream_id, []).append(event.dur)
            elif event.is_compute_event():
                ai_core_stream.add(stream_id)
        compute_stream = event_wait_stream & ai_core_stream if event_wait_stream else ai_core_stream
        for stream in compute_stream:
            dur_list = sdma_dict.get(stream, [])
            self._result_data.overall_metrics.update_sdma_stream_info(sum(dur_list), len(dur_list))
