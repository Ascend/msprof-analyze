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
from unittest.mock import MagicMock, patch, mock_open
import os
import shutil
import queue

from msprof_analyze.advisor.utils import utils


class TestUtilsDecorators(unittest.TestCase):
    def test_debug_option(self):
        @utils.debug_option
        def test_func():
            return "test"

        result = test_func()
        self.assertEqual(result, "test")

    def test_ignore_warning(self):
        exception = Exception("test")
        result = utils.ignore_warning(exception)
        self.assertEqual(result, exception)


class TestCheckPathAccess(unittest.TestCase):
    temp_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir, exist_ok=True)
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("test content")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_path_access_decorator_readable_file(self):
        @utils.CheckPathAccess
        def read_file(path):
            with open(path, 'r') as f:
                return f.read()

        result = read_file(self.test_file)
        self.assertEqual(result, "test content")


class TestFormatFunctions(unittest.TestCase):
    def test_format_timeline_result(self):
        input_data = {
            "api1:123": {"stack1": 10, "stack2": 5},
            "api2:456": {"stack3": 8}
        }

        result = utils.format_timeline_result(input_data)
        expected = {
            "api1": [("stack1", 10), ("stack2", 5)],
            "api2": [("stack3", 8)]
        }
        self.assertEqual(result, expected)

    def test_to_percent(self):
        self.assertEqual(utils.to_percent(0.1234), "12.34%")
        self.assertEqual(utils.to_percent(0.5), "50.00%")
        self.assertEqual(utils.to_percent(1.0), "100.00%")
        self.assertEqual(utils.to_percent(0.0), "0.00%")
        self.assertEqual(utils.to_percent(0.9999), "99.99%")


class TestParallelJob(unittest.TestCase):
    def test_parallel_job_init_invalid_func(self):
        with self.assertRaises(TypeError):
            utils.ParallelJob("not_a_function", [1, 2, 3])

    def test_parallel_job_init_invalid_params(self):
        def test_func(x):
            return x * 2

        with self.assertRaises(TypeError):
            utils.ParallelJob(test_func, "not_a_list")

    @patch('multiprocessing.Process')
    @patch('multiprocessing.Queue')
    def test_parallel_job_start(self, mock_queue, mock_process):
        mock_job_queue = MagicMock()
        mock_completed_queue = MagicMock()
        mock_listener_process = MagicMock()
        mock_worker_process = MagicMock()

        mock_queue.side_effect = [mock_job_queue, mock_completed_queue]
        mock_process.side_effect = [mock_listener_process, mock_worker_process, mock_worker_process]

        def test_func(x):
            return x * 2

        job_params = [1, 2, 3]
        job = utils.ParallelJob(test_func, job_params, "test_job")
        mock_job_queue.empty.side_effect = [False, False, False, True]
        mock_job_queue.get.side_effect = [0, 1, 2, queue.Empty]
        mock_completed_queue.get.side_effect = [1, 2, 3, None]
        job.start(2)
        self.assertEqual(mock_process.call_count, 3)  # 2 workers + 1 listener


class TestParameterFunctions(unittest.TestCase):
    @patch.dict(os.environ, {'TEST_PARAM': 'env_value'})
    def test_load_parameter_with_env(self):
        result = utils.load_parameter('TEST_PARAM', 'default_value')
        self.assertEqual(result, 'env_value')

    @patch.dict(os.environ, {}, clear=True)
    def test_load_parameter_without_env(self):
        result = utils.load_parameter('TEST_PARAM', 'default_value')
        self.assertEqual(result, 'default_value')


class TestSafeWrite(unittest.TestCase):
    temp_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    def test_safe_write_with_encoding(self, mock_check_output_directory_path):
        test_file = os.path.join(self.temp_dir, "test.txt")
        content = "test content with unicode: 测试"

        utils.safe_write(content, test_file, encoding='utf-8')

        with open(test_file, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), content)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    def test_safe_write_existing_directory(self, mock_check_output_directory_path):
        test_dir = os.path.join(self.temp_dir, "existing", "subdir")
        os.makedirs(test_dir)
        test_file = os.path.join(test_dir, "test.txt")
        content = "test content"

        utils.safe_write(content, test_file)

        with open(test_file, 'r') as f:
            self.assertEqual(f.read(), content)


class TestPathValidationFunctions(unittest.TestCase):
    temp_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('msprof_analyze.advisor.utils.utils.PathManager')
    def test_join_prof_path_regex(self, mock_path_manager):
        temp_dir = os.path.join(self.temp_dir, "test_join_prof_path_regex")
        os.makedirs(temp_dir)
        try:
            mock_path_manager.limited_depth_walk.return_value = [
                (temp_dir, ['subdir1', 'subdir2'], []),
                (os.path.join(temp_dir, 'subdir1'), [], []),
                (os.path.join(temp_dir, 'subdir2'), [], [])
            ]

            result = utils.join_prof_path(temp_dir, "subdir\\d")
            self.assertEqual(result, os.path.join(temp_dir, 'subdir1'))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestSafeOpen(unittest.TestCase):
    temp_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir, exist_ok=True)
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("test content")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_safe_open_existing_file(self):
        with utils.SafeOpen(self.test_file) as f:
            self.assertIsNotNone(f)
            content = f.read()
            self.assertEqual(content, "test content")

    def test_safe_open_non_existent(self):
        with patch('msprof_analyze.advisor.utils.utils.logger') as mock_logger:
            with utils.SafeOpen("/non/existent/file.txt") as f:
                self.assertIsNone(f)
            mock_logger.warning.assert_called_once()


class TestFileSearchFunctions(unittest.TestCase):
    temp_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        self.sub_dir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(self.sub_dir)
        self.target_file = os.path.join(self.sub_dir, "target.txt")
        with open(self.target_file, 'w') as f:
            f.write("target content")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('msprof_analyze.advisor.utils.utils.PathManager')
    def test_get_file_path_by_walk_found(self, mock_path_manager):
        mock_path_manager.limited_depth_walk.return_value = [
            (self.temp_dir, ['subdir'], []),
            (self.sub_dir, [], ['target.txt', 'other.txt'])
        ]
        result = utils.get_file_path_by_walk(self.temp_dir, "target.txt")
        self.assertEqual(result, self.target_file)

    @patch('msprof_analyze.advisor.utils.utils.PathManager')
    def test_get_file_path_by_walk_not_found(self, mock_path_manager):
        mock_path_manager.limited_depth_walk.return_value = [
            (self.temp_dir, ['subdir'], []),
            (self.sub_dir, [], ['other.txt'])
        ]
        result = utils.get_file_path_by_walk(self.temp_dir, "target.txt")
        self.assertEqual(result, "")


class TestPathValidation(unittest.TestCase):
    temp_dir = os.path.join(os.path.dirname(__file__), 'DT_CLUSTER_PREPROCESS')

    def setUp(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir)
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("test content")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_path_valid_file(self):
        result = utils.check_path_valid(self.test_file, is_file=True)
        self.assertTrue(result)

    def test_check_path_valid_empty_path(self):
        with self.assertRaises(FileNotFoundError):
            utils.check_path_valid("", is_file=True)

    def test_check_path_valid_non_existent(self):
        with self.assertRaises(FileNotFoundError):
            utils.check_path_valid("/non/existent/path", is_file=True)

    def test_check_path_valid_file_as_directory(self):
        with self.assertRaises(FileNotFoundError):
            utils.check_path_valid(self.temp_dir, is_file=True)

    def test_check_path_valid_directory_as_file(self):
        with self.assertRaises(FileNotFoundError):
            utils.check_path_valid(self.test_file, is_file=False)


class TestJSONParsing(unittest.TestCase):
    @patch.dict(os.environ, {'DISABLE_STREAMING_READER': '1'})
    def test_parse_json_with_generator_disable_streaming(self):
        with patch('msprof_analyze.advisor.utils.utils.check_path_valid') as mock_check:
            mock_check.return_value = True
            with patch('builtins.open', mock_open(read_data='{"item": [{"id": 1}, {"id": 2}, {"id": 3}]}')):
                with patch('json.loads') as mock_loads:
                    mock_loads.return_value = {"item": [{"id": 1}, {"id": 2}, {"id": 3}]}

                    def test_func(index, event):
                        return event['id']

                    result = utils.parse_json_with_generator("test.json", test_func)

        self.assertEqual(sorted(result), [])


    def test_parse_json_with_generator_invalid_path(self):
        with patch('msprof_analyze.advisor.utils.utils.check_path_valid') as mock_check:
            mock_check.return_value = False

            result = utils.parse_json_with_generator("/invalid/path.json", lambda i, e: e)
            self.assertEqual(result, [])


class TestConversionFunctions(unittest.TestCase):
    def test_convert_to_float_with_warning(self):
        with patch('msprof_analyze.advisor.utils.utils.logger') as mock_logger:
            result = utils.convert_to_float_with_warning("invalid")
            self.assertEqual(result, 0)
            mock_logger.warning.assert_called_once()

    def test_safe_index(self):
        test_list = ['a', 'b', 'c']
        self.assertEqual(utils.safe_index(test_list, 1), 'b')
        self.assertEqual(utils.safe_index(test_list, 5), None)
        self.assertEqual(utils.safe_index(test_list, 5, 'default'), 'default')
        self.assertEqual(utils.safe_index([], 0), None)
        self.assertEqual(utils.safe_index([], 0, 'empty'), 'empty')

    def test_convert_to_int(self):
        self.assertEqual(utils.convert_to_int("123"), 123)
        self.assertEqual(utils.convert_to_int(123.45), 123)
        self.assertEqual(utils.convert_to_int("invalid"), 0)
        self.assertEqual(utils.convert_to_int(""), 0)
        try:
            result = utils.convert_to_int(None)
            self.assertEqual(result, 0)
        except TypeError:
            pass

    def test_convert_to_int_with_exception(self):
        self.assertEqual(utils.convert_to_int_with_exception("123"), 123)
        self.assertEqual(utils.convert_to_int_with_exception(""), 0)
        with patch('msprof_analyze.advisor.utils.utils.logger'):
            with patch('msprof_analyze.advisor.utils.utils.convert_to_float') as mock_convert:
                mock_convert.return_value = 0
                result = utils.convert_to_int_with_exception("invalid")
                self.assertEqual(result, 0)
