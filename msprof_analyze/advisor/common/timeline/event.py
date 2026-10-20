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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2024-2024. Huawei Technologies Co., Ltd. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
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

from decimal import Decimal


class AdvisorDict(dict):
    def __getstate__(self):
        return self.__dict__

    def __setstate__(self, d):
        self.__dict__.update(d)

    def __getattr__(self, key: str):
        if key not in self:
            return {}

        value = self[key]
        if isinstance(value, dict):
            value = AdvisorDict(value)
        return value


class TimelineEvent(AdvisorDict):
    def ts_include(self, event):
        self_ts = self.ts
        event_ts = event.ts

        if not self_ts or not event_ts:
            return False

        self_dur = self.dur if not isinstance(self.dur, dict) else 0.0
        event_dur = event.dur if not isinstance(event.dur, dict) else 0.0

        return Decimal(self_ts) <= Decimal(event_ts) and Decimal(self_ts) + Decimal(self_dur) >= Decimal(
            event_ts
        ) + Decimal(event_dur)
