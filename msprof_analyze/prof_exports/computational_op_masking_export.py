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
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class CommunicationOpWithExport(BaseStatsExport):
    QUERY = """
    SELECT
        COMMUNICATION_OP.startNs,
        COMMUNICATION_OP.endNs,
        COMMUNICATION_OP.count,
        D.group_name AS parallelType,
        S_op.value AS opType,
        DT.name AS dataType
    FROM COMMUNICATION_OP
    LEFT JOIN STRING_IDS AS S_group ON COMMUNICATION_OP.groupName = S_group.id
    LEFT JOIN STRING_IDS AS S_op ON COMMUNICATION_OP.opType = S_op.id
    LEFT JOIN ENUM_HCCL_DATA_TYPE AS DT ON COMMUNICATION_OP.dataType = DT.id
    LEFT JOIN (
        SELECT
            j.key,
            json_extract(j.value, '$.group_name') AS group_name
        FROM META_DATA,
            json_each(META_DATA.value) AS j
        WHERE META_DATA.name = "parallel_group_info"
    ) AS D ON S_group.value = D.key;
    """

    FILTER_QUERY = """
    SELECT
        COMMUNICATION_OP.startNs,
        COMMUNICATION_OP.endNs,
        COMMUNICATION_OP.count,
        D.group_name AS parallelType,
        S_op.value AS opType,
        DT.name AS dataType
    FROM COMMUNICATION_OP
    LEFT JOIN STRING_IDS AS S_group ON COMMUNICATION_OP.groupName = S_group.id
    LEFT JOIN STRING_IDS AS S_op ON COMMUNICATION_OP.opType = S_op.id
    LEFT JOIN ENUM_HCCL_DATA_TYPE AS DT ON COMMUNICATION_OP.dataType = DT.id
    LEFT JOIN (
        SELECT
            j.key,
            json_extract(j.value, '$.group_name') AS group_name
        FROM META_DATA,
            json_each(META_DATA.value) AS j
        WHERE META_DATA.name = "parallel_group_info"
    ) AS D ON S_group.value = D.key
    {};
    """

    def __init__(self, db_path, recipe_name, step_range):
        # 1. 将 step_range 转换为 param_dict
        param_dict = None
        if step_range:
            # 假设 step_range 是字典，包含 startNs 和 endNs
            if isinstance(step_range, dict):
                param_dict = {'startNs': step_range.get('startNs'), 'endNs': step_range.get('endNs')}
                # 移除 None 值
                param_dict = {k: v for k, v in param_dict.items() if v is not None}
                if not param_dict:
                    param_dict = None
            else:
                # 如果 step_range 是其他格式，尝试转换
                logger.warning("step_range type %s not supported, treating as None", type(step_range))
                param_dict = None

        # 2. 调用父类初始化（传入 param_dict）
        super().__init__(db_path, recipe_name, param_dict)

        # 3. 构建查询语句
        has_params = param_dict and param_dict.get('startNs') is not None
        if has_params:
            filter_statement = "WHERE COMMUNICATION_OP.startNs >= ? AND COMMUNICATION_OP.endNs <= ? "
            self._query = self.FILTER_QUERY.format(filter_statement)
        else:
            self._query = self.QUERY

    def get_param_order(self):
        """
        实现抽象方法：返回 SQL 查询参数顺序

        Returns:
            list: 参数名称列表，按 SQL 中 ? 占位符的顺序
        """
        # 如果有参数，返回对应的参数名称
        if self._param_dict and self._param_dict.get('startNs') is not None:
            return ['startNs', 'endNs']
        return []


class ComputeTaskInfoWithExport(BaseStatsExport):
    QUERY = """
    WITH compute_info AS (
        SELECT
            (SELECT value FROM STRING_IDS WHERE id = t.name) AS op_name,
            t.globalTaskId,
            (SELECT value FROM STRING_IDS WHERE id = t.opType) AS op_type,
            (SELECT value FROM STRING_IDS WHERE id = t.taskType) AS task_type
        FROM
            COMPUTE_TASK_INFO t
    )
    SELECT
        compute_info.*,
        task.startNs as task_start_time,
        task.endNs as task_end_time,
        task.endNs - task.startNs as task_duration
    FROM
        compute_info
    JOIN
        TASK as task ON compute_info.globalTaskId = task.globalTaskId
    {};
    """

    def __init__(self, db_path, recipe_name, step_range):
        # 转换 step_range 为 param_dict
        param_dict = None
        if step_range and isinstance(step_range, dict):
            param_dict = {'startNs': step_range.get('startNs'), 'endNs': step_range.get('endNs')}
            param_dict = {k: v for k, v in param_dict.items() if v is not None}
            if not param_dict:
                param_dict = None

        super().__init__(db_path, recipe_name, param_dict)

        has_params = param_dict and param_dict.get('startNs') is not None
        if has_params:
            filter_statement = "WHERE task.startNs >= ? AND task.endNs <= ?"
            self._query = self.QUERY.format(filter_statement)
        else:
            self._query = self.QUERY.format("")

    def get_param_order(self):
        if self._param_dict and self._param_dict.get('startNs') is not None:
            return ['startNs', 'endNs']
        return []


class ParallelGroupInfoExport(BaseStatsExport):
    QUERY = """
    WITH parsed AS (
        SELECT
            j.key,
            json_extract(META_DATA.value, '$.' || j.key || '.group_name') AS group_name,
            json_extract(META_DATA.value, '$.' || j.key || '.global_ranks') AS global_ranks
        FROM META_DATA,
            json_each(META_DATA.value) AS j
        WHERE META_DATA.name = "parallel_group_info"
    )
    SELECT
        group_name,
        global_ranks,
        json_array_length(global_ranks) AS rank_count
    FROM parsed
    """

    def __init__(self, db_path, recipe_name, step_range):
        # ParallelGroupInfoExport 不需要参数过滤
        super().__init__(db_path, recipe_name, None)  # param_dict = None
        self._query = self.QUERY

    def get_param_order(self):
        """ParallelGroupInfoExport 不需要查询参数"""
        return []
