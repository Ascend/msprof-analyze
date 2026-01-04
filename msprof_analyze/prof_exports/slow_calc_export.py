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

from token import NAME
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
from msprof_analyze.prof_common.constant import Constant


list_op_analysis = ["MatMulV3", "MatMulV2"]
values_str = ", ".join([f"'{i}'" for i in list_op_analysis])

SIMPLE_QUERY = f"""
    select
        COMPUTE_TASK_INFO.name as "opName",
        COMPUTE_TASK_INFO.opType as "opType",
        inputShapes,
        outputShapes,
        endNs - startNs as {Constant.DURATION_TIME},
        deviceId
    from TASK
    left join
        COMPUTE_TASK_INFO
        on COMPUTE_TASK_INFO.globalTaskId = TASK.globalTaskId
    inner join STRING_IDS
            on STRING_IDS.id = COMPUTE_TASK_INFO.opType
    where STRING_IDS.value in ({values_str})
"""


class SlowCalcExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, {})
        self._query = SIMPLE_QUERY
