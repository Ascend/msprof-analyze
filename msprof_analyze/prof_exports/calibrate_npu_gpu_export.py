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
