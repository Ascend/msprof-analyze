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
from msprof_analyze.compare_tools.compare_backend.utils.module_node import ModuleNode
from msprof_analyze.compare_tools.compare_backend.utils.torch_op_node import TorchOpNode


class NameFunction:
    def __init__(self, args: any):
        self.args = args

    @classmethod
    def get_name(cls, op_node: TorchOpNode) -> str:
        return op_node.name

    @classmethod
    def get_full_name(cls, op_node: TorchOpNode) -> str:
        if isinstance(op_node.origin_input_shape, list):
            data = []
            for dim in op_node.origin_input_shape:
                data.append(','.join([str(x) for x in dim]))
            input_shape = ';\r\n'.join(data)
            return f'{op_node.name}{input_shape}'
        return f'{op_node.name}{op_node.input_shape}'

    def get_name_func(self):
        if not self.args.op_name_map and not self.args.use_input_shape:
            name_func = self.get_name
        elif self.args.op_name_map and not self.args.use_input_shape:
            name_func = self.get_map_name
        elif self.args.op_name_map and not self.args.use_input_shape:
            name_func = self.get_full_name
        else:
            name_func = self.get_full_map_name
        return name_func

    def get_map_name(self, op_node: TorchOpNode) -> str:
        return self.args.op_name_map.get(op_node.name, op_node.name)

    def get_full_map_name(self, op_node: TorchOpNode) -> str:
        if isinstance(op_node.origin_input_shape, list):
            data = []
            for dim in op_node.origin_input_shape:
                data.append(','.join([str(x) for x in dim]))
            input_shape = ';\r\n'.join(data)
            return f'{self.args.op_name_map.get(op_node.name, op_node.name)}{input_shape}'
        return f'{self.args.op_name_map.get(op_node.name, op_node.name)}{op_node.input_shape}'

    def get_module_name(self, module: ModuleNode) -> str:
        if not self.args.op_name_map:
            return module.module_name
        module = module.module_name
        for old_name, new_name in self.args.op_name_map.items():
            module.replace(old_name, new_name)
        return module
