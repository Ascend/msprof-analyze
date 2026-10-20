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
from msprof_analyze.prof_common.utils import convert_to_float, convert_to_int


class OpStatisticBean:
    def __init__(self, data: dict):
        self.kernel_type = data.get("OP Type", "")
        self.core_type = data.get("Core Type", "")
        self.total_dur = convert_to_float(data.get("Total Time(us)", 0))
        self.avg_dur = convert_to_float(data.get("Avg Time(us)", 0))
        self.max_dur = convert_to_float(data.get("Max Time(us)", 0))
        self.min_dur = convert_to_float(data.get("Min Time(us)", 0))
        self.calls = convert_to_int(data.get("Count", 0))
