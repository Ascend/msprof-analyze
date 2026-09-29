# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
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
import unittest
from unittest.mock import patch, MagicMock
from msprof_analyze.compare_tools.compare_backend.compare_bean.module_compare_bean import ModuleCompareBean


class TestModuleCompareBean(unittest.TestCase):

    @patch("msprof_analyze.compare_tools.compare_backend.compare_bean."
           "module_compare_bean.longest_common_subsequence_matching")
    def test_modulecomparebean_rows_should_calculate_successfully(self, mock_longest_common_subsequence_matching):
        mock_kernel = MagicMock(device_dur=30, kernel_details="")
        op = MagicMock()
        op.name = "ADD"
        op.kernel_list = [mock_kernel]
        op.call_stack = ""
        mock_longest_common_subsequence_matching.return_value = [[op, op]]
        module = MagicMock()
        module.module_class = ""
        module.module_level = ""
        module.module_name = ""
        module.device_self_dur = 1
        module.device_total_dur = 2
        module.toy_layer_api_list = []
        module.call_stack = ""
        base_module = module
        module.device_total_dur = 3
        comparison_module = module
        bean = ModuleCompareBean(base_module, comparison_module)
        rows = bean.rows
        self.assertEqual(len(rows), 2)
