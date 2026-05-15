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
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.utils.utils import check_path_valid

logger = get_logger()


class FileOpen:
    """
    open and read file
    """

    def __init__(self: any, file_path: str, mode: str = "r", max_size: int = Constant.MAX_READ_FILE_BYTES) -> None:
        self.file_path = file_path
        self.file_reader = None
        self.mode = mode
        self.max_size = max_size

    def __enter__(self: any) -> any:
        check_path_valid(self.file_path, True, max_size=self.max_size)
        self.file_reader = open(self.file_path, self.mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_reader:
            self.file_reader.close()


class FdOpen:
    """
    creat and write file
    """

    def __init__(self: any, file_path: str, flags: int = Constant.WRITE_FLAGS, mode: int = Constant.WRITE_MODES,
                 operate: str = "w", newline: str = None) -> None:
        self.file_path = file_path
        self.flags = flags
        self.newline = newline
        self.mode = mode
        self.operate = operate
        self.fd = None
        self.file_open = None

    def __enter__(self: any) -> any:
        file_dir = os.path.dirname(self.file_path)
        check_dir_writable(file_dir)


        self.fd = os.open(self.file_path, self.flags, self.mode)
        if self.newline is None:
            self.file_open = os.fdopen(self.fd, self.operate)
        else:
            self.file_open = os.fdopen(self.fd, self.operate, newline=self.newline)
        return self.file_open

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_open:
            try:
                self.file_open.close()
            except Exception:
                os.close(self.fd)
        elif self.fd:
            os.close(self.fd)


def check_dir_writable(path: str, is_file: bool = False) -> None:
    """
    check path is dir and writable
    """
    check_path_valid(path, is_file)
    if not os.access(path, os.W_OK):
        raise PermissionError(f"The path \"{path}\" does not have permission to write. "
                              f"Please check that the path is writeable.")