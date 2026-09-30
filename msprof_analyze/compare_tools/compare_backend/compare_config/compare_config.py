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
