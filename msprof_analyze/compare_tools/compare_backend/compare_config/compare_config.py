# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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
import os

from msprof_analyze.compare_tools.compare_backend.utils.singleton import Singleton
from msprof_analyze.prof_common.utils import SafeConfigReader


@Singleton
class CompareConfig:
    _REQUIRED_SECTIONS = {"OP_MASK": ["FA_MASK", "CONV_MASK", "MATMUL_MASK", "CUBE_MASK", "TRANS_MASK", "MC2_KERNEL"]}

    def __init__(self, cls=None):
        self.config_reader = SafeConfigReader(
            os.path.join(os.path.dirname(os.path.abspath(os.path.join(__file__))), "compare_config.ini")
        )
        self.config_reader.validate(self._REQUIRED_SECTIONS)
        self.config = self.config_reader.get_config()
        self._fa_mask = self.get_mask_by_key("FA_MASK")
        self._conv_mask = self.get_mask_by_key("CONV_MASK")
        self._mm_mask = self.get_mask_by_key("MATMUL_MASK")
        self._cube_mask = self.get_mask_by_key("CUBE_MASK")
        self._trans_mask = self.get_mask_by_key("TRANS_MASK")
        self._mc2_kernel = self.get_mask_by_key("MC2_KERNEL")

    @property
    def fa_mask(self):
        return self._fa_mask

    @property
    def conv_mask(self):
        return self._conv_mask

    @property
    def mm_mask(self):
        return self._mm_mask

    @property
    def cube_mask(self):
        return self._cube_mask

    @property
    def trans_mask(self):
        return self._trans_mask

    @property
    def mc2_kernel(self):
        return self._mc2_kernel

    def get_mask_by_key(self, key):
        return set((mask.strip().lower() for mask in self.config.get("OP_MASK", key).split(",") if mask.strip()))
