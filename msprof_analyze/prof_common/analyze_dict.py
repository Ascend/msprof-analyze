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
class AnalyzeDict(dict):
    def __getstate__(self):
        return self.__dict__

    def __setstate__(self, d):
        self.__dict__.update(d)

    def __setattr__(self, key: str, value):
        if isinstance(value, dict) and not isinstance(value, AnalyzeDict):
            value = AnalyzeDict(value)
        self[key] = value

    def __getattr__(self, key: str):
        if key not in self:
            return {}
        value = self[key]
        if isinstance(value, dict) and not isinstance(value, AnalyzeDict):
            value = AnalyzeDict(value)
            self[key] = value
        return value
