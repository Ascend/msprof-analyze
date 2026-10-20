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

from msprof_analyze.prof_common.additional_args_manager import AdditionalArgsManager


def split_camel_case(word):
    result = []
    current_word = []
    for char in word:
        if char.isupper() and char != "I":
            if current_word:
                result.append(current_word)
            current_word = char
        else:
            current_word += char
    if current_word and current_word != "Checker" and current_word != "Analyzer":
        result.append(current_word)
    return result


class BasePrompt:
    @staticmethod
    def get_prompt_class(class_name):
        res = split_camel_case(class_name)

        language = AdditionalArgsManager().language
        py_name = '_'.join(res).lower()
        prompt_module_name = f"msprof_analyze.advisor.display.prompt.{language}.{py_name}_prompt"
        prompt_module = importlib.import_module(prompt_module_name)

        prompt_class_name = f"{''.join(res)}Prompt"
        prompt_class = getattr(prompt_module, prompt_class_name)
        return prompt_class

    @staticmethod
    def get_sub_table_name(problem, stage):
        language = AdditionalArgsManager().language
        if language == "en":
            sub_table_name = problem if not stage else f"Stage-{stage}: {problem}"
        else:
            sub_table_name = problem if not stage else f"阶段-{stage}：{problem}"
        return sub_table_name
