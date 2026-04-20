# Copyright (c) 2024, Huawei Technologies Co., Ltd.
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
import re
import shutil
import platform

from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager

logger = get_logger()


def is_root():
    return os.name == 'nt' or os.getuid() == 0


class PathManager:
    MAX_PATH_LENGTH = 4096
    MAX_FILE_NAME_LENGTH = 255
    DATA_FILE_AUTHORITY = 0o640
    DATA_DIR_AUTHORITY = 0o750
    WINDOWS = "windows"

    @classmethod
    def check_input_directory_path(cls, path: str):
        """
        Function Description:
            check whether the path is valid, some businesses can accept a path that does not exist,
            so the function do not verify whether the path exists
        Parameter:
            path: the path to check, whether the incoming path is absolute or relative depends on the business
        Exception Description:
            when invalid data throw exception
        """
        cls.input_path_common_check(path)
        base_name = os.path.basename(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"The file {path} does not exists.")
        if os.path.isfile(path):
            msg = f"Invalid input path which is a file path: {base_name}"
            raise RuntimeError(msg)
        cls.check_path_owner_consistent([path])
        cls.check_path_readable(path)
        cls.check_path_executable(path)
        cls.check_others_writable(path)

    @classmethod
    def check_input_file_path(cls, path: str):
        """
        Function Description:
            check whether the file path is valid, some businesses can accept a path that does not exist,
            so the function do not verify whether the path exists
        Parameter:
            path: the file path to check, whether the incoming path is absolute or relative depends on the business
        Exception Description:
            when invalid data throw exception
        """
        cls.input_path_common_check(path)
        base_name = os.path.basename(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"The file {path} does not exists.")
        if os.path.isdir(path):
            msg = f"Invalid input path which is a directory path: {base_name}"
            raise RuntimeError(msg)
        cls.check_path_owner_consistent([path])
        cls.check_path_readable(path)
        cls.check_others_writable(path)

    @classmethod
    def check_output_directory_path(cls, path: str):
        cls.input_path_common_check(path)
        base_name = os.path.basename(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"The file {path} does not exists.")
        if os.path.isfile(path):
            msg = f"Invalid input path which is a file path: {base_name}"
            raise RuntimeError(msg)
        cls.check_path_owner_consistent([path])
        cls.check_path_writeable(path)
        cls.check_path_executable(path)
        cls.check_others_writable(path)

    @classmethod
    def check_path_length(cls, path: str):
        if len(path) > cls.MAX_PATH_LENGTH:
            raise RuntimeError("Length of input path exceeds the limit.")
        path_split_list = path.split("/")
        for path in path_split_list:
            path_list = path.split("\\")
            for name in path_list:
                if len(name) > cls.MAX_FILE_NAME_LENGTH:
                    raise RuntimeError("Length of input path exceeds the limit.")

    @classmethod
    def input_path_common_check(cls, path: str):
        cls.check_path_length(path)

        if os.path.islink(path):
            msg = f"Invalid input path which is a soft link."
            raise RuntimeError(msg)

        pattern = r'(\.|:|\\|/|_|-|\s|[~0-9a-zA-Z\u4e00-\u9fa5])+'
        if not re.fullmatch(pattern, path):
            illegal_pattern = r'([^\.\:\\\/\_\-\s~0-9a-zA-Z\u4e00-\u9fa5])+'
            invalid_obj = re.search(illegal_pattern, path).group()
            msg = f"Invalid path which has illagal characters \"{invalid_obj}\"."
            raise RuntimeError(msg)

        path_split_list = path.split("/")
        for path in path_split_list:
            path_list = path.split("\\")
            for name in path_list:
                if len(name) > cls.MAX_FILE_NAME_LENGTH:
                    raise RuntimeError("Length of input path exceeds the limit.")

    @classmethod
    def check_path_owner_consistent(cls, path_list: list):
        """
        Function Description:
            check whether the path belong to process owner
        Parameter:
            path: the path to check
        Exception Description:
            when invalid path, prompt the user
        """
        if platform.system().lower() == cls.WINDOWS or AdditionalArgsManager().force or is_root():
            return
        for path in path_list:
            if not os.path.exists(path):
                continue
            if os.stat(path).st_uid != os.getuid():
                logger.warning(f"The path does not belong to you: {path}. {Constant.FORCE_BYPASSES_SECURITY}")

    @classmethod
    def check_path_writeable(cls, path):
        """
        Function Description:
            check whether the path is writable
        Parameter:
            path: the path to check
        Exception Description:
            when invalid data throw exception
        """
        if os.path.islink(path):
            msg = f"Invalid path which is a soft link."
            raise RuntimeError(msg)
        if AdditionalArgsManager().force or is_root():
            return
        if not os.access(path, os.W_OK):
            msg = f"The path is not writable: {path}"
            raise RuntimeError(msg)

    @classmethod
    def check_path_readable(cls, path):
        """
        Function Description:
            check whether the path is readable
        Parameter:
            path: the path to check
        Exception Description:
            when invalid data throw exception
        """
        if not os.path.exists(path):
            msg = f"The path does not exist: {path}"
            raise FileNotFoundError(msg)
        if os.path.islink(path):
            msg = f"Invalid path which is a soft link."
            raise RuntimeError(msg)
        if AdditionalArgsManager().force or is_root():
            return
        if not os.access(path, os.R_OK):
            msg = f"The path is not readable: {path}"
            raise RuntimeError(msg)

    @classmethod
    def check_path_executable(cls, path):
        if AdditionalArgsManager().force or is_root():
            return
        if not os.access(path, os.X_OK):
            raise RuntimeError(f"The path is not executable: {path}")

    @classmethod
    def check_others_writable(cls, path):
        if AdditionalArgsManager().force or is_root():
            return
        st = os.stat(path)
        if st.st_mode & 0o022:
            logger.warning(f"The path is writable by others: {path}. {Constant.FORCE_BYPASSES_SECURITY}")

    @classmethod
    def remove_path_safety(cls, path: str):
        if not os.path.exists(path):
            return
        base_name = os.path.basename(path)
        msg = f"Failed to remove path: {base_name}"
        cls.check_path_writeable(path)
        if os.path.islink(path):
            raise RuntimeError(msg)
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
            except Exception as err:
                raise RuntimeError(msg) from err

    @classmethod
    def make_dir_safety(cls, path: str):
        base_name = os.path.basename(path)
        msg = f"Failed to make directory: {base_name}"
        if os.path.exists(path):
            PathManager.check_output_directory_path(path)
            return
        try:
            os.makedirs(path, mode=cls.DATA_DIR_AUTHORITY, exist_ok=True)
        except Exception as err:
            raise RuntimeError(msg) from err

    @classmethod
    def create_file_safety(cls, path: str):
        base_name = os.path.basename(path)
        msg = f"Failed to create file: {base_name}"
        if os.path.islink(path):
            raise RuntimeError(msg)
        if os.path.exists(path):
            return
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT, cls.DATA_FILE_AUTHORITY))
        except Exception as err:
            raise RuntimeError(msg) from err

    @classmethod
    def get_realpath(cls, path: str) -> str:
        if not path:
            raise RuntimeError("The path is empty. Please enter a valid path.")
        if os.path.islink(path):
            msg = f"Invalid input path which is a soft link."
            raise RuntimeError(msg)
        return os.path.abspath(path)

    @classmethod
    def check_file_size(cls, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The file {file_path} does not exists.")
        if AdditionalArgsManager().force:
            return
        file_size = os.path.getsize(file_path)
        if file_size > Constant.MAX_FILE_SIZE_5_GB:
            raise RuntimeError(f"The file({file_path}) size is {file_size} Byte, exceeds the preset max value. "
                               f"{Constant.FORCE_BYPASSES_SECURITY}")

    @classmethod
    def expanduser_for_cli(cls, ctx, parm, str_name: str):
        return cls.expanduser_for_argumentparser(str_name)

    @classmethod
    def expanduser_for_argumentparser(cls, str_name: str):
        # None 对应 参数未赋值的场景
        return str_name if str_name is None else os.path.expanduser(str_name.lstrip('='))

    @classmethod
    def limited_depth_walk(cls, path, max_depth=10, *args, **kwargs):
        base_depth = path.count(os.sep)
        for root, dirs, files in os.walk(path, *args, **kwargs):
            if root.count(os.sep) - base_depth > max_depth:
                dirs.clear()
                continue
            yield root, dirs, files
