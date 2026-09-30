# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
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

"""
profiling info
"""

from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.utils.utils import get_file_path_from_directory
from msprof_analyze.prof_common.file_manager import FileManager

logger = get_logger()


class DeviceInfoParser:
    """
    profiling info
    device_id device 名称信息
    "aiv_num" ai vector 个数
    "ai_core_num" aicore 个数
    """

    DATA_LIST = []

    def __init__(self, path) -> None:
        self._path = path

    @staticmethod
    def _parse(info_file: str) -> bool:
        if info_file.endswith("done"):
            return False  # skip info.json.0.done
        try:
            info = FileManager.read_json_file(info_file)
        except RuntimeError as error:
            logger.error("Parse json info file %s failed : %s", info_file, error)
            return False
        if "DeviceInfo" not in info:
            logger.error("No device info in json info file %s", info_file)
            return False
        config = Config()
        for device_info in info["DeviceInfo"]:
            if "id" in device_info:
                config.set_config("device_id", device_info["id"])
            if "aiv_num" in device_info:
                config.set_config("aiv_num", device_info["aiv_num"])
            if "aic_frequency" in device_info:
                config.set_config("aic_frequency", device_info["aic_frequency"])
            if "ai_core_num" in device_info:
                config.set_config("ai_core_num", device_info["ai_core_num"])
                return True
        logger.error("No ai_core_num in json info file %s", info_file)
        return False

    def parse_data(self) -> bool:
        """
        parse profiling data
        :return: true for success or false
        """
        file_list = get_file_path_from_directory(self._path, lambda x: x.startswith("info.json."))
        if not file_list:
            return False
        for info in file_list:
            if self._parse(info):
                return True
        return False
