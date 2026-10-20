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
import os
import shutil
import stat
import json
import unittest

from msprof_analyze.advisor.advisor_backend.interface import Interface


class TestOptimizerAdvice(unittest.TestCase):
    TMP_DIR = "./ascend_pt"
    interface = None
    err_interface = None

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        if os.path.exists(TestOptimizerAdvice.TMP_DIR):
            shutil.rmtree(TestOptimizerAdvice.TMP_DIR)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if not os.path.exists(TestOptimizerAdvice.TMP_DIR):
            os.makedirs(TestOptimizerAdvice.TMP_DIR)
        # create json files
        json_data = [{
            "ph": "X",
            "name": "Optimizer.step#Adam.step",
            "pid": 2157254,
            "tid": 2157254,
            "ts": 1700547697922669.8,
            "dur": 5762.21,
            "cat": "cpu_op",
            "args": {
                "Sequence number": -1,
                "Fwd thread id": 0
            }
        }]
        json_str = json.dumps(json_data)
        with os.fdopen(os.open(f"{TestOptimizerAdvice.TMP_DIR}/err_file.json",
                               os.O_WRONLY | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR), 'w') as fp:
            fp.write(json_str)
        TestOptimizerAdvice.err_interface = Interface(os.path.join(TestOptimizerAdvice.TMP_DIR, "err_file.json"))
        TestOptimizerAdvice.interface = Interface(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                               "trace_view.json"))


    def test_run(self):
        dataset = TestOptimizerAdvice.err_interface.get_data('timeline', 'optimizer')
        case_advice = dataset.get('advice')
        case_bottleneck = dataset.get('bottleneck')
        case_data = dataset.get('data')
        self.assertEqual(0, len(case_advice))
        self.assertEqual(0, len(case_bottleneck))
        self.assertEqual(0, len(case_data))

        dataset = TestOptimizerAdvice.interface.get_data('timeline', 'optimizer')
        real_advice = real_bottleneck = ("You can choose torch_npu.optim.NpuFusedAdam to "
                                         "replace the current Optimizer: Optimizer.step#Adam.step.")
        real_data = ['Optimizer.step#Adam.step']
        case_advice = dataset.get('advice')
        case_bottleneck = dataset.get('bottleneck')
        case_data = dataset.get('data')
        self.assertEqual(real_advice, case_advice)
        self.assertEqual(real_bottleneck, case_bottleneck)
        self.assertEqual(real_data, case_data)
