# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2023 Huawei Technologies Co.,Ltd.
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
import csv
import json

import yaml
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()

# SQLite database file magic number header
SQLITE_MAGIC = b"SQLite format 3\x00"


class FileManager:
    @classmethod
    def _is_empty_file(cls, file_path: str) -> bool:
        """检查文件是否为空文件（0字节）。"""
        return os.path.getsize(file_path) <= 0

    @classmethod
    def _is_valid_json_file(cls, file_path: str) -> bool:
        """轻量校验JSON文件合法性：通过文件头特征判断，不做全量解析。

        仅检测明显的非JSON特征（二进制null字节、UTF-8 BOM、首字符非法、空文件），
        深层语法错误（如截断、缺少括号）由 read_json_file 的 try-catch 兜底处理，
        避免对大文件做全量 json.loads 导致性能损耗。
        """
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(8192)
        except OSError as e:
            logger.warning("Failed to validate JSON file: %s, system error: %s", file_path, str(e))
            raise
        if not chunk:
            return False
        # 二进制文件伪装（含 null 字节）
        if b'\x00' in chunk:
            return False
        # UTF-8 BOM: json.loads 不支持 BOM，视为损坏
        if chunk.startswith(b'\xef\xbb\xbf'):
            return False
        # 去除前导空白后检查首字符
        stripped = chunk.lstrip()
        if not stripped:
            return False
        # JSON 顶层只允许 object({) 或 array([)
        return stripped[0:1] in (b'{', b'[')

    @classmethod
    def _is_valid_yaml_file(cls, file_path: str) -> bool:
        """通过尝试解析来判断YAML文件是否损坏。"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
            return True
        except (yaml.YAMLError, UnicodeDecodeError, ValueError):
            return False
        except OSError as e:
            logger.warning("Failed to validate YAML file: %s, system error: %s", file_path, str(e))
            raise

    @classmethod
    def _is_valid_csv_file(cls, file_path: str) -> bool:
        """通过尝试读取第一条记录来判断CSV文件是否损坏。"""
        # 首先检查二进制头部是否包含 null 字节（非纯文本文件）
        try:
            with open(file_path, "rb") as f:
                # 读取前 4KB 检查 null 字节，足够覆盖常见文件头
                chunk = f.read(4096)
                if b'\x00' in chunk:
                    return False
        except Exception:
            return False

        try:
            with open(file_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                try:
                    next(reader)
                except StopIteration:
                    # 无数据行，检查是否至少有有效表头
                    if reader.fieldnames is None:
                        return False
            return True
        except Exception:
            return False

    @classmethod
    def _is_valid_sqlite_file(cls, file_path: str) -> bool:
        """通过魔数头规则判断SQLite/DB文件是否损坏。"""
        try:
            with open(file_path, "rb") as f:
                header = f.read(len(SQLITE_MAGIC))
            return header == SQLITE_MAGIC
        except Exception:
            return False

    @classmethod
    def read_json_file(cls, file_path: str) -> dict:
        PathManager.check_input_file_path(file_path)
        base_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        result_data = {}
        if cls._is_empty_file(file_path):
            logger.warning("Empty file detected, skip: %s", file_path)
            return result_data
        if not AdditionalArgsManager().force and file_size > Constant.MAX_JSON_SIZE:
            logger.warning(
                "The file(%s) size is %s Byte, exceeds the preset max value. %s",
                file_path,
                file_size,
                Constant.FORCE_BYPASSES_SECURITY,
            )
            return result_data
        try:
            with open(file_path, "r", encoding="utf-8") as json_file:
                result_data = json.loads(json_file.read())
        except (OSError, PermissionError) as e:
            logger.warning("Failed to access the JSON file: %s, reason is %s", base_name, str(e))
            raise
        except Exception as e:
            logger.warning("Failed to read the JSON file: %s, reason is %s, skip it.", base_name, str(e))
            return result_data
        return result_data

    @classmethod
    def read_csv_file(cls, file_path: str, class_bean: any = None) -> list:
        PathManager.check_input_file_path(file_path)
        result_data = []
        file_size = os.path.getsize(file_path)
        if cls._is_empty_file(file_path):
            logger.warning("Empty file detected, skip: %s", file_path)
            return result_data
        if not AdditionalArgsManager().force and file_size > Constant.MAX_CSV_SIZE:
            logger.warning(
                "The file(%s) size is %s Byte, exceeds the preset max value. %s",
                file_path,
                file_size,
                Constant.FORCE_BYPASSES_SECURITY,
            )
            return result_data
        if not cls._is_valid_csv_file(file_path):
            logger.warning("Corrupted CSV file detected, skip: %s", file_path)
            return result_data

        try:
            with open(file_path, newline="", encoding="utf-8") as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    row_data = class_bean(row) if class_bean else row
                    result_data.append(row_data)
        except Exception as e:
            logger.warning("Failed to read the CSV file: %s, reason is %s, skip it.", file_path, str(e))
            return result_data
        return result_data

    @classmethod
    def check_json_type(cls, file_path: str) -> str:
        json_data = cls.read_json_file(file_path)
        if isinstance(json_data, dict):
            return Constant.GPU
        return Constant.NPU

    @classmethod
    def read_yaml_file(cls, file_path: str) -> dict:
        PathManager.check_input_file_path(file_path)
        base_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        result_data = {}
        if cls._is_empty_file(file_path):
            logger.warning("Empty file detected, skip: %s", file_path)
            return result_data
        if not AdditionalArgsManager().force and file_size > Constant.MAX_JSON_SIZE:
            logger.warning(
                "The file(%s) size exceeds the preset max value. %s, skip it.",
                base_name,
                Constant.FORCE_BYPASSES_SECURITY,
            )
            return result_data
        try:
            with open(file_path, "r", encoding="utf-8") as yaml_file:
                result_data = yaml.safe_load(yaml_file)
        except (OSError, PermissionError) as e:
            logger.warning("Failed to access the YAML file: %s, reason is %s", base_name, str(e))
            raise
        except Exception as e:
            logger.warning("Failed to read the YAML file: %s, reason is %s, skip it.", base_name, str(e))
            return result_data
        return result_data

    @classmethod
    def read_common_file(cls, file_path: str) -> str:
        PathManager.check_input_file_path(file_path)
        base_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        result_data = ""
        if cls._is_empty_file(file_path):
            logger.warning("Empty file detected, skip: %s", file_path)
            return result_data
        if not AdditionalArgsManager().force and file_size > Constant.MAX_COMMON_SIZE:
            logger.warning(
                "The file(%s) size exceeds the preset max value. %s, skip it.",
                base_name,
                Constant.FORCE_BYPASSES_SECURITY,
            )
            return result_data
        try:
            with open(file_path, 'r', encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning("Failed to read the common file: %s, reason is %s, skip it.", base_name, str(e))
            return result_data
        return content

    @classmethod
    def create_common_file(cls, file_path: str, content: str) -> None:
        base_name = os.path.basename(file_path)
        PathManager.check_output_directory_path(os.path.dirname(file_path))
        try:
            with os.fdopen(
                os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, Constant.FILE_AUTHORITY),
                'w',
                encoding='utf-8',
            ) as file:
                file.write(content)
        except Exception as e:
            raise RuntimeError(f"Can't create file: {base_name}") from e

    @classmethod
    def create_csv_from_dataframe(cls, file_path: str, data, index) -> None:
        base_name = os.path.basename(file_path)
        PathManager.check_output_directory_path(os.path.dirname(file_path))
        try:
            data.to_csv(file_path, index=index, encoding='utf-8')
        except Exception as e:
            raise RuntimeError(f"Can't create file: {base_name}") from e

    @classmethod
    def create_csv_file(cls, profiler_path: str, data: list, file_name: str, headers: list = None) -> None:
        if not data:
            return
        output_path = os.path.join(profiler_path, Constant.CLUSTER_ANALYSIS_OUTPUT)
        output_file = os.path.join(output_path, file_name)
        base_name = os.path.basename(output_file)
        PathManager.check_output_directory_path(output_path)
        try:
            with os.fdopen(
                os.open(output_file, os.O_WRONLY | os.O_CREAT, Constant.FILE_AUTHORITY),
                'w',
                newline="",
                encoding='utf-8',
            ) as file:
                writer = csv.writer(file)
                if headers:
                    writer.writerow(headers)
                writer.writerows(data)
        except Exception as e:
            raise RuntimeError(f"Can't create file: {base_name}") from e

    @classmethod
    def create_json_file(cls, profiler_path: str, data: dict, file_name: str, common_flag: bool = False) -> None:
        if not data:
            return
        if not common_flag:
            output_path = os.path.join(profiler_path, Constant.CLUSTER_ANALYSIS_OUTPUT)
            output_file = os.path.join(output_path, file_name)
            PathManager.check_output_directory_path(output_path)
        else:
            output_file = os.path.join(profiler_path, file_name)
            PathManager.check_output_directory_path(profiler_path)
        base_name = os.path.basename(output_file)
        try:
            with os.fdopen(
                os.open(output_file, os.O_WRONLY | os.O_CREAT, Constant.FILE_AUTHORITY), 'w', encoding='utf-8'
            ) as file:
                file.write(json.dumps(data))
        except Exception as e:
            raise RuntimeError(f"Can't create the file: {base_name}") from e

    @classmethod
    def create_output_dir(cls, collection_path: str, is_overwrite: bool = False) -> None:
        output_path = os.path.join(collection_path, Constant.CLUSTER_ANALYSIS_OUTPUT)
        if is_overwrite:
            if not os.path.exists(output_path):
                PathManager.make_dir_safety(output_path)
            return
        PathManager.remove_path_safety(output_path)
        PathManager.make_dir_safety(output_path)

    @classmethod
    def check_file_size(cls, file_path):
        suffix = os.path.splitext(file_path)
        base_name = os.path.join(file_path)
        if suffix[1] == Constant.CSV_SUFFIX:
            limit_size = Constant.MAX_CSV_SIZE
        else:
            limit_size = Constant.MAX_JSON_SIZE
        file_size = os.path.getsize(file_path)
        if not AdditionalArgsManager().force and file_size > limit_size:
            raise RuntimeError(
                f"The file({base_name}) size exceeds the preset max value. {Constant.FORCE_BYPASSES_SECURITY}"
            )


def check_db_path_valid(path: str, is_create: bool = False, max_size: int = Constant.MAX_READ_DB_FILE_BYTES) -> bool:
    if os.path.islink(path):
        logger.warning('The db file path: %s is link. Please check the path', path)
    if not is_create and os.path.exists(path) and os.path.getsize(path) > max_size:
        if not AdditionalArgsManager().force:
            logger.error('The db file: %s is too large to read. Please check the file', path)
            return False
    if not is_create and os.path.exists(path) and os.path.getsize(path) > 0:
        if not FileManager._is_valid_sqlite_file(path):
            logger.warning('The db file: %s is corrupted (invalid SQLite header), skip it.', path)
            return False
    return True
