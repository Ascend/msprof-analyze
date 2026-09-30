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
import sys
from collections import defaultdict, Counter

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.trace_event_bean import TraceEventBean
from msprof_analyze.compare_tools.compare_backend.profiling_parser.base_profiling_parser import BaseProfilingParser
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class GPUProfilingParser(BaseProfilingParser):
    SDMA_MARK_LIST = ['htod', 'dtod', 'dtoh', 'memset (device)']
    FLOW_CAT = ("async_gpu", "async_cpu_to_gpu", "ac2g", "async")
    TORCH_OP_CAT = ("cpu_op", "user_annotation", "cuda_runtime", "operator", "runtime")

    def __init__(self, args: any, path_dict: dict, step_id: int = Constant.VOID_STEP):
        super().__init__(args, path_dict, step_id)
        self._flow_cat = (args.gpu_flow_cat,) if args.gpu_flow_cat else self.FLOW_CAT
        self._compute_stream_id = self._infer_compute_stream_id()
        self._marks = defaultdict(int)
        self._aten_index = 0
        self._find_bwd_tid()

    @classmethod
    def __is_sdma_time(cls, name: str):
        return any(mask in name.lower() for mask in cls.SDMA_MARK_LIST)

    def _update_kernel_details(self):
        pass

    def _calculate_mc2_communication_time(self, kernel):
        pass

    def _update_memory_list(self):
        if not self._enable_memory_compare:
            return
        self._memory_events.sort(key=lambda x: x.start_time)
        addr_dict = {}
        for memory_event in self._memory_events:
            allocate_bytes = memory_event.bytes_kb
            record = addr_dict.get(memory_event.addr)
            if allocate_bytes > 0:
                if record:
                    self._result_data.update_memory_list(record)
                addr_dict[memory_event.addr] = {
                    Constant.SIZE: allocate_bytes,
                    Constant.TS: memory_event.start_time,
                    Constant.ALLOCATION_TIME: memory_event.start_time,
                }
            if allocate_bytes < 0 and record:
                if abs(allocate_bytes) == record.get(Constant.SIZE):
                    record[Constant.RELEASE_TIME] = memory_event.start_time
                    self._result_data.update_memory_list(record)
                del addr_dict[memory_event.addr]
        for record in addr_dict.values():
            self._result_data.update_memory_list(record)

    def _update_overall_metrics(self):
        self._calculate_performance_time()
        self.__parse_memory_reserved()
        self._result_data.overall_metrics.calculate_schedule_time()
        self._result_data.overall_metrics.trans_time_to_s()

    def _calculate_performance_time(self):
        min_ts = sys.float_info.max
        max_ts = sys.float_info.min
        kernels = list(self._all_kernels.values())
        kernels.sort(key=lambda x: x.start_time)
        flow_dict_new = self._get_flow_time_dict()
        computing_events = []
        for event in kernels:
            if event.stream:
                min_ts = min(event.start_time, min_ts)
                max_ts = max(event.end_time, max_ts)
            if event.stream == self._compute_stream_id and self.__is_sdma_time(event.name):
                self._result_data.overall_metrics.update_sdma_stream_info(event.dur)
                continue
            if not event.is_kernel_cat():
                continue
            self.__add_marks(event)
            if event.is_nccl_name():
                continue
            computing_events.append(event)
        ordered_computing_events = sorted(
            ((flow_dict_new.get(event.start_time, 0), event) for event in computing_events), key=lambda x: x[0]
        )
        for flow_start_time, event in ordered_computing_events:
            self.categorize_computing_performance_data(event, flow_start_time)
        self._result_data.overall_metrics.set_e2e_time(float(max_ts - min_ts))
        self.__add_compute_and_overlap_time()

    def __add_compute_and_overlap_time(self):
        compute_time = len([_ for _, value in self._marks.items() if value < 0])
        communication_not_overlapped = len([_ for _, value in self._marks.items() if value > 0])
        self._result_data.overall_metrics.set_compute_time(compute_time)
        self._result_data.overall_metrics.set_comm_not_overlap(communication_not_overlapped)

    def __add_marks(self, event: TraceEventBean):
        if event.is_nccl_name():
            for timestep in range(int(event.start_time + 1), int(event.end_time + 1)):
                self._marks[str(timestep)] += 1  # mark this timestep in communication stream
        else:
            for timestep in range(int(event.start_time + 1), int(event.end_time + 1)):
                self._marks[str(timestep)] += -100  # mark this timestep in compute stream

    def _picking_memory_event(self, event: TraceEventBean):
        if event.is_memory_event():
            self._memory_events.append(event)
            return True
        return False

    def _is_torch_op_event(self, event: TraceEventBean):
        return event.lower_cat in self.TORCH_OP_CAT

    def _is_kernel_event(self, event: TraceEventBean):
        return event.is_kernel_cat() or event.is_memory_copy_cat()

    def _is_flow_event(self, event: TraceEventBean):
        return event.lower_cat in self._flow_cat

    def __parse_memory_reserved(self):
        if not self._memory_events:
            logger.info("Gpu profiling data doesn't contain memory info.")
            return
        memory_used = max(event.total_reserved for event in self._memory_events) / 1024**3
        self._result_data.overall_metrics.set_memory_used(memory_used)

    def _get_dispatch_func(self):
        func_set = set()
        if self._enable_memory_compare or self._enable_operator_compare or self._enable_profiling_compare:
            func_set.add(self._picking_torch_op_event)
        if self._enable_communication_compare or self._enable_profiling_compare:
            func_set.add(self._picking_kernel_event)
        if self._enable_operator_compare:
            func_set.add(self._picking_python_function_event)
            func_set.add(self._picking_fwdbwd_flow_event)
        if self._enable_operator_compare or self._args.max_kernel_num:
            func_set.add(self._picking_kernel_event)
            func_set.add(self._picking_flow_event)
        if self._enable_memory_compare or self._enable_profiling_compare:
            func_set.add(self._picking_memory_event)
        if self._enable_profiling_compare:
            func_set.add(self._picking_flow_event)
        if self._enable_api_compare:
            func_set.add(self._picking_torch_op_event)
        return list(func_set)

    def _infer_compute_stream_id(self):
        if not self._enable_profiling_compare:
            return -1
        kernel_stream_ids = []
        for event in self._trace_event_generator(Constant.GPU):
            if event.is_kernel_except_nccl() and event.stream:
                kernel_stream_ids.append(event.stream)
        if not kernel_stream_ids:
            raise RuntimeError('The profiling data does not contain kernel running data.')
        counter = Counter(kernel_stream_ids)
        return counter.most_common(1)[0][0]

    def _find_bwd_tid(self):
        for event in self._trace_event_generator(Constant.GPU):
            if event.is_fwdbwd() and event.is_flow_end():
                self._bwd_tid = event.tid
                break
