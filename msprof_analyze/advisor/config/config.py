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


from msprof_analyze.prof_common.logger import get_logger
import os
import html

from msprof_analyze.advisor.utils.utils import Timer
from msprof_analyze.prof_common.singleton import singleton
from msprof_analyze.prof_common.utils import SafeConfigReader
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


@singleton
class Config:
    """
    config
    """
    # pylint: disable=too-many-instance-attributes

    _CONFIG_DIR_NAME = "config"
    _CONFIG_FILE_NAME = "config.ini"
    _REQUIRED_SECTIONS = {
        'LOG': ['console_logging_level'],
        'ANALYSE': ['analysis_result_file', 'tune_ops_file'],
        'THRESHOLD': ['operator_bound_ratio', 'frequency_threshold'],
        'RULE-BUCKET': ['cn-north-9', 'cn-southwest-2', 'cn-north-7'],
        'URL': [
            'timeline_api_doc_url', 'timeline_with_stack_doc_url',
            'pytorch_aoe_operator_tune_url', 'mslite_infer_aoe_operator_tune_url',
            'enable_compiled_tune_url', 'ascend_profiler_url'
        ]
    }

    def __init__(self) -> None:
        self._work_path = os.getcwd()  # pwd
        self._root_path = os.path.abspath(os.path.join(__file__, "../../"))
        self.config_reader = SafeConfigReader(os.path.join(self._root_path, self._CONFIG_DIR_NAME,
                                                           self._CONFIG_FILE_NAME))
        self.config_reader.validate(self._REQUIRED_SECTIONS)
        self.config = self.config_reader.get_config()
        # ANALYSE
        self._analysis_result_file = self._normalize_path(self.config.get("ANALYSE", "analysis_result_file"))
        self._tune_ops_file = os.path.abspath(
            os.path.join(self._work_path, f"operator_tuning_file_{Timer().strftime}.cfg"))
        self.log_path = None

    @property
    def work_path(self) -> str:
        """
        get work path
        :return: work path
        """
        return self._work_path

    @property
    def root_path(self) -> str:
        """
        get root path
        :return: root path
        """
        return self._root_path

    @property
    def analysis_result_file(self) -> str:
        """
        get filename of op result file
        :return: filename
        """
        return self._analysis_result_file

    @property
    def tune_ops_file(self) -> str:
        """
        get filename of tune op file
        :return: filename
        """
        return self._tune_ops_file

    @property
    def operator_bound_ratio(self) -> float:
        """
        operator_bound_ratio
        """
        return float(self.config.get("THRESHOLD", "operator_bound_ratio"))

    @property
    def frequency_threshold(self) -> float:
        """
        frequency_threshold
        """
        return float(self.config.get("THRESHOLD", "frequency_threshold"))

    @property
    def timeline_api_doc_url(self) -> str:
        try:
            return html.escape(self.config.get("URL", "timeline_api_doc_url"))
        except Exception:
            return ""

    @property
    def timeline_with_stack_doc_url(self) -> str:
        try:
            return html.escape(self.config.get("URL", "timeline_with_stack_doc_url"))
        except Exception:
            return ""

    @property
    def pytorch_aoe_operator_tune_url(self) -> str:
        try:
            return html.escape(self.config.get("URL", "pytorch_aoe_operator_tune_url"))
        except Exception:
            return ""

    @property
    def mslite_infer_aoe_operator_tune_url(self) -> str:
        try:
            return html.escape(self.config.get("URL", "mslite_infer_aoe_operator_tune_url"))
        except Exception:
            return ""

    @property
    def enable_compiled_tune_url(self) -> str:
        try:
            return html.escape(self.config.get("URL", "enable_compiled_tune_url"))
        except Exception:
            return ""

    @property
    def ascend_profiler_url(self) -> str:
        try:
            return html.escape(self.config.get("URL", "ascend_profiler_url"))
        except Exception:
            return ""

    def set_config(self, key, value) -> None:
        """
        set config value
        :param key: config key
        :param value: config value
        """
        setattr(self, key, value)

    def get_config(self, key) -> str:
        """
        get value of config
        :param key: config key
        :return: config value
        """
        try:
            return getattr(self, key)
        except AttributeError:
            return ""

    def set_log_path(self, result_file: str, log_path: str = None):
        self.log_path = log_path if log_path is not None else os.path.join(self._work_path, "log")
        PathManager.make_dir_safety(self.log_path)
        self.config.set("ANALYSE", "analysis_result_file", os.path.join(self.log_path, result_file))
        self._analysis_result_file = os.path.join(self.log_path, result_file)

    def remove_log(self):
        if self.log_path and os.path.isdir(self.log_path) and not os.listdir(self.log_path):
            os.rmdir(self.log_path)

    def _normalize_path(self, file) -> str:
        if not file.startswith("/"):
            file = os.path.join(self._work_path, file)
        return os.path.abspath(file)
