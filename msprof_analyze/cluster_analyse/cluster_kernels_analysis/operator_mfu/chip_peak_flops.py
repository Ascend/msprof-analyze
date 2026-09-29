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

import os
import re

from msprof_analyze.prof_common.path_manager import PathManager

from msprof_analyze.prof_common.utils import convert_to_float
from msprof_analyze.prof_common.file_manager import FileManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.operator_flops import DataType
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


class ChipPeakFLOPSCalculator:
    """
    Chip peak FLOPS(Floating Point Operations Per Second) calculation
    Formula: AICore count * frequency * operations per cycle
    """

    DEVICE_DIR_PATTERN = r"device_\d{1,2}$"
    INFO_JSON_PATTERN = r"^info\.json\.\d{1,2}$"

    OPS_PER_CYCLE = {
        DataType.FLOAT16: 16 * 16 * 16 * 2,
        DataType.INT8: 16 * 32 * 16 * 2,
    }
    MHZ_TO_HZ = 1000000

    def __init__(self, profiler_path):
        self.aicore_count = 0
        self.aic_frequency = 0
        self.peak_flops = {}
        if not self._load_chip_info(profiler_path):
            logger.error("ChipPeakFLOPSCalculator initialization failed")

    @staticmethod
    def find_device_info_json(profiler_path):
        for root, dirs, _ in PathManager.limited_depth_walk(profiler_path):
            for dir_name in dirs:
                if not re.match(ChipPeakFLOPSCalculator.DEVICE_DIR_PATTERN, dir_name):
                    continue
                device_dir = os.path.join(root, dir_name)
                for file in os.listdir(device_dir):
                    if re.match(ChipPeakFLOPSCalculator.INFO_JSON_PATTERN, file):
                        return os.path.join(device_dir, file)
        raise FileNotFoundError(f"Device info JSON not found in: {profiler_path}")

    def is_valid(self):
        return self.aicore_count and self.aic_frequency

    def get_peak_performance(self, data_type: DataType):
        if not self.aicore_count or not self.aic_frequency:
            return Constant.INVALID_RETURN

        if data_type not in self.OPS_PER_CYCLE:
            logger.error("Unsupported data type: %s", data_type)
            return Constant.INVALID_RETURN

        if data_type not in self.peak_flops:
            ops_per_cycle = self.OPS_PER_CYCLE[data_type]
            self.peak_flops[data_type] = self.aicore_count * self.aic_frequency * ops_per_cycle * self.MHZ_TO_HZ
            logger.debug("Calculated %s peak: %s", data_type, self.peak_flops[data_type])

        return self.peak_flops[data_type]

    def _load_chip_info(self, profiler_path):
        if not os.path.exists(profiler_path):
            logger.error("Profiler path does not exist: %s", profiler_path)
            return False
        try:
            info_json = self.find_device_info_json(profiler_path)
            device_data = FileManager.read_json_file(info_json)

            if not device_data or "DeviceInfo" not in device_data or not device_data["DeviceInfo"]:
                logger.error("No DeviceInfo data found in device/info.json file")
                return False

            device_info = device_data["DeviceInfo"][0]
            self.aicore_count = device_info.get('ai_core_num', 0)
            aic_frequency_str = device_info.get('aic_frequency', '0')
            self.aic_frequency = convert_to_float(aic_frequency_str)

            if self.aicore_count <= 0 or self.aic_frequency <= 0:
                logger.error(
                    "Invalid device parameters: AICore=%s, frequency=%s", self.aicore_count, self.aic_frequency
                )
                return False

            logger.info("Device info loaded: AICore count=%s, frequency=%s MHz", self.aicore_count, self.aic_frequency)
            return True

        except Exception as e:
            logger.error("Failed to load device information: %s", e)
            return False
