# Copyright (c) 2025, Huawei Technologies Co., Ltd.
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

import unittest

from msprof_analyze.prof_exports.mbu_export import KernelBytesExport, QUERY_KERNEL_BYTES


class TestMbuExport(unittest.TestCase):
    def test_kernel_bytes_export_init_and_param_order(self):
        export = KernelBytesExport("dummy.db", "operator_mbu")
        self.assertEqual(export.get_param_order(), [])
        self.assertEqual(export.get_query(), QUERY_KERNEL_BYTES)

    def test_query_includes_output_data_types(self):
        # MBU 需要输出数据类型来计算访存字节，查询必须包含 outputDataTypes
        self.assertIn("outputDataTypes", QUERY_KERNEL_BYTES)
        self.assertIn("output_types", QUERY_KERNEL_BYTES)


if __name__ == "__main__":
    unittest.main()
