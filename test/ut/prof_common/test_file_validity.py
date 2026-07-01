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
"""
集成测试：验证 FileManager 文件合法性校验功能
- 空文件/0字节文件自动跳过
- 损坏文件自动跳过（JSON/YAML/CSV/SQLite）
- 无效文件不中断分析流程
"""

import csv
import json
import os
import sqlite3
import unittest

from msprof_analyze.prof_common.file_manager import FileManager, check_db_path_valid, SQLITE_MAGIC
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager


class TestFileValidityCheck(unittest.TestCase):
    """测试文件合法性校验方法"""

    def setUp(self):
        AdditionalArgsManager._instance = {}
        self.temp_dir = os.path.join(os.path.dirname(__file__), "DT_FileValidity")
        os.makedirs(self.temp_dir)

        # 正常文件
        self.valid_json = os.path.join(self.temp_dir, "valid.json")
        with open(self.valid_json, "w", encoding="utf-8") as f:
            json.dump({"key": "value", "items": [1, 2, 3]}, f)

        self.valid_yaml = os.path.join(self.temp_dir, "valid.yaml")
        with open(self.valid_yaml, "w", encoding="utf-8") as f:
            f.write("key: value\nitems:\n  - 1\n  - 2\n")

        self.valid_csv = os.path.join(self.temp_dir, "valid.csv")
        with open(self.valid_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name", "value"])
            writer.writerow(["1", "test", "100"])

        self.valid_db = os.path.join(self.temp_dir, "valid.db")
        conn = sqlite3.connect(self.valid_db)
        conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'hello')")
        conn.commit()
        conn.close()

        # 空文件（0字节）
        self.empty_json = os.path.join(self.temp_dir, "empty.json")
        with open(self.empty_json, "wb"):
            pass
        self.empty_yaml = os.path.join(self.temp_dir, "empty.yaml")
        with open(self.empty_yaml, "wb"):
            pass
        self.empty_csv = os.path.join(self.temp_dir, "empty.csv")
        with open(self.empty_csv, "wb"):
            pass
        self.empty_txt = os.path.join(self.temp_dir, "empty.txt")
        with open(self.empty_txt, "wb"):
            pass

        # 损坏JSON文件
        self.corrupted_json = os.path.join(self.temp_dir, "corrupted.json")
        with open(self.corrupted_json, "w", encoding="utf-8") as f:
            f.write("this is not valid json {{{{{")

        # 损坏YAML文件
        self.corrupted_yaml = os.path.join(self.temp_dir, "corrupted.yaml")
        with open(self.corrupted_yaml, "w", encoding="utf-8") as f:
            f.write("\tbad indent: : : : [[[")

        # 损坏CSV文件（二进制垃圾）
        self.corrupted_csv = os.path.join(self.temp_dir, "corrupted.csv")
        with open(self.corrupted_csv, "wb") as f:
            f.write(b"\x00\x01\x02\x03\xff\xfe\xfd")

        # 损坏SQLite文件（魔数头错误）
        self.corrupted_db = os.path.join(self.temp_dir, "corrupted.db")
        with open(self.corrupted_db, "wb") as f:
            f.write(b"Not a valid SQLite file!")

    def tearDown(self):
        AdditionalArgsManager._instance = {}
        for file_path in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file_path))
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    # ==================== _is_empty_file 测试 ====================

    def test_is_empty_file_true(self):
        """空文件应返回 True"""
        self.assertTrue(FileManager._is_empty_file(self.empty_json))

    def test_is_empty_file_false(self):
        """正常文件应返回 False"""
        self.assertFalse(FileManager._is_empty_file(self.valid_json))

    # ==================== _is_valid_json_file 测试 ====================

    def test_valid_json_file(self):
        """合法JSON文件应返回 True"""
        self.assertTrue(FileManager._is_valid_json_file(self.valid_json))

    def test_corrupted_json_file(self):
        """损坏JSON文件应返回 False"""
        self.assertFalse(FileManager._is_valid_json_file(self.corrupted_json))

    def test_empty_json_file(self):
        """空JSON文件应返回 False（json.loads 解析空文件会失败）"""
        self.assertFalse(FileManager._is_valid_json_file(self.empty_json))

    # ==================== _is_valid_yaml_file 测试 ====================

    def test_valid_yaml_file(self):
        """合法YAML文件应返回 True"""
        self.assertTrue(FileManager._is_valid_yaml_file(self.valid_yaml))

    def test_corrupted_yaml_file(self):
        """损坏YAML文件应返回 False"""
        self.assertFalse(FileManager._is_valid_yaml_file(self.corrupted_yaml))

    def test_empty_yaml_file(self):
        """空YAML文件特殊：yaml.safe_load("") 返回 None 不抛异常"""
        result = FileManager._is_valid_yaml_file(self.empty_yaml)
        self.assertTrue(result)

    # ==================== _is_valid_csv_file 测试 ====================

    def test_valid_csv_file(self):
        """合法CSV文件应返回 True"""
        self.assertTrue(FileManager._is_valid_csv_file(self.valid_csv))

    def test_corrupted_csv_file(self):
        """损坏CSV文件（二进制垃圾）应返回 False"""
        self.assertFalse(FileManager._is_valid_csv_file(self.corrupted_csv))

    def test_empty_csv_file(self):
        """空CSV文件应返回 False（无行可读取）"""
        self.assertFalse(FileManager._is_valid_csv_file(self.empty_csv))

    # ==================== _is_valid_sqlite_file 测试 ====================

    def test_valid_sqlite_file(self):
        """合法SQLite文件应返回 True"""
        self.assertTrue(FileManager._is_valid_sqlite_file(self.valid_db))

    def test_corrupted_sqlite_file(self):
        """损坏SQLite文件（魔数不对）应返回 False"""
        self.assertFalse(FileManager._is_valid_sqlite_file(self.corrupted_db))

    def test_empty_sqlite_file(self):
        """空文件检查魔数——读取0字节，不等于魔数"""
        self.assertFalse(FileManager._is_valid_sqlite_file(self.empty_json))

    # ==================== SQLITE_MAGIC 常量测试 ====================

    def test_sqlite_magic_value(self):
        """验证 SQLITE_MAGIC 常量值正确"""
        self.assertEqual(SQLITE_MAGIC, b"SQLite format 3\x00")
        self.assertEqual(len(SQLITE_MAGIC), 16)


class TestFileManagerReadWithInvalidFiles(unittest.TestCase):
    """测试读取方法对无效文件的处理——应返回空结果，不抛异常"""

    def setUp(self):
        AdditionalArgsManager._instance = {}
        self.temp_dir = os.path.join(os.path.dirname(__file__), "DT_FileValidityRead")
        os.makedirs(self.temp_dir)

        # 正常文件
        self.valid_json = os.path.join(self.temp_dir, "valid.json")
        with open(self.valid_json, "w", encoding="utf-8") as f:
            json.dump({"key": "value", "items": [1, 2, 3]}, f)

        self.valid_yaml = os.path.join(self.temp_dir, "valid.yaml")
        with open(self.valid_yaml, "w", encoding="utf-8") as f:
            f.write("key: value\nitems:\n  - 1\n  - 2\n")

        self.valid_csv = os.path.join(self.temp_dir, "valid.csv")
        with open(self.valid_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name", "value"])
            writer.writerow(["1", "test", "100"])

        self.valid_db = os.path.join(self.temp_dir, "valid.db")
        conn = sqlite3.connect(self.valid_db)
        conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'hello')")
        conn.commit()
        conn.close()

        # 空文件
        self.empty_json = os.path.join(self.temp_dir, "empty.json")
        with open(self.empty_json, "wb"):
            pass
        self.empty_yaml = os.path.join(self.temp_dir, "empty.yaml")
        with open(self.empty_yaml, "wb"):
            pass
        self.empty_csv = os.path.join(self.temp_dir, "empty.csv")
        with open(self.empty_csv, "wb"):
            pass
        self.empty_txt = os.path.join(self.temp_dir, "empty.txt")
        with open(self.empty_txt, "wb"):
            pass

        # 损坏文件
        self.corrupted_json = os.path.join(self.temp_dir, "corrupted.json")
        with open(self.corrupted_json, "w", encoding="utf-8") as f:
            f.write("this is not valid json {{{{{")

        self.corrupted_yaml = os.path.join(self.temp_dir, "corrupted.yaml")
        with open(self.corrupted_yaml, "w", encoding="utf-8") as f:
            f.write("\tbad indent: : : : [[[")

        self.corrupted_csv = os.path.join(self.temp_dir, "corrupted.csv")
        with open(self.corrupted_csv, "wb") as f:
            f.write(b"\x00\x01\x02\x03\xff\xfe\xfd")

        self.corrupted_db = os.path.join(self.temp_dir, "corrupted.db")
        with open(self.corrupted_db, "wb") as f:
            f.write(b"Not a valid SQLite file!")

    def tearDown(self):
        AdditionalArgsManager._instance = {}
        for file_path in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file_path))
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    # ==================== read_json_file 测试 ====================

    def test_read_valid_json(self):
        """正常JSON文件应正确读取"""
        result = FileManager.read_json_file(self.valid_json)
        self.assertEqual(result, {"key": "value", "items": [1, 2, 3]})

    def test_read_empty_json_no_crash(self):
        """空JSON文件应返回 {} 不抛异常"""
        result = FileManager.read_json_file(self.empty_json)
        self.assertEqual(result, {})

    def test_read_corrupted_json_no_crash(self):
        """损坏JSON文件应返回 {} 不抛异常"""
        result = FileManager.read_json_file(self.corrupted_json)
        self.assertEqual(result, {})

    # ==================== read_yaml_file 测试 ====================

    def test_read_valid_yaml(self):
        """正常YAML文件应正确读取"""
        result = FileManager.read_yaml_file(self.valid_yaml)
        self.assertEqual(result, {"key": "value", "items": [1, 2]})

    def test_read_empty_yaml_no_crash(self):
        """空YAML文件应返回 {} 不抛异常"""
        result = FileManager.read_yaml_file(self.empty_yaml)
        self.assertEqual(result, {})

    def test_read_corrupted_yaml_no_crash(self):
        """损坏YAML文件应返回 {} 不抛异常"""
        result = FileManager.read_yaml_file(self.corrupted_yaml)
        self.assertEqual(result, {})

    # ==================== read_csv_file 测试 ====================

    def test_read_valid_csv(self):
        """正常CSV文件应正确读取"""
        result = FileManager.read_csv_file(self.valid_csv)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "1")
        self.assertEqual(result[0]["name"], "test")

    def test_read_empty_csv_no_crash(self):
        """空CSV文件应返回 [] 不抛异常"""
        result = FileManager.read_csv_file(self.empty_csv)
        self.assertEqual(result, [])

    def test_read_corrupted_csv_no_crash(self):
        """损坏CSV文件应返回 [] 不抛异常"""
        result = FileManager.read_csv_file(self.corrupted_csv)
        self.assertEqual(result, [])

    # ==================== read_common_file 测试 ====================

    def test_read_empty_common_file_no_crash(self):
        """空普通文件应返回 "" 不抛异常"""
        result = FileManager.read_common_file(self.empty_txt)
        self.assertEqual(result, "")

    # ==================== check_db_path_valid 测试 ====================

    def test_check_db_valid(self):
        """合法SQLite文件应返回 True"""
        self.assertTrue(check_db_path_valid(self.valid_db))

    def test_check_db_corrupted(self):
        """损坏SQLite文件应返回 False"""
        self.assertFalse(check_db_path_valid(self.corrupted_db))

    def test_check_db_create_mode(self):
        """创建模式不检查魔数"""
        self.assertTrue(check_db_path_valid(self.corrupted_db, is_create=True))


class TestNoCrashOnAllInvalidFiles(unittest.TestCase):
    """综合测试：确保所有无效文件场景都不会导致异常中断"""

    def setUp(self):
        AdditionalArgsManager._instance = {}
        self.temp_dir = os.path.join(os.path.dirname(__file__), "DT_FileValidityCrash")
        os.makedirs(self.temp_dir)

        # 空文件
        self.empty_json = os.path.join(self.temp_dir, "empty.json")
        with open(self.empty_json, "wb"):
            pass
        self.empty_yaml = os.path.join(self.temp_dir, "empty.yaml")
        with open(self.empty_yaml, "wb"):
            pass
        self.empty_csv = os.path.join(self.temp_dir, "empty.csv")
        with open(self.empty_csv, "wb"):
            pass
        self.empty_txt = os.path.join(self.temp_dir, "empty.txt")
        with open(self.empty_txt, "wb"):
            pass

        # 损坏文件
        self.corrupted_json = os.path.join(self.temp_dir, "corrupted.json")
        with open(self.corrupted_json, "w", encoding="utf-8") as f:
            f.write("this is not valid json {{{{{")

        self.corrupted_yaml = os.path.join(self.temp_dir, "corrupted.yaml")
        with open(self.corrupted_yaml, "w", encoding="utf-8") as f:
            f.write("\tbad indent: : : : [[[")

        self.corrupted_csv = os.path.join(self.temp_dir, "corrupted.csv")
        with open(self.corrupted_csv, "wb") as f:
            f.write(b"\x00\x01\x02\x03\xff\xfe\xfd")

        self.corrupted_db = os.path.join(self.temp_dir, "corrupted.db")
        with open(self.corrupted_db, "wb") as f:
            f.write(b"Not a valid SQLite file!")

    def tearDown(self):
        AdditionalArgsManager._instance = {}
        for file_path in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file_path))
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def test_all_invalid_files_no_exception(self):
        """遍历所有无效文件，任何读取操作都不应抛出异常"""
        test_cases = [
            (FileManager.read_json_file, self.empty_json, dict),
            (FileManager.read_json_file, self.corrupted_json, dict),
            (FileManager.read_yaml_file, self.empty_yaml, dict),
            (FileManager.read_yaml_file, self.corrupted_yaml, dict),
            (FileManager.read_csv_file, self.empty_csv, list),
            (FileManager.read_csv_file, self.corrupted_csv, list),
            (FileManager.read_common_file, self.empty_txt, str),
        ]

        for method, file_path, expected_type in test_cases:
            with self.subTest(method=method.__name__, file=os.path.basename(file_path)):
                try:
                    result = method(file_path)
                    self.assertIsInstance(
                        result,
                        expected_type,
                        f"{method.__name__}({os.path.basename(file_path)}) should return {expected_type}",
                    )
                except Exception as e:
                    self.fail(f"{method.__name__}({os.path.basename(file_path)}) raised {type(e).__name__}: {e}")

    def test_db_validity_no_exception(self):
        """check_db_path_valid 对损坏文件不应抛异常，应返回 False"""
        try:
            result = check_db_path_valid(self.corrupted_db)
            self.assertFalse(result)
        except Exception as e:
            self.fail(f"check_db_path_valid raised {type(e).__name__}: {e}")


class TestFileValidityEdgeCases(unittest.TestCase):
    """边界情况测试：超大文件头、特殊编码、截断文件等"""

    def setUp(self):
        AdditionalArgsManager._instance = {}
        self.temp_dir = os.path.join(os.path.dirname(__file__), "DT_FileValidityEdge")
        os.makedirs(self.temp_dir)

    def tearDown(self):
        AdditionalArgsManager._instance = {}
        for file_path in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, file_path))
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

    def _create_file(self, name, content, mode="w"):
        path = os.path.join(self.temp_dir, name)
        if 'b' in mode:
            with open(path, mode) as f:  # pylint: disable=unspecified-encoding
                f.write(content)
        else:
            with open(path, mode, encoding="utf-8") as f:
                f.write(content)
        return path

    # ==================== JSON 边界情况 ====================

    def test_json_truncated_incomplete(self):
        """截断JSON：{"key": 缺少闭合括号。
        轻量校验仅看头部特征（首字符{）通过校验；
        深层语法错误由 read_json_file 的 try-catch 兜底返回空。
        """
        path = self._create_file("truncated.json", '{"key":')
        self.assertTrue(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, {})

    def test_json_array_not_dict(self):
        """合法JSON数组（非字典）应通过校验"""
        path = self._create_file("array.json", '[1, 2, 3]')
        self.assertTrue(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, [1, 2, 3])

    def test_json_only_whitespace(self):
        """仅含空白字符的JSON文件"""
        path = self._create_file("whitespace.json", '   \n\t\r\n   ')
        self.assertFalse(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, {})

    def test_json_utf8_bom_header(self):
        """带UTF-8 BOM头的JSON文件——json.loads 不支持BOM，应视为损坏"""
        path = self._create_file("bom.json", '\ufeff{"key": "value"}', mode="w")
        self.assertFalse(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, {})

    def test_json_utf16_encoded(self):
        """UTF-16 LE编码的JSON文件——应解析失败"""
        path = self._create_file("utf16.json", '{"key": "value"}'.encode('utf-16-le'), mode="wb")
        self.assertFalse(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, {})

    def test_json_null_byte_in_middle(self):
        """JSON内容中间包含null字节"""
        path = self._create_file("nullbyte.json", b'{"key":\x00"value"}', mode="wb")
        self.assertFalse(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, {})

    def test_json_binary_disguised(self):
        """二进制文件伪装成JSON（PNG头）"""
        path = self._create_file("fake.json", b'\x89PNG\r\n\x1a\n' + b'\x00' * 100, mode="wb")
        self.assertFalse(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, {})

    def test_json_huge_header(self):
        """超大JSON文件头：100KB的合法JSON"""
        huge_content = json.dumps({"key": "x" * 100000})
        path = self._create_file("huge.json", huge_content)
        self.assertTrue(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(len(result["key"]), 100000)

    # ==================== YAML 边界情况 ====================

    def test_yaml_only_comments(self):
        """仅含注释的YAML文件"""
        path = self._create_file("comments.yaml", "# just a comment\n# another comment\n")
        self.assertTrue(FileManager._is_valid_yaml_file(path))

    def test_yaml_null_byte_in_middle(self):
        """YAML内容中间包含null字节"""
        path = self._create_file("nullbyte.yaml", b'key: \x00value\n', mode="wb")
        self.assertFalse(FileManager._is_valid_yaml_file(path))
        result = FileManager.read_yaml_file(path)
        self.assertEqual(result, {})

    def test_yaml_deeply_nested(self):
        """深层嵌套的合法YAML"""
        content = "root:\n" + "".join(f"  child{i}: value{i}\n" for i in range(100))
        path = self._create_file("deep.yaml", content)
        self.assertTrue(FileManager._is_valid_yaml_file(path))

    # ==================== CSV 边界情况 ====================

    def test_csv_header_only_no_data(self):
        """仅含表头无数据的CSV——应通过校验"""
        path = self._create_file("headeronly.csv", "id,name,value\n")
        self.assertTrue(FileManager._is_valid_csv_file(path))
        result = FileManager.read_csv_file(path)
        self.assertEqual(result, [])

    def test_csv_null_byte_in_middle(self):
        """CSV内容中间包含null字节"""
        path = self._create_file("nullbyte.csv", b'id,name\n1,\x00test\n', mode="wb")
        self.assertFalse(FileManager._is_valid_csv_file(path))
        result = FileManager.read_csv_file(path)
        self.assertEqual(result, [])

    def test_csv_very_long_line(self):
        """CSV超长行（10万字符）"""
        content = "id,data\n1," + "x" * 100000 + "\n"
        path = self._create_file("longline.csv", content)
        self.assertTrue(FileManager._is_valid_csv_file(path))
        result = FileManager.read_csv_file(path)
        self.assertEqual(len(result), 1)

    def test_csv_utf16_encoded(self):
        """UTF-16 LE编码的CSV文件"""
        path = self._create_file("utf16.csv", 'id,name\n1,test\n'.encode('utf-16-le'), mode="wb")
        result = FileManager.read_csv_file(path)
        self.assertEqual(result, [])

    # ==================== SQLite 边界情况 ====================

    def test_sqlite_magic_only_15_bytes(self):
        """仅15字节的魔数头（缺少最后一个0x00）"""
        path = self._create_file("short_magic.db", b"SQLite format 3", mode="wb")
        self.assertFalse(FileManager._is_valid_sqlite_file(path))
        self.assertFalse(check_db_path_valid(path))

    def test_sqlite_magic_exact_16_bytes(self):
        """刚好16字节的完整魔数头"""
        path = self._create_file("exact_magic.db", SQLITE_MAGIC, mode="wb")
        self.assertTrue(FileManager._is_valid_sqlite_file(path))

    def test_sqlite_magic_then_garbage(self):
        """魔数正确但后续数据为垃圾"""
        path = self._create_file("magic_garbage.db", SQLITE_MAGIC + b'\x00' * 100, mode="wb")
        self.assertTrue(FileManager._is_valid_sqlite_file(path))

    def test_sqlite_magic_wrong_encoding(self):
        """魔数文字正确但编码不同（UTF-16）"""
        path = self._create_file("magic_utf16.db", 'SQLite format 3\x00'.encode('utf-16-le'), mode="wb")
        self.assertFalse(FileManager._is_valid_sqlite_file(path))

    def test_sqlite_magic_with_extra_bytes(self):
        """魔数后紧跟额外字节但仍有效"""
        path = self._create_file("magic_extra.db", SQLITE_MAGIC + b'\x00\x00\x00\x00', mode="wb")
        self.assertTrue(FileManager._is_valid_sqlite_file(path))

    # ==================== 综合边界情况 ====================

    def test_json_only_null_bytes(self):
        """仅null字节的JSON文件"""
        path = self._create_file("nulls.json", b'\x00' * 1000, mode="wb")
        self.assertFalse(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, {})

    def test_json_single_byte(self):
        """仅1字节的JSON文件：轻量校验通过首字符{，
        完整性由 read_json_file 的 try-catch 兜底返回空。
        """
        path = self._create_file("single.json", '{')
        self.assertTrue(FileManager._is_valid_json_file(path))
        result = FileManager.read_json_file(path)
        self.assertEqual(result, {})

    def test_common_file_very_large(self):
        """超大普通文件（100KB）"""
        content = "x" * 100000
        path = self._create_file("large.txt", content)
        result = FileManager.read_common_file(path)
        self.assertEqual(len(result), 100000)


if __name__ == "__main__":
    unittest.main()
