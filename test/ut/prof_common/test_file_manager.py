# Copyright (c) 2023, Huawei Technologies Co., Ltd. All rights reserved.
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
import csv
import json
import os
import unittest
from unittest import mock
from unittest.mock import patch, mock_open

from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.file_manager import FileManager, check_db_path_valid
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class TestFileManager(unittest.TestCase):
    def setUp(self):
        self.addition_arg_manager = AdditionalArgsManager()
        # 创建临时目录和文件用于测试
        self.temp_dir = os.path.join(os.path.dirname(__file__), "DT_FileManager")
        os.makedirs(self.temp_dir)
        self.temp_json_path = os.path.join(self.temp_dir, "test.json")
        self.temp_csv_path = os.path.join(self.temp_dir, "test.csv")
        self.temp_yaml_path = os.path.join(self.temp_dir, "test.yaml")
        self.temp_common_path = os.path.join(self.temp_dir, "test.txt")

        # 创建测试用JSON文件
        with open(self.temp_json_path, "w", encoding='utf-8') as f:
            json.dump({"key": "value"}, f)

        # 创建测试用CSV文件
        with open(self.temp_csv_path, "w", newline="", encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name"])
            writer.writerow([1, "test"])

        # 创建测试用YAML文件
        with open(self.temp_yaml_path, "w", encoding='utf-8') as f:
            f.write("key: value\n")

        # 创建测试用普通文件
        with open(self.temp_common_path, "w", encoding='utf-8') as f:
            f.write("test content")

    def tearDown(self):
        AdditionalArgsManager._instance = {}
        # 清理临时文件
        for file_path in [self.temp_json_path, self.temp_csv_path, self.temp_yaml_path, self.temp_common_path]:
            if os.path.exists(file_path):
                os.remove(file_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    @patch('msprof_analyze.prof_common.additional_args_manager.AdditionalArgsManager')
    def test_read_json_file_success(self, mock_additional_args, mock_getsize, mock_check_input_file_path):
        # 测试成功读取JSON文件
        mock_additional_args.return_value.force = False
        mock_getsize.return_value = 100
        mock_file_content = json.dumps({"key": "value"})

        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            result = FileManager.read_json_file(self.temp_json_path)
            self.assertEqual(result, {"key": "value"})
            mock_check_input_file_path.assert_called_once_with(self.temp_json_path)
            mock_getsize.assert_called_once_with(self.temp_json_path)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    def test_read_json_file_empty(self, mock_getsize, mock_check_input_file_path):
        # 测试空文件
        mock_getsize.return_value = 0
        result = FileManager.read_json_file(self.temp_json_path)
        self.assertEqual(result, {})

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    def test_read_json_file_exception(self, mock_getsize, mock_check_input_file_path):
        # 测试读取JSON文件时发生异常
        mock_getsize.return_value = 100
        with patch("builtins.open", mock_open()) as m:
            m.side_effect = Exception("Read error")
            with self.assertRaises(RuntimeError):
                FileManager.read_json_file(self.temp_json_path)

    @patch('os.path.isfile')
    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    @patch('csv.DictReader')
    def test_read_csv_file_success(self, mock_dict_reader, mock_getsize, mock_check_input_file_path, mock_isfile):
        # 测试成功读取CSV文件
        mock_isfile.return_value = True
        mock_getsize.return_value = 100
        mock_dict_reader.return_value = [{"id": "1", "name": "test"}]

        with patch("builtins.open", mock_open()):
            result = FileManager.read_csv_file(self.temp_csv_path)
            self.assertEqual(result, [{"id": "1", "name": "test"}])

    def test_read_csv_file_not_exists(self):
        # 测试文件不存在
        non_existent_path = os.path.join(self.temp_dir, "non_existent.csv")
        with self.assertRaises(FileNotFoundError):
            FileManager.read_csv_file(non_existent_path)

    @patch('os.path.isfile')
    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    def test_read_csv_file_empty(self, mock_getsize, mock_check_input_file_path, mock_isfile):
        # 测试空文件
        mock_isfile.return_value = True
        mock_getsize.return_value = 0
        result = FileManager.read_csv_file(self.temp_csv_path)
        self.assertEqual(result, [])

    @patch('os.path.isfile')
    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_path_readable')
    @patch('os.path.getsize')
    def test_read_csv_file_exception(self, mock_getsize, mock_check_readable, mock_isfile):
        # 测试读取CSV文件时发生异常
        mock_isfile.return_value = True
        mock_getsize.return_value = 100

        with patch("builtins.open", mock_open()) as m:
            m.side_effect = Exception("Read error")
            with self.assertRaises(RuntimeError):
                FileManager.read_csv_file(self.temp_csv_path)

    @patch('msprof_analyze.prof_common.file_manager.FileManager.read_json_file')
    def test_check_json_type_dict(self, mock_read_json):
        # 测试检查JSON类型为字典
        mock_read_json.return_value = {"key": "value"}
        result = FileManager.check_json_type(self.temp_json_path)
        self.assertEqual(result, Constant.GPU)
        mock_read_json.assert_called_once_with(self.temp_json_path)

    @patch('msprof_analyze.prof_common.file_manager.FileManager.read_json_file')
    def test_check_json_type_non_dict(self, mock_read_json):
        # 测试检查JSON类型为非字典
        mock_read_json.return_value = ["value1", "value2"]
        result = FileManager.check_json_type(self.temp_json_path)
        self.assertEqual(result, Constant.NPU)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    @patch('yaml.safe_load')
    def test_read_yaml_file_success(self, mock_safe_load, mock_getsize, mock_check_input_file_path):
        # 测试成功读取YAML文件
        mock_getsize.return_value = 100
        mock_safe_load.return_value = {"key": "value"}
        with patch("builtins.open", mock_open()):
            result = FileManager.read_yaml_file(self.temp_yaml_path)
            self.assertEqual(result, {"key": "value"})

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    def test_read_yaml_file_exception(self, mock_getsize, mock_check_input_file_path):
        # 测试读取YAML文件时发生异常
        mock_getsize.return_value = 100
        with patch("builtins.open", mock_open()) as m:
            m.side_effect = Exception("Read error")
            with self.assertRaises(RuntimeError):
                FileManager.read_yaml_file(self.temp_yaml_path)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    def test_read_common_file_success(self, mock_getsize, mock_check_input_file_path):
        # 测试成功读取普通文件
        mock_getsize.return_value = 100
        mock_file_content = "test content"
        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            result = FileManager.read_common_file(self.temp_common_path)
            self.assertEqual(result, "test content")

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    def test_read_common_file_empty(self, mock_getsize, mock_check_input_file_path):
        # 测试空文件
        mock_getsize.return_value = 0
        with self.assertRaises(RuntimeError):
            FileManager.read_common_file(self.temp_common_path)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_input_file_path')
    @patch('os.path.getsize')
    def test_read_common_file_exception(self, mock_getsize, mock_check_input_file_path):
        # 测试读取普通文件时发生异常
        mock_getsize.return_value = 100
        with patch("builtins.open", mock_open()) as m:
            m.side_effect = Exception("Read error")
            with self.assertRaises(RuntimeError):
                FileManager.read_common_file(self.temp_common_path)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    @patch('os.open')
    @patch('os.fdopen')
    def test_create_common_file(self, mock_fdopen, mock_open_os, mock_check_output_directory_path):
        # 测试创建普通文件
        mock_file = mock.MagicMock()
        mock_fdopen.return_value.__enter__.return_value = mock_file
        file_path = os.path.join(self.temp_dir, "new_file.txt")
        content = "new content"
        FileManager.create_common_file(file_path, content)

        mock_check_output_directory_path.assert_called_once_with(os.path.dirname(file_path))
        mock_open_os.assert_called_once_with(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, Constant.FILE_AUTHORITY)
        mock_file.write.assert_called_once_with(content)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    def test_create_common_file_exception(self, mock_check_output_directory_path):
        # 测试创建普通文件时发生异常
        with patch("os.open", side_effect=Exception("Open error")):
            file_path = os.path.join(self.temp_dir, "new_file.txt")

            with self.assertRaises(RuntimeError):
                FileManager.create_common_file(file_path, "content")

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    def test_create_csv_from_dataframe_exception(self, mock_check_output_directory_path):
        # 测试从数据帧创建CSV文件时发生异常
        mock_data = mock.MagicMock()
        mock_data.to_csv.side_effect = Exception("CSV error")
        file_path = os.path.join(self.temp_dir, "new_csv.csv")

        with self.assertRaises(RuntimeError):
            FileManager.create_csv_from_dataframe(file_path, mock_data, index=True)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    @patch('os.open')
    @patch('os.fdopen')
    @patch('csv.writer')
    def test_create_csv_file(self, mock_writer, mock_fdopen, mock_open_os, mock_check_output):
        # 测试创建CSV文件
        mock_file = mock.MagicMock()
        mock_fdopen.return_value.__enter__.return_value = mock_file
        mock_csv_writer = mock.MagicMock()
        mock_writer.return_value = mock_csv_writer

        data = [[1, "test1"], [2, "test2"]]
        headers = ["id", "name"]
        FileManager.create_csv_file(self.temp_dir, data, "test_output.csv", headers)
        output_path = os.path.join(self.temp_dir, Constant.CLUSTER_ANALYSIS_OUTPUT)
        mock_check_output.assert_called_once_with(output_path)
        mock_csv_writer.writerow.assert_called_once_with(headers)
        mock_csv_writer.writerows.assert_called_once_with(data)

    def test_create_csv_file_empty_data(self):
        # 测试空数据
        with patch(
            'msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path'
        ) as mock_check_output_directory_path:
            FileManager.create_csv_file(self.temp_dir, [], "test_output.csv")
            mock_check_output_directory_path.assert_not_called()

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    @patch('os.open')
    @patch('os.fdopen')
    @patch('json.dumps')
    def test_create_json_file(self, mock_dumps, mock_fdopen, mock_open_os, mock_check_output):
        # 测试创建JSON文件
        mock_file = mock.MagicMock()
        mock_fdopen.return_value.__enter__.return_value = mock_file
        mock_dumps.return_value = "{\"key\": \"value\"}"
        data = {"key": "value"}
        FileManager.create_json_file(self.temp_dir, data, "test_output.json")
        output_path = os.path.join(self.temp_dir, Constant.CLUSTER_ANALYSIS_OUTPUT)
        mock_check_output.assert_called_once_with(output_path)
        mock_file.write.assert_called_once_with("{\"key\": \"value\"}")

    @patch('msprof_analyze.prof_common.path_manager.PathManager.check_output_directory_path')
    @patch('os.open')
    @patch('os.fdopen')
    @patch('json.dumps')
    def test_create_json_file_common_flag(
        self, mock_dumps, mock_fdopen, mock_open_os, mock_check_output_directory_path
    ):
        # 测试使用common_flag创建JSON文件
        mock_file = mock.MagicMock()
        mock_fdopen.return_value.__enter__.return_value = mock_file
        mock_dumps.return_value = "{\"key\": \"value\"}"
        data = {"key": "value"}
        FileManager.create_json_file(self.temp_dir, data, "test_output.json", common_flag=True)
        mock_check_output_directory_path.assert_called_once_with(self.temp_dir)

    def test_create_json_file_empty_data(self):
        # 测试空数据
        with patch('msprof_analyze.prof_common.path_manager.PathManager.check_path_writeable') as mock_check_writeable:
            FileManager.create_json_file(self.temp_dir, {}, "test_output.json")
            mock_check_writeable.assert_not_called()

    @patch('msprof_analyze.prof_common.path_manager.PathManager.make_dir_safety')
    @patch('os.path.exists')
    def test_create_output_dir_overwrite(self, mock_exists, mock_make_dir):
        # 测试创建输出目录（覆盖模式）
        mock_exists.return_value = False
        FileManager.create_output_dir(self.temp_dir, is_overwrite=True)
        output_path = os.path.join(self.temp_dir, Constant.CLUSTER_ANALYSIS_OUTPUT)
        mock_exists.assert_called_once_with(output_path)
        mock_make_dir.assert_called_once_with(output_path)

    @patch('msprof_analyze.prof_common.path_manager.PathManager.remove_path_safety')
    @patch('msprof_analyze.prof_common.path_manager.PathManager.make_dir_safety')
    def test_create_output_dir_normal(self, mock_make_dir, mock_remove_dir):
        # 测试创建输出目录（正常模式）
        FileManager.create_output_dir(self.temp_dir, is_overwrite=False)
        output_path = os.path.join(self.temp_dir, Constant.CLUSTER_ANALYSIS_OUTPUT)
        mock_remove_dir.assert_called_once_with(output_path)
        mock_make_dir.assert_called_once_with(output_path)

    @patch('os.path.splitext')
    @patch('os.path.getsize')
    def test_check_file_size_csv(self, mock_getsize, mock_splitext):
        # 测试检查CSV文件大小
        self.addition_arg_manager._force = False
        mock_splitext.return_value = ("test", Constant.CSV_SUFFIX)
        mock_getsize.return_value = Constant.MAX_CSV_SIZE + 1

        with self.assertRaises(RuntimeError):
            FileManager.check_file_size(self.temp_csv_path)

    @patch('os.path.splitext')
    @patch('os.path.getsize')
    def test_check_file_size_json(self, mock_getsize, mock_splitext):
        # 测试检查JSON文件大小
        mock_splitext.return_value = ("test", ".json")
        mock_getsize.return_value = Constant.MAX_JSON_SIZE + 1

        with self.assertRaises(RuntimeError):
            FileManager.check_file_size(self.temp_json_path)

    @patch('os.path.islink')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_check_db_path_valid_force(self, mock_getsize, mock_exists, mock_islink):
        # 测试检查数据库路径（使用force参数）
        mock_islink.return_value = False
        mock_exists.return_value = True
        mock_getsize.return_value = Constant.MAX_READ_DB_FILE_BYTES + 1

        self.addition_arg_manager._force = True
        result = check_db_path_valid(self.temp_dir, is_create=False)
        self.assertTrue(result)

    @patch('os.path.islink')
    @patch('os.path.exists')
    @patch('msprof_analyze.prof_common.additional_args_manager.AdditionalArgsManager')
    def test_check_db_path_valid_create(self, mock_additional_args, mock_exists, mock_islink):
        # 测试检查数据库路径（创建模式）
        mock_islink.return_value = False
        mock_exists.return_value = False
        result = check_db_path_valid(self.temp_dir, is_create=True)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
