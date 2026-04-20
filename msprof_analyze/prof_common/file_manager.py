# Copyright (c) 2023, Huawei Technologies Co., Ltd.
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

import os
import csv
import json

import yaml
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()


class FileManager:
    @classmethod
    def read_json_file(cls, file_path: str) -> dict:
        PathManager.check_input_file_path(file_path)
        base_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        result_data = {}
        if file_size <= 0:
            return result_data
        if not AdditionalArgsManager().force and file_size > Constant.MAX_JSON_SIZE:
            logger.warning(f"The file({file_path}) size is {file_size} Byte, exceeds the preset max value. "
                           f"{Constant.FORCE_BYPASSES_SECURITY}")
            return result_data
        try:
            with open(file_path, "r") as json_file:
                result_data = json.loads(json_file.read())
        except Exception as e:
            raise RuntimeError(f"Failed to read the file: {base_name}, reason is {str(e)}") from e
        return result_data

    @classmethod
    def read_csv_file(cls, file_path: str, class_bean: any = None) -> list:
        PathManager.check_input_file_path(file_path)
        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            return []
        if not AdditionalArgsManager().force and file_size > Constant.MAX_CSV_SIZE:
            logger.warning(f"The file({file_path}) size is {file_size} Byte, exceeds the preset max value. "
                           f"{Constant.FORCE_BYPASSES_SECURITY}")
            return []
        result_data = []
        try:
            with open(file_path, newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    row_data = class_bean(row) if class_bean else row
                    result_data.append(row_data)
        except Exception as e:
            msg = f"Failed to read the file: {file_path}, reason is {str(e)}"
            raise RuntimeError(msg) from e
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
        if file_size <= 0:
            return {}
        if not AdditionalArgsManager().force and file_size > Constant.MAX_JSON_SIZE:
            raise RuntimeError(f"The file({base_name}) size exceeds the preset max value. "
                               f"{Constant.FORCE_BYPASSES_SECURITY}")

        try:
            with open(file_path, "r", encoding="utf-8") as yaml_file:
                result_data = yaml.safe_load(yaml_file)
        except Exception as e:
            raise RuntimeError(f"Failed to read the file: {base_name}, reason is {str(e)}") from e
        return result_data

    @classmethod
    def read_common_file(cls, file_path: str) -> str:
        PathManager.check_input_file_path(file_path)
        base_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            raise RuntimeError(f"The file({base_name}) size is less than or equal to 0.")
        if not AdditionalArgsManager().force and file_size > Constant.MAX_COMMON_SIZE:
            raise RuntimeError(f"The file({base_name}) size exceeds the preset max value. "
                               f"{Constant.FORCE_BYPASSES_SECURITY}")
        try:
            with open(file_path, 'r') as f:
                content = f.read()
        except Exception as e:
            raise RuntimeError(f"Failed to read the file: {base_name}, reason is {str(e)}") from e
        return content

    @classmethod
    def create_common_file(cls, file_path: str, content: str) -> None:
        base_name = os.path.basename(file_path)
        PathManager.check_output_directory_path(os.path.dirname(file_path))
        try:
            with os.fdopen(
                    os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, Constant.FILE_AUTHORITY),
                    'w') as file:
                file.write(content)
        except Exception as e:
            raise RuntimeError(f"Can't create file: {base_name}") from e

    @classmethod
    def create_csv_from_dataframe(cls, file_path: str, data, index) -> None:
        base_name = os.path.basename(file_path)
        PathManager.check_output_directory_path(os.path.dirname(file_path))
        try:
            data.to_csv(file_path, index=index)
        except Exception as e:
            raise RuntimeError(f"Can't create file: {base_name}") from e
        os.chmod(file_path, Constant.FILE_AUTHORITY)

    @classmethod
    def create_csv_file(cls, profiler_path: str, data: list, file_name: str, headers: list = None) -> None:
        if not data:
            return
        output_path = os.path.join(
            profiler_path, Constant.CLUSTER_ANALYSIS_OUTPUT)
        output_file = os.path.join(output_path, file_name)
        base_name = os.path.basename(output_file)
        PathManager.check_output_directory_path(output_path)
        try:
            with os.fdopen(
                    os.open(output_file, os.O_WRONLY | os.O_CREAT, Constant.FILE_AUTHORITY),
                    'w', newline=""
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
                    os.open(output_file, os.O_WRONLY | os.O_CREAT, Constant.FILE_AUTHORITY), 'w'
            ) as file:
                file.write(json.dumps(data))
        except Exception as e:
            raise RuntimeError(f"Can't create the file: {base_name}") from e

    @classmethod
    def create_output_dir(cls, collection_path: str, is_overwrite: bool = False) -> None:
        output_path = os.path.join(
            collection_path, Constant.CLUSTER_ANALYSIS_OUTPUT)
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
            raise RuntimeError(f"The file({base_name}) size exceeds the preset max value. "
                               f"{Constant.FORCE_BYPASSES_SECURITY}")


def check_db_path_valid(path: str, is_create: bool = False, max_size: int = Constant.MAX_READ_DB_FILE_BYTES) -> bool:
    if os.path.islink(path):
        logger.error('The db file path: %s is link. Please check the path', path)
        return False
    if not is_create and os.path.exists(path) and os.path.getsize(path) > max_size:
        if not AdditionalArgsManager().force:
            logger.error('The db file: %s is too large to read. Please check the file', path)
            return False
    return True
