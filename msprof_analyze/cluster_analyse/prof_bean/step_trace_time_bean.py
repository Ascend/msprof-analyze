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
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class StepTraceTimeBean:
    STEP = "Step"
    COMPLEMENT_HEADER = ["Step", "Type", "Index"]
    EXCLUDE_HEADER = ["Step", "Device_id"]

    def __init__(self, data: list):
        self._data = data

    @property
    def row(self) -> list:
        row = []
        for field_name in self._data.keys():
            if field_name in self.EXCLUDE_HEADER:
                continue
            try:
                row.append(
                    float(
                        self._data.get(
                            field_name,
                        )
                    )
                )
            except Exception as e:
                logger.warning(e)
                row.append(0)
        return row

    @property
    def step(self) -> str:
        return self._data.get(self.STEP, '')

    @property
    def all_headers(self) -> list:
        headers = [filed_name for filed_name in self._data.keys() if filed_name not in self.EXCLUDE_HEADER]
        return self.COMPLEMENT_HEADER + headers
