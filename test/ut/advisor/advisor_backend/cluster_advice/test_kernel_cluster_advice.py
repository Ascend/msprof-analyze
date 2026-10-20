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
import stat
import shutil
import unittest
from unittest import mock
from unittest.mock import MagicMock

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.advisor_backend.cluster_advice.kernel_cluster_advice import KernelClusterAdvice


class TestClusterAdviceBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp_dir = './tmp_dir'
        cls.data_map_normal = {
            0: os.path.join(cls.tmp_dir, 'rank_0'),
            1: os.path.join(cls.tmp_dir, 'rank_1')
        }
        cls.data_map_abnormal = {
            2: os.path.join(cls.tmp_dir, 'rank_2')
        }
        ascend_output_0 = os.path.join(cls.tmp_dir, 'rank_0', Constant.SINGLE_OUTPUT)
        os.makedirs(ascend_output_0)
        ascend_output_1 = os.path.join(cls.tmp_dir, 'rank_1', Constant.SINGLE_OUTPUT)
        os.makedirs(ascend_output_1)
        ascend_output_2 = os.path.join(cls.tmp_dir, 'rank_2', Constant.SINGLE_OUTPUT)
        os.makedirs(ascend_output_2)
        # write data to csv file
        flags = os.O_WRONLY | os.O_CREAT
        mode = stat.S_IWUSR | stat.S_IRUSR
        with os.fdopen(os.open(
            os.path.join(ascend_output_0, Constant.KERNEL_DETAILS_CSV), flags, mode), 'w') as fp:
            fp.write('Step Id,Name,Input Shapes,Input Data Types,Output Shapes,Duration(us)\n')
            fp.write('0,ZerosLike46,"""544404480""",FLOAT16,"""544404480""",10.0\n')
            fp.write('0,ZerosLike46,"""544404480""",FLOAT16,"""544404480""",20.0\n')
        with os.fdopen(os.open(
            os.path.join(ascend_output_1, Constant.KERNEL_DETAILS_CSV), flags, mode), 'w') as fp:
            fp.write('Step Id,Name,Input Shapes,Input Data Types,Output Shapes,Duration(us)\n')
            fp.write('0,Mul85,"""4,1024,12288;4,1024,1""",FLOAT16,"""4,1024,12288""",30.0\n')
            fp.write('0,Mul85,"""4,1024,12288;4,1024,1""",FLOAT16,"""4,1024,12288""",40.0\n')
        cls.all_kernel_data = {
            'rank id': {0: 0, 1: 0, 2: 1, 3: 1},
            'Name': {0: 'ZerosLike46', 1: 'ZerosLike46', 2: 'Mul85', 3: 'Mul85'},
            'Input Shapes': {0: '"544404480"', 1: '"544404480"', 2: '"4,1024,12288;4,1024,1"',
                             3: '"4,1024,12288;4,1024,1"'},
            'Input Data Types': {0: 'FLOAT16', 1: 'FLOAT16', 2: 'FLOAT16', 3: 'FLOAT16'},
            'Output Shapes': {0: '"544404480"', 1: '"544404480"', 2: '"4,1024,12288"', 3: '"4,1024,12288"'},
            'Duration(us)': {0: 10.0, 1: 20.0, 2: 30.0, 3: 40.0}
        }
        cls.expect_result = {
            'rank id': {0: 0, 1: 1},
            'Name': {0: 'ZerosLike46', 1: 'Mul85'},
            'Input Shapes': {0: '"544404480"', 1: '"4,1024,12288;4,1024,1"'},
            'Input Data Types': {0: 'FLOAT16', 1: 'FLOAT16'},
            'Output Shapes': {0: '"544404480"', 1: '"4,1024,12288"'},
            'Duration(us)_mean': {0: 15.0, 1: 35.0},
            'Duration(us)_var': {0: 50.0, 1: 50.0},
            'Duration(us)_max': {0: 20.0, 1: 40.0},
            'Duration(us)_min': {0: 10.0, 1: 30.0},
            'Duration(us)_count': {0: 2, 1: 2},
            'Duration(us)_sum': {0: 30.0, 1: 70.0}
        }
        with os.fdopen(os.open(
            os.path.join(ascend_output_2, Constant.KERNEL_DETAILS_CSV), flags, mode), 'w') as fp:
            fp.write('Wrong Title\n')
            fp.write('0\n')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir)

    def test_run(self):
        advice_inst = KernelClusterAdvice(self.tmp_dir)
        advice_inst.load_kernel_details_data = MagicMock(name="load_kernel_details_data")
        advice_inst.calculate_data = MagicMock(name="calculate_data")
        advice_inst.run()
        advice_inst.load_kernel_details_data.assert_called_once()
        advice_inst.calculate_data.assert_called_once()

    def load_kernel_details_data_with_normal_data(self):
        advice_inst = KernelClusterAdvice(self.tmp_dir)
        with mock.patch("cluster_data_preprocess.pytorch_data_preprocessor.PytorchDataPreprocessor") as py_mock, \
            mock.patch("common_func.path_manager.PathManager.check_path_readable"):
            py_mock_inst = py_mock.return_valuee
            py_mock_inst.get_data_map.return_value = self.data_map_normal
            advice_inst.load_kernel_details_data()
        self.assertEqual(self.all_kernel_data, advice_inst.all_kernel_data.to_dict())

    def load_kernel_details_data_with_abnormal_data(self):
        advice_inst = KernelClusterAdvice(self.tmp_dir)
        with self.assertRaises(RuntimeError):
            with mock.patch("cluster_data_preprocess.pytorch_data_preprocessor.PytorchDataPreprocessor") as py_mock, \
                mock.patch("common_func.path_manager.PathManager.check_path_readable"):
                py_mock_inst = py_mock.return_valuee
                py_mock_inst.get_data_map.return_value = self.data_map_abnormal
                advice_inst.load_kernel_details_data()

    def calculate_data(self):
        advice_inst = KernelClusterAdvice(self.tmp_dir)
        advice_inst.all_kernel_data = self.all_kernel_data
        result = advice_inst.calculate_data()
        self.assertEqual(self.expect_result, result.to_dict())
