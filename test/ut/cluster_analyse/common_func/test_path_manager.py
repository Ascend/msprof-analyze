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
import os
import time
import pytest

from msprof_analyze.prof_common.path_manager import PathManager


PATH_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../../resource'))
PATH_FILE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../../resource/test.csv'))
PATH_TEMP = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../../temp'))


class TestPathManager(unittest.TestCase):
    def test_check_input_directory_path(self):
        with pytest.raises(RuntimeError) as _:
            PathManager.check_input_directory_path(PATH_FILE)
        PathManager.check_input_directory_path(PATH_DIR)

    def test_check_input_file_path(self):
        with pytest.raises(RuntimeError) as _:
            PathManager.check_input_file_path(PATH_DIR)
        PathManager.check_input_file_path(PATH_FILE)

    def test_check_path_length(self):
        path_max = "a" * 4097
        name_max = "a" * 257
        path_with_name_max = "a/" + name_max
        with pytest.raises(FileNotFoundError) as _:
            PathManager.check_input_directory_path(path_max)
        with pytest.raises(FileNotFoundError) as _:
            PathManager.check_input_directory_path(path_with_name_max)
        PathManager.check_path_length(PATH_FILE)

    def test_input_path_common_check(self):
        path_max = "a" * 4097
        name_max = "a" * 257
        path_with_name_max = "a/" + name_max
        PathManager.input_path_common_check(path_max)
        PathManager.input_path_common_check(path_with_name_max)
        PathManager.input_path_common_check(PATH_DIR + "!@~#$%")
        PathManager.input_path_common_check(PATH_FILE)

    def test_check_path_owner_consistent(self):
        PathManager.check_path_owner_consistent([PATH_DIR])

    def test_check_path_writeable(self):
        link_name = "test_link" + str(time.time())
        os.symlink(PATH_FILE, link_name)
        PathManager.check_path_writeable(link_name)
        PathManager.check_path_writeable(PATH_DIR)
        os.unlink(link_name)

    def test_check_path_readable(self):
        link_name = "test_link" + str(time.time())
        os.symlink(PATH_FILE, link_name)
        PathManager.check_path_readable(link_name)
        PathManager.check_path_readable(PATH_DIR)
        os.unlink(link_name)

    def test_remove_path_safety(self):
        path = PATH_TEMP + str(time.time())
        os.makedirs(path)
        link_name = "test_link" + str(time.time())
        os.symlink(PATH_FILE, link_name)
        with pytest.raises(RuntimeError) as _:
            PathManager.remove_path_safety(link_name)
        PathManager.remove_path_safety(path)
        os.unlink(link_name)

    def test_make_dir_safety(self):
        path = PATH_TEMP + str(time.time())
        link_name = "test_link" + str(time.time())
        os.symlink(PATH_FILE, link_name)
        with pytest.raises(RuntimeError) as _:
            PathManager.make_dir_safety(link_name)
        PathManager.make_dir_safety(path)
        os.removedirs(path)
        os.unlink(link_name)

    def test_create_file_safety(self):
        path = PATH_TEMP + str(time.time())
        link_name = "test_link" + str(time.time())
        os.symlink(PATH_FILE, link_name)
        PathManager.create_file_safety(link_name)
        PathManager.create_file_safety(path)
        os.remove(path)
        os.unlink(link_name)

    def test_get_realpath(self):
        path = PATH_TEMP + str(time.time())
        real_path = PathManager.get_realpath(path)
        link_name = "test_link" + str(time.time())
        os.symlink(PATH_FILE, link_name)
        PathManager.get_realpath(link_name)
        self.assertTrue(real_path.endswith(path))
        os.unlink(link_name)
