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
import unittest
from unittest import mock

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.cluster_data_preprocess.mindspore_data_preprocessor import MindsporeDataPreprocessor


class TestMindsporeDataPreprocessor(unittest.TestCase):
    DIR_PATH = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self) -> None:
        if os.path.exists(self.DIR_PATH):
            shutil.rmtree(self.DIR_PATH)

        def create_worker_dir(worker_name, rank_id):
            worker_path = os.path.join(self.DIR_PATH, worker_name)
            profiler_info_name = f"profiler_info_{rank_id}.json" if rank_id else "profiler_info.json"
            os.makedirs(worker_path)
            with open(os.path.join(worker_path, profiler_info_name), 'w'):
                pass
            output_dir = os.path.join(worker_path, Constant.ASCEND_PROFILER_OUTPUT)
            os.makedirs(output_dir)
            db_filename = f"ascend_mindspore_profiler_{rank_id}.db" if rank_id else "ascend_mindspore_profiler.db"
            with open(os.path.join(output_dir, db_filename), 'w'):
                pass

        # Create all worker directories with their respective files
        create_worker_dir('worker1_114514_ascend_ms', rank_id=1)
        create_worker_dir('worker2_124500_ascend_ms', rank_id=2)
        create_worker_dir('single_worker_114514_ascend_ms', rank_id=None)
        create_worker_dir('worker1_114515_ascend_ms', rank_id=1)
        create_worker_dir('worker2_114516_ascend_ms', rank_id=2)

        self.dirs = [os.path.join(self.DIR_PATH, filename) for filename in os.listdir(self.DIR_PATH)]

    def tearDown(self) -> None:
        shutil.rmtree(self.DIR_PATH)

    def test_get_data_map_when_given_normal_input_expect_dict(self):
        res = MindsporeDataPreprocessor(self.dirs).get_data_map()
        self.assertIsInstance(res, dict)

    def test_get_rank_id_when_given_cluster_rank_1_dirs_expect_rank_1(self):
        check = MindsporeDataPreprocessor(self.dirs)
        ret = check.get_rank_id(os.path.join(self.DIR_PATH, 'worker1_114514_ascend_ms'))
        self.assertEqual(ret, 1)

    def test_get_rank_id_when_single_device_not_cluster_expect_rank_minus1(self):
        check = MindsporeDataPreprocessor(self.dirs)
        ret = check.get_rank_id(os.path.join(self.DIR_PATH, 'single_worker_114514_ascend_ms'))
        self.assertEqual(ret, -1)

    def test_get_data_map_given_cluster_files_expect_rank_12(self):
        check = MindsporeDataPreprocessor(self.dirs)
        with mock.patch("msprof_analyze.prof_common.file_manager.FileManager.read_json_file",
                        return_value={}):
            ret = check.get_data_map()
            self.assertEqual(len(ret), 2)
            self.assertIn(1, ret.keys())
            self.assertIn(2, ret.keys())
            self.assertIn(os.path.join(self.DIR_PATH, 'worker1_114515_ascend_ms'), ret.values())
            self.assertIn(os.path.join(self.DIR_PATH, 'worker2_124500_ascend_ms'), ret.values())

    def test_get_msprof_dir_should_return_(self):
        res = MindsporeDataPreprocessor(self.dirs).get_msprof_dir(os.path.join(self.DIR_PATH,
                                                                               'worker1_114514_ascend_ms'))
        self.assertEqual(res, "")

if __name__ == '__main__':
    unittest.main()
