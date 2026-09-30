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
from msprof_analyze.prof_common.constant import Constant


class ProfilingInfo:
    __slots__ = [
        'profiling_type',
        'other_time',
        'lccl_num',
        'compute_time',
        'communication_not_overlapped',
        'wait_time',
        'memory_used',
        'e2e_time',
        'scheduling_time',
        'lccl_time',
        'minimal_profiling',
        'hide_op_details',
        'is_level0',
        'fa_time_fwd_cube',
        'fa_num_fwd_cube',
        'fa_time_bwd_cube',
        'fa_num_bwd_cube',
        'fa_time_fwd_vector',
        'fa_num_fwd_vector',
        'fa_time_bwd_vector',
        'fa_num_bwd_vector',
        'conv_time_fwd_cube',
        'conv_num_fwd_cube',
        'conv_time_bwd_cube',
        'conv_num_bwd_cube',
        'conv_time_fwd_vector',
        'conv_num_fwd_vector',
        'conv_time_bwd_vector',
        'conv_num_bwd_vector',
        'matmul_time_cube',
        'matmul_num_cube',
        'matmul_time_vector',
        'matmul_num_vector',
        'page_attention_time',
        'page_attention_num',
        'vector_time_trans',
        'vector_num_trans',
        'vector_time_notrans',
        'vector_num_notrans',
        'sdma_time_tensor_move',
        'sdma_num_tensor_move',
        'sdma_time_stream',
        'sdma_num_stream',
        'other_cube_time',
        'other_cube_num',
        'rdma_bandwidth',
        'sdma_bandwidth',
        'communication_group_time',
        'mc2_time_dict',
        'pg_name_dict',
        'communication_overlap_time',
    ]
    TABLE_NAME = Constant.PERFORMANCE_TABLE
    HEADERS = []
    OVERHEAD = []

    def __init__(self, profiling_type: str):
        self.profiling_type = profiling_type
        self.other_time = 0.0
        self.lccl_num = 0
        self.compute_time = 0.0
        self.communication_not_overlapped = 0.0
        self.wait_time = 0.0
        self.memory_used = 0.0
        self.e2e_time = 0.0
        self.scheduling_time = 0.0
        self.lccl_time = 0.0
        self.minimal_profiling = False
        self.hide_op_details = False
        self.is_level0 = False

        # 性能拆解新指标
        self.fa_time_fwd_cube = 0.0
        self.fa_num_fwd_cube = 0
        self.fa_time_bwd_cube = 0.0
        self.fa_num_bwd_cube = 0
        self.fa_time_fwd_vector = 0.0
        self.fa_num_fwd_vector = 0
        self.fa_time_bwd_vector = 0.0
        self.fa_num_bwd_vector = 0

        self.conv_time_fwd_cube = 0.0
        self.conv_num_fwd_cube = 0
        self.conv_time_bwd_cube = 0.0
        self.conv_num_bwd_cube = 0
        self.conv_time_fwd_vector = 0.0
        self.conv_num_fwd_vector = 0
        self.conv_time_bwd_vector = 0.0
        self.conv_num_bwd_vector = 0

        self.matmul_time_cube = 0.0
        self.matmul_num_cube = 0
        self.matmul_time_vector = 0.0
        self.matmul_num_vector = 0

        self.page_attention_time = 0.0
        self.page_attention_num = 0

        self.vector_time_trans = 0.0
        self.vector_num_trans = 0
        self.vector_time_notrans = 0.0
        self.vector_num_notrans = 0

        self.sdma_time_tensor_move = 0.0
        self.sdma_num_tensor_move = 0
        self.sdma_time_stream = 0.0
        self.sdma_num_stream = 0

        self.other_cube_time = 0.0
        self.other_cube_num = 0
        self.rdma_bandwidth = 0.0
        self.sdma_bandwidth = 0.0

        self.mc2_time_dict = {}

        # 按group展示通信的卡间等待和传输耗时
        self.communication_group_time = {}
        # communication_group与pg_name的对应关系
        self.pg_name_dict = {}
        # 展示通信间的掩盖耗时
        self.communication_overlap_time = {}

    @property
    def e2e_time_ms(self):
        return self.e2e_time * 10**3

    @property
    def compute_time_ms(self):
        return self.compute_time * 10**3

    @property
    def free_time_ms(self):
        return self.scheduling_time * 10**3

    @property
    def communication_not_overlapped_ms(self):
        return self.communication_not_overlapped * 10**3

    @property
    def wait_time_ms(self):
        return self.wait_time * 10**3

    @property
    def transmit_time_ms(self):
        return (self.communication_not_overlapped - self.wait_time) * 10**3

    @property
    def fa_fwd_time(self):
        return self.fa_time_fwd_cube + self.fa_time_fwd_vector

    @property
    def fa_bwd_time(self):
        return self.fa_time_bwd_cube + self.fa_time_bwd_vector

    @property
    def fa_fwd_num(self):
        return self.fa_num_fwd_cube + self.fa_num_fwd_vector

    @property
    def fa_bwd_num(self):
        return self.fa_num_bwd_cube + self.fa_num_bwd_vector

    @property
    def conv_fwd_time(self):
        return self.conv_time_fwd_cube + self.conv_time_fwd_vector

    @property
    def conv_bwd_time(self):
        return self.conv_time_bwd_cube + self.conv_time_bwd_vector

    @property
    def conv_fwd_num(self):
        return self.conv_num_fwd_cube + self.conv_num_fwd_vector

    @property
    def conv_bwd_num(self):
        return self.conv_num_bwd_cube + self.conv_num_bwd_vector

    @property
    def mm_total_time(self):
        return sum((self.matmul_time_cube, self.matmul_time_vector))

    @property
    def mm_total_num(self):
        return sum((self.matmul_num_cube, self.matmul_num_vector))

    @property
    def vector_total_time(self):
        return sum((self.vector_time_trans, self.vector_time_notrans))

    @property
    def vector_total_num(self):
        return sum((self.vector_num_trans, self.vector_num_notrans))

    @property
    def cube_time(self):
        return (
            self.matmul_time_cube + self.matmul_time_vector + self.other_cube_time + self.all_mc2_time
        ) / Constant.MILLISECONDS_TO_SECONDS

    @property
    def vec_time(self):
        return (self.vector_time_trans + self.vector_time_notrans) / Constant.MILLISECONDS_TO_SECONDS

    @property
    def cube_num(self):
        return self.matmul_num_cube + self.matmul_num_vector + self.other_cube_num

    @property
    def vec_num(self):
        return self.vector_num_trans + self.vector_num_notrans

    @property
    def sdma_num(self):
        return self.sdma_num_tensor_move + self.sdma_num_stream

    @property
    def fa_num_fwd(self):
        return self.fa_num_fwd_cube + self.fa_num_fwd_vector

    @property
    def fa_num_bwd(self):
        return self.fa_num_bwd_cube + self.fa_num_bwd_vector

    @property
    def pa_num(self):
        return self.page_attention_num

    @property
    def pa_time(self):
        return self.page_attention_time / Constant.MILLISECONDS_TO_SECONDS

    @property
    def conv_time_fwd(self):
        return (self.conv_time_fwd_cube + self.conv_time_fwd_vector) / Constant.MILLISECONDS_TO_SECONDS

    @property
    def conv_time_bwd(self):
        return (self.conv_time_bwd_cube + self.conv_time_bwd_vector) / Constant.MILLISECONDS_TO_SECONDS

    @property
    def conv_num_fwd(self):
        return self.conv_num_fwd_cube + self.conv_num_fwd_vector

    @property
    def conv_num_bwd(self):
        return self.conv_num_bwd_cube + self.conv_num_bwd_vector

    @property
    def sdma_time(self):
        return (self.sdma_time_tensor_move + self.sdma_time_stream) / Constant.MILLISECONDS_TO_SECONDS

    @property
    def fa_time_fwd(self):
        return (self.fa_time_fwd_cube + self.fa_time_fwd_vector) / Constant.MILLISECONDS_TO_SECONDS

    @property
    def fa_time_bwd(self):
        return (self.fa_time_bwd_cube + self.fa_time_bwd_vector) / Constant.MILLISECONDS_TO_SECONDS

    @property
    def all_mc2_time(self):
        return sum((self.get_mc2_time_by_name(kernel_name) for kernel_name in self.mc2_time_dict))

    def calculate_other_time(self):
        self.other_time = max(
            0,
            (
                self.compute_time_ms
                - self.fa_fwd_time
                - self.fa_bwd_time
                - self.conv_fwd_time
                - self.conv_bwd_time
                - self.mm_total_time
                - self.vector_total_time
                - self.sdma_time_tensor_move
                - self.all_mc2_time
                - self.other_cube_time
                - self.page_attention_time
            )
            / Constant.MILLISECONDS_TO_SECONDS,
        )

    def calculate_schedule_time(self):
        self.scheduling_time = self.e2e_time - self.compute_time - self.lccl_time - self.communication_not_overlapped

    def update_fa_fwd_cube_info(self, time: float):
        self.fa_time_fwd_cube += time
        self.fa_num_fwd_cube += 1

    def update_fa_bwd_cube_info(self, time: float):
        self.fa_time_bwd_cube += time
        self.fa_num_bwd_cube += 1

    def update_fa_fwd_vector_info(self, time: float):
        self.fa_time_fwd_vector += time
        self.fa_num_fwd_vector += 1

    def update_fa_bwd_vector_info(self, time: float):
        self.fa_time_bwd_vector += time
        self.fa_num_bwd_vector += 1

    def update_sdma_tensor_move_info(self, time: float):
        self.sdma_time_tensor_move += time
        self.sdma_num_tensor_move += 1

    def update_sdma_stream_info(self, time: float, num: int = 1):
        self.sdma_time_stream += time
        self.sdma_num_stream += num

    def update_lccl_info(self, time: float):
        self.lccl_time += time
        self.lccl_num += 1

    def update_conv_bwd_cube_info(self, time: float):
        self.conv_time_bwd_cube += time
        self.conv_num_bwd_cube += 1

    def update_conv_fwd_cube_info(self, time: float):
        self.conv_time_fwd_cube += time
        self.conv_num_fwd_cube += 1

    def update_conv_bwd_vector_info(self, time: float):
        self.conv_time_bwd_vector += time
        self.conv_num_bwd_vector += 1

    def update_conv_fwd_vector_info(self, time: float):
        self.conv_time_fwd_vector += time
        self.conv_num_fwd_vector += 1

    def update_matmul_cube_info(self, time: float):
        self.matmul_time_cube += time
        self.matmul_num_cube += 1

    def update_matmul_vector_info(self, time: float):
        self.matmul_time_vector += time
        self.matmul_num_vector += 1

    def update_page_attention_info(self, time: float):
        self.page_attention_time += time
        self.page_attention_num += 1

    def update_vector_trans_info(self, time: float):
        self.vector_time_trans += time
        self.vector_num_trans += 1

    def update_vector_notrans_info(self, time: float):
        self.vector_time_notrans += time
        self.vector_num_notrans += 1

    def update_other_cube_info(self, time: float):
        self.other_cube_time += time
        self.other_cube_num += 1

    def set_compute_time(self, time: float):
        self.compute_time = time

    def update_compute_time(self, time: float):
        self.compute_time += time

    def set_e2e_time(self, time: float):
        self.e2e_time = time

    def set_comm_not_overlap(self, time: float):
        self.communication_not_overlapped = time

    def update_comm_not_overlap(self, time: float):
        self.communication_not_overlapped += time

    def update_communication_group_time(self, time_dict: dict):
        self.communication_group_time = time_dict
        for time in time_dict.values():
            self.wait_time += time.get(Constant.WAIT_TIME, 0)

    def update_communication_overlap_time(self, time_dict: dict):
        self.communication_overlap_time = time_dict

    def update_communication_group_pg_name(self, pg_name_dict: dict):
        self.pg_name_dict = pg_name_dict

    def set_memory_used(self, memory: float):
        self.memory_used = memory

    def is_not_minimal_profiling(self) -> bool:
        return self.profiling_type == Constant.NPU and not self.minimal_profiling

    def set_rdma_bandwidth(self, bandwidth: float):
        self.rdma_bandwidth = bandwidth

    def set_sdma_bandwidth(self, bandwidth: float):
        self.sdma_bandwidth = bandwidth

    def update_mc2_info(self, kernel_name, mc2_time, computing_time, communication_time):
        default_dict = {
            Constant.MC2_TIME: 0,
            Constant.MC2_COMPUTING: 0,
            Constant.MC2_COMMUNICATION: 0,
            Constant.MC2_NUMBER: 0,
        }
        self.mc2_time_dict.setdefault(kernel_name, default_dict)[Constant.MC2_TIME] += mc2_time
        self.mc2_time_dict.setdefault(kernel_name, default_dict)[Constant.MC2_COMPUTING] += computing_time
        self.mc2_time_dict.setdefault(kernel_name, default_dict)[Constant.MC2_COMMUNICATION] += communication_time
        self.mc2_time_dict.setdefault(kernel_name, default_dict)[Constant.MC2_NUMBER] += 1

    def trans_time_to_s(self):
        # 新指标单位为ms
        self.fa_time_fwd_cube /= Constant.MILLISECONDS_TO_SECONDS
        self.fa_time_bwd_cube /= Constant.MILLISECONDS_TO_SECONDS
        self.fa_time_fwd_vector /= Constant.MILLISECONDS_TO_SECONDS
        self.fa_time_bwd_vector /= Constant.MILLISECONDS_TO_SECONDS
        self.conv_time_fwd_cube /= Constant.MILLISECONDS_TO_SECONDS
        self.conv_time_bwd_cube /= Constant.MILLISECONDS_TO_SECONDS
        self.conv_time_fwd_vector /= Constant.MILLISECONDS_TO_SECONDS
        self.conv_time_bwd_vector /= Constant.MILLISECONDS_TO_SECONDS
        self.matmul_time_cube /= Constant.MILLISECONDS_TO_SECONDS
        self.matmul_time_vector /= Constant.MILLISECONDS_TO_SECONDS
        self.vector_time_trans /= Constant.MILLISECONDS_TO_SECONDS
        self.vector_time_notrans /= Constant.MILLISECONDS_TO_SECONDS
        self.sdma_time_tensor_move /= Constant.MILLISECONDS_TO_SECONDS
        self.sdma_time_stream /= Constant.MILLISECONDS_TO_SECONDS
        self.page_attention_time /= Constant.MILLISECONDS_TO_SECONDS
        self.other_cube_time /= Constant.MILLISECONDS_TO_SECONDS
        self.other_time /= Constant.MICROSECONDS_TO_SECONDS
        self.compute_time /= Constant.MICROSECONDS_TO_SECONDS
        self.communication_not_overlapped /= Constant.MICROSECONDS_TO_SECONDS
        self.wait_time /= Constant.MICROSECONDS_TO_SECONDS
        self.e2e_time /= Constant.MICROSECONDS_TO_SECONDS
        self.scheduling_time /= Constant.MICROSECONDS_TO_SECONDS
        self.lccl_time /= Constant.MICROSECONDS_TO_SECONDS

    def get_wait_time_by_group(self, group_name: str):
        return self.communication_group_time.get(group_name, {}).get(Constant.WAIT_TIME, 0) / 10**3

    def get_transmit_time_by_group(self, group_name: str):
        return self.communication_group_time.get(group_name, {}).get(Constant.TRANSMIT_TIME, 0) / 10**3

    def get_communication_time_by_group(self, group_name: str):
        return (
            self.communication_group_time.get(group_name, {}).get(Constant.WAIT_TIME, 0)
            + self.communication_group_time.get(group_name, {}).get(Constant.TRANSMIT_TIME, 0)
        ) / 10**3

    def get_mc2_time_by_name(self, kernel_name: str):
        return self.mc2_time_dict.get(kernel_name, {}).get(Constant.MC2_TIME, 0) / 10**3

    def get_mc2_computing_time_by_name(self, kernel_name: str):
        return self.mc2_time_dict.get(kernel_name, {}).get(Constant.MC2_COMPUTING, 0) / 10**3

    def get_mc2_communication_time_by_name(self, kernel_name: str):
        return self.mc2_time_dict.get(kernel_name, {}).get(Constant.MC2_COMMUNICATION, 0) / 10**3

    def get_mc2_number_by_name(self, kernel_name: str):
        return self.mc2_time_dict.get(kernel_name, {}).get(Constant.MC2_NUMBER, 0)

    def get_pg_name_by_group(self, group: str):
        return self.pg_name_dict.get(group, Constant.UNKNOWN)
