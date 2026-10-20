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
from unittest.mock import MagicMock
from msprof_analyze.compare_tools.compare_backend.compare_bean.module_statistic_bean import ModuleStatisticBean


class TestModuleStatisticBean(unittest.TestCase):

    def test_modulestatisticbean_rows_should_calculate_successfully(self):
        mock_kernel = MagicMock()
        mock_kernel.kernel_name = "add"
        mock_kernel.device_dur = 2
        mock_torch_op = MagicMock()
        mock_torch_op.name = "add"
        mock_torch_op.device_dur = 5
        mock_torch_op.kernel_list = [mock_kernel]
        mock_data = MagicMock()
        mock_data.device_self_dur = 5
        mock_data.device_total_dur = 10
        mock_data.toy_layer_api_list = [mock_torch_op]
        base_data = [mock_data]
        mock_data.device_total_dur = 11
        comparison_data = [mock_data]
        bean = ModuleStatisticBean("nn.Module/add", base_data, comparison_data)
        rows = bean.rows
        self.assertEqual(len(rows), 2)
