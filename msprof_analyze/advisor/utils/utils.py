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

import json

import multiprocessing as mp
import os
import queue
import re
import stat
import time
import traceback
import types
from functools import wraps
from typing import Any, Set
import ijson
import click
from tqdm import tqdm

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger, set_debug_mode
from msprof_analyze.prof_common.singleton import singleton
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()
permission_warned: Set = set()


def ignore_warning(exception: Exception = None):
    return exception


def debug_option(f):
    return click.option('--debug',
                        is_flag=True,
                        expose_value=False,
                        is_eager=True,
                        callback=set_debug_mode,
                        help="Debug Mode. Shows full stack trace when error occurs.")(f)




def lazy_property(func):
    """
    Lazy loading of class attributes.
    which is calculated only once when it is called for the first time,
    and will not be repeated for each call after that.
    """
    attr_name = "_lazy_" + func.__name__

    @property
    def _lazy_property(instance):
        if not hasattr(instance, attr_name):
            setattr(instance, attr_name, func(instance))
        return getattr(instance, attr_name)

    return _lazy_property


class CheckPathAccess:
    """
    check path access permissions
    """

    # pylint: disable=no-member
    def __init__(self, func):
        wraps(func)(self)
        self.warned = permission_warned

    def __call__(self, *args, **kwargs):
        path = args[0]
        if not os.access(path, os.R_OK) and path not in self.warned:
            logger.warning("%s can not read, check the permissions", path)
            self.warned.add(path)
        return self.__wrapped__(*args, **kwargs)

    def __get__(self, instance, cls):
        if instance is None:
            return self
        return types.MethodType(self, instance)


def walk_error_handler(error):
    """
    handle dir walk error
    """
    if error.filename not in permission_warned:
        logger.warning(error)
        permission_warned.add(error.filename)


@CheckPathAccess
def get_file_path_from_directory(path: str, check_func: Any) -> list:
    """
    get file from directory
    """
    file_list = []
    for root, _, files in PathManager.limited_depth_walk(path, onerror=walk_error_handler):
        for filename in files:
            filepath = os.path.join(root, filename)
            if check_func(filename):
                file_list.append(filepath)
    return file_list


@singleton
class Timer:
    def __init__(self):
        self.strftime = time.strftime("%Y%m%d%H%M%S", time.localtime(time.time()))


def get_analyze_processes():
    # n_processes not exposed to user through att-advisor command arguments now
    return min(int(os.getenv(Constant.ADVISOR_ANALYZE_PROCESSES, 1)), Constant.ADVISOR_MAX_PROCESSES)


def format_timeline_result(result: dict, dump_html=False):
    """
    :Param result: json for api name and stack
    :Return: json after format
    """
    format_result = {}
    if dump_html:
        result = json.loads(json.dumps(result).replace("\\r\\n", "<br/>").replace("<module>", "&lt;module>"))

    for key, stacks in result.items():
        api_name = key.split(":")[0]
        format_result[api_name] = sorted(list(stacks.items()), key=lambda stack: stack[1], reverse=True)
    return format_result


class ParallelJob:

    def __init__(self, src_func, job_params, job_name=None):
        if not callable(src_func):
            raise TypeError(f"src_func should be callable")

        if not isinstance(job_params, (list, tuple)):
            raise TypeError(f"job_params should be list or tuple")

        self.src_func = src_func
        self.job_params = job_params
        self.job_name = job_name

    def start(self, n_proccesses):

        job_queue = mp.Queue(len(self.job_params))
        completed_queue = mp.Queue()
        for i in range(len(self.job_params)):
            job_queue.put(i)

        processes = []
        listen = mp.Process(target=self.listener, args=(completed_queue, len(self.job_params),))
        listen.start()

        for _ in range(n_proccesses):
            p = mp.Process(target=self.parallel_queue, args=(job_queue, completed_queue,))
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

        completed_queue.put(None)
        listen.join()

    def listener(self, completed_queue, num):
        pbar = tqdm(total=num, position=0, leave=False, ncols=100, desc=self.job_name)
        for _ in iter(completed_queue.get, None):
            pbar.update()
        pbar.refresh()
        pbar.n = num

    def parallel_queue(self, job_queue, completed_queue):
        while True:
            try:
                if job_queue.empty():
                    break
                token = job_queue.get(timeout=1)
            except queue.Empty:
                continue
            if isinstance(self.job_params[token], (list, tuple)):
                self.src_func(*self.job_params[token])
            elif isinstance(self.job_params[token], dict):
                self.src_func(**self.job_params[token])
            else:
                self.src_func(self.job_params[token])
            completed_queue.put(token)


def load_parameter(parameter, default):
    if not os.environ.get(parameter, None):
        return default
    else:
        return os.environ.get(parameter)


def to_percent(num: float) -> str:
    """
    change float to percent format
    """
    num = num * 100
    return f"{num:.2f}%"


def safe_division(numerator, denominator):
    """Return 0 if denominator is 0."""
    return denominator and numerator / denominator


def safe_write(content, save_path, encoding=None):
    if os.path.dirname(save_path) != "":
        PathManager.make_dir_safety(os.path.dirname(save_path))

    with os.fdopen(os.open(save_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                           stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP), "w", encoding=encoding) as f:
        f.write(content)


class CheckPathAccess:
    """
    check path access permissions
    """

    # pylint: disable=no-member
    def __init__(self, func):
        wraps(func)(self)
        self.warned = permission_warned

    def __call__(self, *args, **kwargs):
        path = args[0]
        if path and not os.access(path, os.R_OK) and path not in self.warned:
            logger.warning("%s can not read, check the permissions", path)
            self.warned.add(path)
        return self.__wrapped__(*args, **kwargs)

    def __get__(self, instance, cls):
        if instance is None:
            return self
        return types.MethodType(self, instance)


@CheckPathAccess
def get_file_path_from_directory(path, check_func):
    """
    get file from directory
    """
    file_list = []

    if not path:
        return file_list

    if not os.path.isdir(path):
        logger.warning("Expected existed directory, but got %s", path)

    for root, _, files in PathManager.limited_depth_walk(path):
        for filename in files:
            filepath = os.path.join(root, filename)
            if check_func(filename):
                file_list.append(filepath)
    return file_list


def is_regex_pattern(string: str):
    """
    Check if str is a regular expression.
    """
    escaped_string = re.escape(string)
    return not (escaped_string == string)


def join_prof_path(root_dir: str, sub_dir: str) -> str:
    """
    regular expression matching method for path concatenation
    """
    if is_regex_pattern(sub_dir):
        for root, _, _ in PathManager.limited_depth_walk(root_dir, onerror=walk_error_handler):
            if re.match(sub_dir, os.path.basename(root)):
                return root
        logger.debug("Fail to get profiling path %s from local path %s by regular expression matching", sub_dir,
                     root_dir)
    else:
        sub_dir = os.path.join(root_dir, sub_dir)
        if os.path.exists(sub_dir):
            return sub_dir
        logger.debug("Fail to get profiling path %s from local path %s", sub_dir, root_dir)
    return ""


def format_excel_title(title: str) -> str:
    """
    format excel title
    """
    title = title.lower()
    title = title.replace("(us)", '')
    title = title.replace("(ns)", '')
    title = title.replace("(%)", '')
    title = title.replace(" ", "_")

    # 将kernel_details中的列名转为与op_summary_x.csv中一致
    kernel_details_col_name_map = {
        "name": "op_name",
        "type": "op_type",
        "accelerator_core": "task_type",
        "start_time": "task_start_time",
        "duration": "task_duration",
        "wait_time": "task_wait_time"
    }
    return kernel_details_col_name_map.get(title, title)


class SafeOpen:
    """
    safe open to check file
    """

    # pylint: disable=consider-using-with
    def __init__(self, name, mode='r', encoding=None):
        self.file = None
        if not os.path.exists(name):
            logger.warning("%s not exist, please check", name)
            return

        if os.access(name, os.R_OK):
            self.file = open(name, mode, encoding=encoding, errors="ignore")
        else:
            logger.warning("%s can not read, check the permissions", name)

    def __enter__(self):
        return self.file

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()


def get_file_path_by_walk(root, filename):
    file_path = ""
    for root, _, files in PathManager.limited_depth_walk(root):
        for name in files:
            if name == filename:
                file_path = os.path.join(root, name)
                return file_path
    return file_path


def check_path_valid(path: str, is_file: bool = True, max_size: int = Constant.MAX_READ_FILE_BYTES) -> bool:
    """
    check the path is valid or not
    :param path: file path
    :param is_file: file or not
    :param max_size: file's max size
    :return: bool
    """
    if path == "":
        raise FileNotFoundError("The path is empty. Please enter a valid path.")
    if not os.path.exists(path):
        raise FileNotFoundError(f"The path \"{path}\" does not exist. Please check that the path exists.")
    if is_file:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"The path \"{path}\" is not a file. Please check the path.")
        if os.path.islink(path):
            raise FileNotFoundError(f"The path \"{path}\" is link. Please check the path.")
        if os.path.getsize(path) > max_size:
            raise OSError(f"The path \"{path}\" is too large to read. Please check the path.")
    else:
        if not os.path.isdir(path):
            raise FileNotFoundError(f"The path \"{path}\" is not a directory. Please check the path.")
        if os.path.islink(path):
            raise FileNotFoundError(f"The path \"{path}\" is link. Please check the path.")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"The path \"{path}\" does not have permission to read. "
                              f"Please check that the path is readable.")
    return True


def parse_json_with_generator(timeline_data_path, func):
    result = []
    if not check_path_valid(timeline_data_path):
        return result
    try:
        with open(timeline_data_path, "r") as f:
            if os.getenv(Constant.DISABLE_STREAMING_READER) == "1":
                logger.debug("Disable streaming reader.")
                file_parser = json.loads(f.read())
            else:
                logger.debug("Enable streaming reader.")
                file_parser = ijson.items(f, "item")

            for i, event in tqdm(enumerate(file_parser),
                                 leave=False, ncols=100, desc="Building dataset for timeline analysis"):
                func_res = func(index=i, event=event)
                if func_res is not None:
                    result.append(func_res)

    except Exception:
        logger.warning("Error %s while parsing file %s, continue to timeline analysis", traceback.format_exc(),
                       timeline_data_path)
    return result


def convert_to_float(num):
    try:
        return float(num)
    except (ValueError, FloatingPointError):
        logger.error(f"Can not convert %s to float", num)
    return 0


def convert_to_float_with_warning(num):
    try:
        return float(num)
    except (ValueError, FloatingPointError):
        logger.warning(f"Can not convert %s to float", num)
    return 0


def safe_index_value(array, value, return_index_if_error=None):
    if value in array:
        return array.index(value)

    return return_index_if_error


def safe_index(array, index, return_value_if_error=None):
    if index < len(array):
        return array[index]
    return return_value_if_error


def convert_to_int(data: any) -> int:
    try:
        int_value = int(convert_to_float(data))
    except ValueError:
        logger.warning(f"Can not convert %s to int.", data)
        return 0
    return int_value


def convert_to_int_with_exception(data: any) -> int:
    if data == "":
        logger.warning("convert_to_int_with_exception: an empty string was encountered.")
        return 0
    return convert_to_int(data)
