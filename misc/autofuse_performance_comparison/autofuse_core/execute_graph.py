# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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
# ruff: noqa: E402
import importlib
import numpy as np
import os
import sys
import acl
import mstx
from ge.ge_global import GeApi

so_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib64")
sys.path.append(os.path.realpath(so_path))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from misc.autofuse_performance_comparison.utils.utils import parse_args
from misc.autofuse_performance_comparison.utils.constant import STRING_TO_DTYPE
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


def acl_check(ret: int, msg: str) -> bool:
    if ret != 0:
        logger.error("%s, ret = %s", msg, ret)
        return False
    return True


class ACLContextManager:
    def __init__(self, device_id=0):
        self.device_id = device_id
        self.context = None
        self.stream = None

    def __enter__(self):
        _ = acl_check(acl.init(), "acl init failed")
        _ = acl_check(acl.rt.set_device(self.device_id), "set device failed")
        self.context, ret = acl.rt.create_context(self.device_id)
        _ = acl_check(ret, "create context failed")
        self.stream, ret = acl.rt.ctx_get_current_default_stream()
        _ = acl_check(ret, "get default stream failed")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            _ = acl_check(acl.rt.destroy_context(self.context), "destroy context failed")
        _ = acl_check(acl.rt.reset_device(self.device_id), "reset device failed")
        _ = acl_check(acl.finalize(), "finalize acl failed")


class GEContextManager:
    def __init__(self, config: dict):
        self.config = config

    def __enter__(self):
        _ = acl_check(GeApi.ge_initialize(self.config), "GE initialize failed")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _ = acl_check(GeApi.ge_finalize(), "GE finalize failed")


class Autofuse:
    MSTX_MESSAGE = "autofuse"

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
        graphs = data.get("graph", [])
        max_ops_num = 0
        max_idx = 0
        for i, g in enumerate(graphs):
            cnt = len(g.get("op", []))
            if cnt > max_ops_num:
                max_ops_num = cnt
                max_idx = i
        return graphs[max_idx].get("op", []) if graphs else []

    def extract_value(self, op):
        op_name = op.get("name")
        self.fused_ops[op_name] = {
            "inputs_shape": [],
            "inputs_dtype": [],
            "inputs_data_path": [],
            "outputs_data_path": [],
        }
        for desc in op.get("input_desc", []):
            shape = desc.get("shape", {}).get("dim", [])
            dtype = desc.get("dtype")
            if shape or dtype is not None:
                self.fused_ops[op_name]["inputs_shape"].append(shape)
                self.fused_ops[op_name]["inputs_dtype"].append(STRING_TO_DTYPE[dtype])

    def get_dump_data(self):
        for file in os.listdir(self.dump_path):
            if not file.endswith(".npy"):
                continue
            parts = file.split(".")
            if len(parts) < 5:
                continue
            op_name, arg_type = parts[1], parts[-3]
            if op_name not in self.fused_ops:
                continue
            path = os.path.join(self.dump_path, file)
            if arg_type == "input":
                self.fused_ops[op_name]["inputs_data_path"].append(path)
            elif arg_type == "output":
                self.fused_ops[op_name]["outputs_data_path"].append(path)

    def execute_graph(self, graph_path, inputs_data, inputs_shape, inputs_dtype, outputs_data):
        self.module.execute_graph(graph_path, inputs_data, inputs_shape, inputs_dtype, outputs_data)

    def run_single_op(self, op_name, op_data, acl_mgr):
        subgraph = os.path.join(self.subgraph_dir, f"{op_name}_origin_subgraph.air")
        if not os.path.exists(subgraph):
            logger.warning("subgraph not exists: %s", op_name)
            return
        # load data
        inputs = [np.load(p) for p in op_data["inputs_data_path"]]
        outputs = [np.load(p) for p in op_data["outputs_data_path"]]
        if not inputs or not outputs:
            logger.error("input/output missing for %s", op_name)
            return
        if len(inputs) != len(op_data["inputs_shape"]):
            logger.error("shape mismatch for %s", op_name)
            return
        # mstx
        range_id = mstx.range_start(f"autofuse_{op_name}", acl_mgr.stream)
        try:
            self.execute_graph(subgraph, inputs, op_data["inputs_shape"], op_data["inputs_dtype"], outputs)
        except Exception as e:
            logger.error("execute %s failed: %s", op_name, e)
        finally:
            acl.rt.set_context(acl_mgr.context)
            mstx.range_end(range_id)

    def run(self):
        for op in self.get_ops(self.whole_graph):
            self.extract_value(op)
        self.get_dump_data()
        device_id = 0
        ge_config = {"ge.execDeviceId": str(device_id), "ge.graphRunMode": "0"}
        with GEContextManager(ge_config), ACLContextManager(device_id) as acl_mgr:
            for op_name, op_data in self.fused_ops.items():
                self.run_single_op(op_name, op_data, acl_mgr)


if __name__ == "__main__":
    args = parse_args()
    try:
        Autofuse(args).run()
    except Exception as err:
        logger.error(err, exc_info=True)
