# Copyright (c) 2023, Huawei Technologies Co., Ltd.
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
import functools
from typing import Dict
import logging

from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import Constant
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import CoreType
from msprof_analyze.advisor.advisor_backend.common_func_advisor.constant import PerfColor

logger = logging.getLogger()


class OpPerfFactory:
    @classmethod
    def build(cls, op_row: Dict):
        if op_row.get(Constant.TITLE.TASK_TYPE) == CoreType.AIV:
            return VecOpPerf(op_row)
        elif op_row.get(Constant.TITLE.TASK_TYPE) == CoreType.AIC:
            return CubeOpPerf(op_row)
        else:
            return OpPerf(op_row)


class OpPerf:
    def __init__(self, op_row: Dict):
        if "OP Type" in op_row.keys():
            Constant.update_title()
        if "Block Num" in op_row.keys():
            self.block_num = op_row.get("Block Num")
            self.mix_block_dim = op_row.get("Mix Block Num")
        else:
            self.block_num = op_row.get("Block Dim")
            self.mix_block_dim = op_row.get("Mix Block Dim")
        self.row = op_row
        self.model_name = op_row.get("Model Name")
        self.model_id = op_row.get("Model ID")
        self.task_id = op_row.get("Task ID")
        self.stream_id = op_row.get("Stream ID")
        self.infer_id = op_row.get("Infer ID")
        self.op_name = op_row.get("Name")
        self.op_type = op_row.get("Type")
        self.task_type = op_row.get("Accelerator Core")
        self.task_start_time = op_row.get("Start Time(us)")
        self.task_duration = op_row.get("Duration(us)")
        self.task_wait_time = op_row.get("Wait Time(us)")
        self.hf32_eligible = op_row.get("HF32 Eligible")
        self.input_shapes = op_row.get("Input Shapes")
        self.input_data_types = op_row.get("Input Data Types")
        self.input_formats = op_row.get("Input Formats")
        self.output_shapes = op_row.get("Output Shapes")
        self.output_data_types = op_row.get("Output Data Types")
        self.output_formats = op_row.get("Output Formats")
        self.context_id = op_row.get("Context ID")
        self.aicore_time = op_row.get("aicore_time(us)")
        self.aic_total_cycles = op_row.get("aic_total_cycles")

        self.aic_mac_time = op_row.get("aic_mac_time(us)")
        self.aic_mac_ratio = op_row.get("aic_mac_ratio")
        self.aic_scalar_time = op_row.get("aic_scalar_time(us)")
        self.aic_scalar_ratio = op_row.get("aic_scalar_ratio")
        self.aic_mte1_time = op_row.get("aic_mte1_time(us)")
        self.aic_mte1_ratio = op_row.get("aic_mte1_ratio")
        self.aic_mte2_time = op_row.get("aic_mte2_time(us)")
        self.aic_mte2_ratio = op_row.get("aic_mte2_ratio")
        self.aic_fixpipe_time = op_row.get("aic_fixpipe_time(us)")
        self.aic_fixpipe_ratio = op_row.get("aic_fixpipe_ratio")
        self.aic_icache_miss_rate = op_row.get("aic_icache_miss_rate")
        self.aiv_time = op_row.get("aiv_time(us)")
        self.aiv_total_cycles = op_row.get("aiv_total_cycles")
        self.aiv_vec_time = op_row.get("aiv_vec_time(us)")
        self.aiv_vec_ratio = op_row.get("aiv_vec_ratio")
        self.aiv_scalar_time = op_row.get("aiv_scalar_time(us)")
        self.aiv_scalar_ratio = op_row.get("aiv_scalar_ratio")
        self.aiv_mte2_time = op_row.get("aiv_mte2_time(us)")

        self.aiv_mte2_ratio = op_row.get("aiv_mte2_ratio")
        self.aiv_mte3_time = op_row.get("aiv_mte3_time(us)")
        self.aiv_mte3_ratio = op_row.get("aiv_mte3_ratio")
        self.aiv_icache_miss_rate = op_row.get("aiv_icache_miss_rate")
        self.cube_utilization = op_row.get("cube_utilization( %)")
    
    @staticmethod
    def get_dtype_size(dtype_str: str):
        return Constant.DTYPE_SIZE_MAP.get(dtype_str.lower(), 0)
    
    @staticmethod
    def get_element_count(shape: list):
        return functools.reduce(lambda x, y: int(x) * int(y), shape)
    
    @staticmethod
    def shape_to_tuple(shape_str: str) -> tuple:
        if not isinstance(shape_str, str):
            return []
        shape_str = shape_str.strip('"')
        split_shape = shape_str.strip(';')
        if not split_shape:
            return []
        pairs = split_shape.split(';')
        shape_result = []
        for pair in pairs:
            pair = pair.strip(";")
            elements = pair.split(',')
            elements = tuple(int(element) if "" != element else 0 for element in elements)
            shape_result.append(elements)
        return tuple(shape_result)
    
    @staticmethod
    def dtype_to_tuple(dtypes_str: str) -> tuple:
        if not isinstance(dtypes_str, str):
            return []
        dtypes_str = dtypes_str.strip('"')
        split_dtypes = dtypes_str.strip(';')
        if not split_dtypes:
            return []
        pairs = split_dtypes.split(';')
        return tuple(pairs)
    
    def get_mac_ratio(self):
        return self.aic_mac_ratio
    
    def get_size(self, shapes_str, dtypes_str):
        shapes = self.shape_to_tuple(shapes_str)
        dtypes = self.dtype_to_tuple(dtypes_str)
        if len(shapes) > len(dtypes):
            logger.error("The size of shape is greater than that of dtypes.")
            return 0
        if len(shapes) < len(dtypes):
            shapes = list(shapes)
            shapes.extend([(1,)] * (len(dtypes) - len(shapes)))
        all_size = 0
        for index, shape in enumerate(shapes):
            element_count = self.get_element_count(shape)
            dtype_size = self.get_dtype_size(dtypes[index])
            all_size += element_count * dtype_size
        return all_size
    
    def get_calc_size(self):
        # input and output bytes (MB)
        if not self.input_shapes or not self.output_shapes:
            logger.error("There is no tensor data, do not assess vector op performance.")
            return 0
        intput_size = self.get_size(self.input_shapes, self.input_data_types)
        output_size = self.get_size(self.output_shapes, self.output_data_types)
        return (intput_size + output_size) / (Constant.BYTE_UNIT_TRANS * Constant.BYTE_UNIT_TRANS)
    
    def get_throughput(self):
        # throughput bytes (GB/s)
        if not self.task_duration or abs(self.task_duration) < 1e-6:
            logger.error("There is no task_duration, do not assess vector op performance.")
            return 0
        return (self.row[Constant.TITLE.SIZE] /
                Constant.BYTE_UNIT_TRANS / self.task_duration * Constant.UNIT_TRANS * Constant.UNIT_TRANS)
    
    def get_perf_color(self):
        row = self.row
        return PerfColor.WHITE

    def update(self):
        self.row[Constant.TITLE.SIZE] = self.get_calc_size()
        self.row[Constant.TITLE.THROUGHPUT] = self.get_throughput()
        self.row[Constant.TITLE.COLOR] = self.get_perf_color().name
        return self.row


class VecOpPerf(OpPerf):
    def get_perf_color(self) -> PerfColor:
        throughput = self.row[Constant.TITLE.THROUGHPUT]
        op_duration = self.task_duration
        tp_threshold = Constant.TP_THRESHOLD
        if throughput == 0:
            return PerfColor.WHITE
        if throughput < tp_threshold / 2 and op_duration > 20:
            return PerfColor.RED
        elif tp_threshold / 2 <= throughput < tp_threshold:
            return PerfColor.YELLOW
        else:
            return PerfColor.GREEN


class CubeOpPerf(OpPerf):
    def get_perf_color(self) -> PerfColor:
        aic_mac_ratio = self.get_mac_ratio()
        if not aic_mac_ratio:
            logger.warning("There is no aic_mac_ratio, do not assess cube op performance.")
            return PerfColor.WHITE
        elif aic_mac_ratio < 0.6:
            return PerfColor.RED
        elif 0.6 <= aic_mac_ratio < 0.8:
            return PerfColor.YELLOW
        else:
            return PerfColor.GREEN
