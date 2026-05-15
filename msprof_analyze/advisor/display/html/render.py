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
from typing import List, Dict
from collections import defaultdict, OrderedDict

from jinja2 import Environment, FileSystemLoader
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.config.config import Config
from msprof_analyze.advisor.utils.utils import safe_write
from msprof_analyze.prof_common.singleton import singleton

logger = get_logger()


@singleton
class HTMLRender:
    SUPPORTED_KEYS = [
    "main", "overall", "comparison", "computation", "schedule", "communication", "dataloader",
    "memory",
    ]
    PERFORMANCE_PROBLEM_ANALYSIS = "performance_problem_analysis"

    def __init__(self):
        self.html = ""
        self.render_list = defaultdict(list)

    def render_html(self, template_dir: str = "templates", template_name: str = "main.html",
                    template_header=Constant.DEFAULT_TEMPLATE_HEADER):

        # 确保overall 和 comparison 在 performance problem analysis 之前
        sorted_render_htmls = OrderedDict()
        for key in ["overall", "comparison"]:
            if key in self.render_list:
                sorted_render_htmls[key] = self.render_list.get(key)
        for key, html in self.render_list.items():
            if key in sorted_render_htmls:
                continue
            sorted_render_htmls[key] = html

        self.html = self.render_template("main", template_dir, template_name, render_list=sorted_render_htmls,
                                         template_header=template_header)

    def get_rendered_html(self, key: str, template_dir: str, template_name: str, **kwargs):
        if key not in self.SUPPORTED_KEYS:
            error_msg = f"Error render template key {key}, optionals are {self.SUPPORTED_KEYS}"
            logger.error(error_msg)
            raise Exception(error_msg)

        if not os.path.isabs(template_dir):
            template_dir = os.path.join(os.path.dirname(__file__), template_dir)

        env = Environment(loader=FileSystemLoader(template_dir),
                          autoescape=True)
        template = env.get_template(template_name)
        if "priority" not in kwargs:
            kwargs["priority"] = "low priority"
        rendered_html = template.render(**kwargs)
        return rendered_html

    def render_template(self, key: str, template_dir: str, template_name: str, **kwargs):
        rendered_html = self.get_rendered_html(key, template_dir, template_name, **kwargs)

        if not kwargs.get("add_render_list", True):
            return rendered_html

        if key in ["main", "overall", "comparison"]:
            if key not in self.render_list:
                self.render_list[key] = []
            self.render_list[key].append(rendered_html)
        else:
            if self.PERFORMANCE_PROBLEM_ANALYSIS not in self.render_list:
                self.render_list[self.PERFORMANCE_PROBLEM_ANALYSIS] = {}
            if key not in self.render_list[self.PERFORMANCE_PROBLEM_ANALYSIS]:
                self.render_list[self.PERFORMANCE_PROBLEM_ANALYSIS][key] = []
            self.render_list[self.PERFORMANCE_PROBLEM_ANALYSIS][key].append(rendered_html)

        return rendered_html

    def save_to_file(self, save_path: str):
        save_path = os.path.join(Config().work_path, save_path)
        if not save_path.endswith(".html"):
            logger.error("Skip save html file because file name must endswith `.html`, "
                         "but got %s.", os.path.basename(save_path))
            return

        safe_write(self.html, save_path, encoding="UTF-8")
        logger.info("Save suggestion to %s.", save_path)
