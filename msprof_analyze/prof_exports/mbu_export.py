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

from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
from msprof_analyze.prof_exports.mfu_export import QUERY_KERNEL_SHAPES_TEMPLATE
from msprof_analyze.prof_common.constant import Constant


# Issue #29 限定 Matmul / FlashAttention / GroupedMatmul 三类算子。
# 新增已验证的 Device opType 时更新此清单及中英文支持列表；SQL 和计算层共同使用。
TARGET_OP_TYPES = ("MatMulV2", "MatMulV3", "FlashAttentionScore", "GroupedMatmul", "GroupedMatMul")
OP_TYPE_PARAMS = tuple(f"op_type_{index}" for index in range(len(TARGET_OP_TYPES)))

QUERY_KERNEL_BYTES = QUERY_KERNEL_SHAPES_TEMPLATE.format(
    extra_columns=",\n            (SELECT value FROM STRING_IDS WHERE id = t.outputDataTypes) AS output_types",
    where_clause=(
        "WHERE task.startNs >= ? AND task.startNs <= ? "
        f"AND compute_info.type IN ({', '.join('?' for _ in TARGET_OP_TYPES)})"
    ),
)


class KernelBytesExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, step_range=None):
        params = {Constant.START_NS: 0, Constant.END_NS: Constant.MAX_INTEGER}
        if step_range is not None:
            params.update(step_range)
        params.update(zip(OP_TYPE_PARAMS, TARGET_OP_TYPES))
        super().__init__(db_path, recipe_name, param_dict=params)
        self._query = QUERY_KERNEL_BYTES

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS, *OP_TYPE_PARAMS]
