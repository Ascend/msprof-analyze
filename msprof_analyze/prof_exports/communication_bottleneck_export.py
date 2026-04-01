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

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport

QUERY_BASIC_COMMUNICATION_OP_SQL = '''
    SELECT 
        COMMUNICATION_OP.startNs as "start_ns",
        COMMUNICATION_OP.endNs as "end_ns",
        COMMUNICATION_OP.endNs - COMMUNICATION_OP.startNs as "duration",
        STRING_IDS.value as "comm_name"
    FROM COMMUNICATION_OP
    JOIN STRING_IDS on STRING_IDS.id = COMMUNICATION_OP.opName
    WHERE COMMUNICATION_OP.startNs >= ? AND COMMUNICATION_OP.endNs <= ?
    ORDER BY "duration" DESC
'''

class CommunicationOpExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_BASIC_COMMUNICATION_OP_SQL

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]



QUERY_TARGET_COMMUNICATION_OP_WITH_NAME_SQL = '''
    SELECT 
        COMMUNICATION_OP.startNs as "start_ns", 
        COMMUNICATION_OP.endNs as "end_ns", 
        COMMUNICATION_OP.endNs - COMMUNICATION_OP.startNs AS "duration", 
        STRING_IDS.value as "comm_name"
    FROM COMMUNICATION_OP
    JOIN STRING_IDS ON COMMUNICATION_OP.opName = STRING_IDS.id 
    WHERE STRING_IDS.value = ?
    GROUP BY STRING_IDS.value
'''


class TargetCommunicationOpWithNameExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_TARGET_COMMUNICATION_OP_WITH_NAME_SQL

    def get_param_order(self):
        return ["comm_op_name"]



QUERY_ALL_DEVICE_NODE_LAUNCH_PYTORCH_TASK_SQL = '''
    SELECT 
        TASK.connectionId as "connection_id", 
        TASK.startNs as "device_start_ns", 
        TASK.endNs as "device_end_ns", 
        CANN_API.startNs as "cann_start_ns", 
        CANN_API.endNs as "cann_end_ns", 
        PYTORCH_API.startNs as "pytorch_start_ns", 
        PYTORCH_API.endNs as "pytorch_end_ns"
    FROM TASK
    JOIN CANN_API ON TASK.connectionId = CANN_API.connectionId
    JOIN CONNECTION_IDS ON CONNECTION_IDS.connectionId = TASK.connectionId
    JOIN PYTORCH_API ON CONNECTION_IDS.id = PYTORCH_API.connectionId
    JOIN ENUM_API_TYPE ON CANN_API.type = ENUM_API_TYPE.id
    JOIN STRING_IDS on STRING_IDS.id = CANN_API.name
    WHERE TASK.startNs > ? AND TASK.endNs < ? AND ENUM_API_TYPE.name = 'node' AND STRING_IDS.value = 'launch'
    ORDER BY TASK.startNs DESC
'''


class AllDeviceNodeLaunchPytorchTaskExport(BaseStatsExport):

    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_ALL_DEVICE_NODE_LAUNCH_PYTORCH_TASK_SQL

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


QUERY_COMPUTE_TASK_SQL = '''
    SELECT 
        TASK.startNs as "start_ns", 
        TASK.endNs as "end_ns", 
        (TASK.endNs - TASK.startNs) as "duration", 
        STRING_IDS.value as "task_name"
    FROM TASK
    JOIN COMPUTE_TASK_INFO ON TASK.globalTaskId = COMPUTE_TASK_INFO.globalTaskId
    JOIN STRING_IDS ON COMPUTE_TASK_INFO.name = STRING_IDS.id
    WHERE TASK.startNs >= ? AND TASK.endNs <= ?
    ORDER BY "start_ns" DESC
'''


class ComputeTaskExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_COMPUTE_TASK_SQL

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


QUERY_COMMUNICATION_TASK_SQL = '''
    SELECT 
        MIN(TASK.startNs) as "start_ns", 
        MAX(TASK.endNs) as "end_ns", 
        MAX(TASK.endNs) - MIN(TASK.startNs) as "duration",  
        STRING_IDS.value as "task_name"
    FROM TASK
    JOIN COMMUNICATION_TASK_INFO ON TASK.globalTaskId = COMMUNICATION_TASK_INFO.globalTaskId
    JOIN STRING_IDS ON COMMUNICATION_TASK_INFO.name = STRING_IDS.id
    WHERE TASK.startNs >= ? AND TASK.endNs <= ?
    GROUP BY STRING_IDS.value
    ORDER BY "start_ns" DESC
'''


class CommunicationTaskExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_COMMUNICATION_TASK_SQL

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


QUERY_MEMORY_DEVICE_TASK_SQL = '''
    SELECT 
        TASK.startNs as "start_ns", 
        TASK.endNs as "end_ns", 
        (TASK.endNs - TASK.startNs) as "duration", 
        STRING_IDS.value as "task_name"
    FROM TASK
    JOIN STRING_IDS ON TASK.taskType = STRING_IDS.id
    WHERE TASK.startNs >= ? AND TASK.endNs <= ? and LOWER(STRING_IDS.value) LIKE LOWER('%memcpy%') 
    ORDER BY TASK.startNs DESC
'''

class DeviceMemoryTaskExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_MEMORY_DEVICE_TASK_SQL

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


QUERY_BEFORE_TIME_PYTORCH_TASK_SQL = '''
    SELECT 
        PYTORCH_API.startNs as "start_ns", 
        PYTORCH_API.endNs as "end_ns",
        PYTORCH_API.endNs - PYTORCH_API.startNs as "duration", 
        STRING_IDS.value as "task_name"
    FROM PYTORCH_API
    JOIN STRING_IDS ON STRING_IDS.id = PYTORCH_API.name
    WHERE PYTORCH_API.startNs >= ? and PYTORCH_API.endNs <= ? and STRING_IDS.value LIKE '%::%'
    ORDER BY PYTORCH_API.startNs DESC
'''


class PytorchTaskExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_BEFORE_TIME_PYTORCH_TASK_SQL

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]


QUERY_CANN_TASK_SQL = '''
    SELECT 
        CANN_API.startNs as "start_ns", 
        CANN_API.endNs as "end_ns", 
        CANN_API.endNs - CANN_API.startNs as "duration", 
        ENUM_API_TYPE.name || '@' || STRING_IDS.value as "task_name"
    FROM CANN_API
    JOIN STRING_IDS ON STRING_IDS.id = CANN_API.name
    JOIN ENUM_API_TYPE on ENUM_API_TYPE.id = CANN_API.type
    WHERE CANN_API.startNs >= ? AND CANN_API.endNs <= ?
    ORDER BY CANN_API.startNs DESC
'''


class CannTaskExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name, param_dict):
        super().__init__(db_path, recipe_name, param_dict)
        self._query = QUERY_CANN_TASK_SQL

    def get_param_order(self):
        return [Constant.START_NS, Constant.END_NS]



