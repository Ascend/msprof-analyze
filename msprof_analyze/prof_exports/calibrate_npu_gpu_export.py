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

from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport


logger = get_logger()


QUERY_GPU_NVTX_EVENTS = """
    SELECT
        n.start AS start_ns,
        n.end AS end_ns,
        n.globalTid AS thread_id,
        COALESCE(n.text, s.value, 'Unknown_Region') as name
    FROM
        NVTX_EVENTS AS n
    LEFT JOIN
        StringIds AS s ON n.textId = s.id
    WHERE
        n.eventType = 59
    ORDER BY n.start
    """

QUERY_GPU_KERNELS = """
    SELECT
        r.start AS cpu_start_ns,
        r.globalTid AS thread_id,
        k.start AS gpu_start_ns,
        k.end - k.start AS gpu_duration_ns,
        s.value AS kernel_name,
        k.deviceId AS rank_id
    FROM
        CUPTI_ACTIVITY_KIND_RUNTIME AS r
    JOIN 
        CUPTI_ACTIVITY_KIND_KERNEL AS k ON r.correlationId = k.correlationId
    LEFT JOIN
        StringIds AS s ON k.demangledName = s.id
    """


class GPUNVTXEventsExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, param_dict=None)
        self._query = QUERY_GPU_NVTX_EVENTS

    def get_param_order(self):
        return []


class GPUKernelExport(BaseStatsExport):
    def __init__(self, db_path, recipe_name):
        super().__init__(db_path, recipe_name, param_dict=None)
        self._query = QUERY_GPU_KERNELS

    def get_param_order(self):
        return []
