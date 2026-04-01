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
import importlib
import numpy as np
import os
import sys
import torch
import torch_npu

so_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib64")
sys.path.append(os.path.realpath(so_path))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from misc.autofuse_performance_comparison.utils.utils import parse_args
from misc.autofuse_performance_comparison.utils.constant import STRING_TO_DTYPE
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class Autofuse:
    DOMAIN = "autofuse"
    def __init__(self, params):
        self.module = importlib.import_module("ExecuteGraph_C")
        self.whole_graph = params.whole_graph
        self.subgraph_dir = params.subgraph_dir
        self.dump_path = params.dump_path
        self.output_path = params.output_path
        self.fused_ops = {}

    @staticmethod
    def get_ops(json_path):
        data = FileManager.read_json_file(json_path)
        graphs = data["graph"]
        len_ops_list = []
        max_ops_graph_index = 0
        max_ops_num = 0
        for i in range(len(graphs)):
            graph = graphs[i]
            len_ops = len(graph["op"])
            len_ops_list.append(len_ops)
            if len_ops > max_ops_num:
                max_ops_num = len_ops
                max_ops_graph_index = i
        return graphs[max_ops_graph_index]["op"] if graphs else []

    def extract_value(self, op):
        op_name = op.get("name")
        self.fused_ops[op_name] = {
            "inputs_shape": [],
            "inputs_dtype": [],
            "inputs_data_path": [],
            "outputs_data_path": [],
        }
        for input_data in op.get("input_desc", []):
            input_shape = input_data.get("shape", {}).get("dim", [])
            input_dtype = input_data.get("dtype")
            if not input_shape and input_dtype is None:
                continue
            self.fused_ops[op_name]["inputs_shape"].append(input_shape)
            self.fused_ops[op_name]["inputs_dtype"].append(STRING_TO_DTYPE[input_dtype])

    def get_dump_data(self):
        for file in os.listdir(self.dump_path):
            if not file.endswith(".npy"):
                continue
            parts = file.split(".")
            if len (parts) < 5:
                continue
            op_name = parts[1]
            arg_type = parts[-3]
            if op_name not in self.fused_ops:
                continue
            file_path = os.path.join(self.dump_path, file)
            if arg_type == "input":
                self.fused_ops[op_name]["inputs_data_path"].append(file_path)
            elif arg_type == "output":
                self.fused_ops[op_name]["outputs_data_path"].append(file_path)
            else:
                logger.warning(f"Unknown arg_type '{arg_type}'")
                continue

    def get_prof_config(self):
        experimental_config = torch_npu.profiler._ExperimentalConfig(
            export_type=[
                torch_npu.profiler.ExportType.Db
            ],
            profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
            aic_metrics=torch_npu.profiler.AiCMetrics.PipeUtilization,
            mstx_domain_include=[self.DOMAIN],
            mstx=True,
        )
        prof = torch_npu.profiler.profile(
            activities=[
                torch_npu.profiler.ProfilerActivity.NPU
            ],
            on_trace_ready=torch_npu.profiler.tensorboard_trace_handler(self.output_path),
            experimental_config=experimental_config)
        return prof

    def execute_graph(self, graph_path, inputs_data, inputs_shape, inputs_dtype, outputs_data):
        self.module.execute_graph(graph_path, inputs_data, inputs_shape, inputs_dtype, outputs_data)

    def run(self):
        ops = self.get_ops(self.whole_graph)
        for op in ops:
            self.extract_value(op)
        self.get_dump_data()
        prof = self.get_prof_config()
        stream = torch_npu.npu.current_stream()
        prof.start()
        for op_name, op_data in self.fused_ops.items():
            subgraph = os.path.join( self.subgraph_dir, f"{op_name}.txt")
            if not os.path.exists(subgraph):
                logger.warning(f"The subgraph file for fused op '{op_name}' not exists")
                continue
            inputs_data = [np.load(file) for file in op_data["inputs_data_path"]]
            outputs_data = [np.load(file) for file in op_data["outputs_data_path"]]
            if not inputs_data:
                logger.error(f"No input .npy files found for fused op '{op_name}' in '{self.dump_path}'")
                continue
            if not outputs_data:
                logger.error(f"No output .npy files found for fused op '{op_name}' in '{self.dump_path}'")
                continue
            if len(inputs_data) != len(op_data["inputs_shape"]):
                logger.error(f"The number of input data does not match the number of "
                             f"input shapes for fused op '{op_name}'")
                continue
            range_id = torch_npu.npu.mstx.range_start(op_name, stream, domain=self.DOMAIN)
            try:
                self.execute_graph(subgraph, inputs_data, op_data["inputs_shape"],
                                   op_data["inputs_dtype"], outputs_data)
            except Exception as e:
                logger.error(f"Execute graph failed for fused op '{op_name}': {e}")
            torch_npu.npu.mstx.range_end(range_id, domain=self.DOMAIN)
        prof.stop()


if __name__ == "__main__":
    args = parse_args()
    try:
        Autofuse(args).run()
    except Exception as err:
        logger.error(err, exc_info=True)
