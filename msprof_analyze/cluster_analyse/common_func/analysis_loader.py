# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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

import importlib
import inspect

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


def is_analysis_class(obj):
    return inspect.isclass(obj) and issubclass(obj, BaseRecipeAnalysis) and obj != BaseRecipeAnalysis


def get_class_from_name(analysis_name: str):
    analysis_path = f"msprof_analyze.cluster_analyse.recipes.{analysis_name}.{analysis_name}"
    module = None
    try:
        module = importlib.import_module(analysis_path)
    except Exception as e:
        logger.error("%s not find:%s", analysis_path, e)
        return module

    specific_analysis = [
        (name, cls) for name, cls in inspect.getmembers(module, is_analysis_class) if cls.__module__ == analysis_path
    ]
    if not specific_analysis:
        logger.error("%s not found.", analysis_name)
        return None
    return specific_analysis[0]
