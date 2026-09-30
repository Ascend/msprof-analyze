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

from msprof_analyze.compare_tools.compare_backend.compare_bean.origin_data_bean.kernel_details_bean \
    import KernelDetailsBean


class TestKernelDetailsBean(unittest.TestCase):
    kernel_bean1 = KernelDetailsBean(
        {'Type': "memcopy", 'Name': "aclnninplacecopy_tensormove", 'aiv_vec_time(us)': "N/A", 'mac_time(us)': 5.7,
         'Duration(us)': 5})
    kernel_bean2 = KernelDetailsBean({'Type': "matmul", 'Name': "matmul", 'Duration(us)': 5})
    kernel_bean3 = KernelDetailsBean(
        {'Type': "Add", 'Name': "Add", 'aiv_vec_time(us)': 1.2, 'mac_time(us)': 5.7, 'Duration(us)': 5})
    kernel_bean4 = KernelDetailsBean(
        {'Type': "flashattention_bwd_grad", 'Name': "flashattention", 'mac_time(us)': 0, 'Duration(us)': 5})

    @staticmethod
    def _get_property_str(bean: KernelDetailsBean):
        return f"{bean.name}-{bean.op_type}-{bean.duration}-{bean.aiv_vec_time}-{bean.mac_time}"

    def test_property(self):
        self.assertEqual(self._get_property_str(self.kernel_bean2), "matmul-matmul-5.0-nan-nan")
        self.assertEqual(self._get_property_str(self.kernel_bean3), "Add-Add-5.0-1.2-5.7")

    def test_is_hide_op_pmu(self):
        self.assertTrue(self.kernel_bean2.is_hide_op_pmu())
        self.assertFalse(self.kernel_bean1.is_hide_op_pmu())

    def test_is_vector(self):
        self.assertTrue(self.kernel_bean3.is_vector())
        self.assertTrue(self.kernel_bean4.is_vector())
        self.assertFalse(self.kernel_bean1.is_vector())

    def test_is_invalid(self):
        self.assertTrue(self.kernel_bean2.is_invalid())
        self.assertFalse(self.kernel_bean1.is_invalid())

    def test_is_fa_bwd(self):
        self.assertTrue(self.kernel_bean4.is_fa_bwd())
        self.assertFalse(self.kernel_bean1.is_fa_bwd())

    def test_is_sdma(self):
        self.assertTrue(self.kernel_bean1.is_sdma())
        self.assertFalse(self.kernel_bean2.is_sdma())

    def test_is_flash_attention(self):
        self.assertTrue(self.kernel_bean4.is_flash_attention())
        self.assertFalse(self.kernel_bean2.is_flash_attention())

    def test_is_cube(self):
        self.assertTrue(self.kernel_bean2.is_matmul())
        self.assertFalse(self.kernel_bean3.is_matmul())
