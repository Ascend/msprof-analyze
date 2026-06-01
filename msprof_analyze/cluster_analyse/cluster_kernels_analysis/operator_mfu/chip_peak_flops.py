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
            logger.error(f"Unsupported data type: {data_type}")
            return Constant.INVALID_RETURN

        if data_type not in self.peak_flops:
            ops_per_cycle = self.OPS_PER_CYCLE[data_type]
            self.peak_flops[data_type] = self.aicore_count * self.aic_frequency * ops_per_cycle * self.MHZ_TO_HZ
            logger.debug(f"Calculated {data_type} peak: {self.peak_flops[data_type]}")

        return self.peak_flops[data_type]

    def _load_chip_info(self, profiler_path):
        if not os.path.exists(profiler_path):
            logger.error(f"Profiler path does not exist: {profiler_path}")
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
                logger.error(f"Invalid device parameters: AICore={self.aicore_count}, frequency={self.aic_frequency}")
                return False

            logger.info(f"Device info loaded: AICore count={self.aicore_count}, frequency={self.aic_frequency} MHz")
            return True

        except Exception as e:
            logger.error(f"Failed to load device information: {e}")
            return False
