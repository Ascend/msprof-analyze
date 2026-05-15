#  Copyright (c) Huawei Technologies Co., Ltd. 2024-2024. All rights reserved.
import copy
from msprof_analyze.prof_common.logger import get_logger


logger = get_logger()


class OpRule:

    def __init__(self, rule=None, timeline_op_rule_handler=None):
        if rule is None:
            self._tmp_rule = {}
        else:
            self._tmp_rule = copy.deepcopy(rule)
        if timeline_op_rule_handler is None:
            self.timeline_op_rule_handler = {}
        else:
            self.timeline_op_rule_handler = copy.deepcopy(timeline_op_rule_handler)
        self._rule = {}

    @property
    def tmp_rule(self):
        return self._tmp_rule

    @staticmethod
    def _format_rule(rule):
        """格式化规则函数, 将额外规则格式化为{key,数组list}形式, 使得yaml文件中operator_rules若写成key:str形式也能正常读取"""
        format_rule = {}
        for key, val in rule.items():
            if not isinstance(val, list):
                val = [val]
            format_rule[key] = val
        return format_rule

    def merge(self, extra_rule):
        """合并函数, 将已有规则库与额外规则合并, 若无继承则已有规则库应为空"""
        for key, val in extra_rule.items():
            for func, op_rules in val.items():
                try:
                    getattr(self, f"{func}")(key, op_rules)
                except AttributeError:
                    logger.error("Undefined field and function name. Ensure that %s is correct in the rule "
                                 "library.", func)

    def get_final_rules(self):
        """获取最终的规则库"""
        self._restore_rule()
        return self._rule

    def add(self, key, add_rules: dict):
        """新增函数, 新增已有规则库不存在的额外规则"""
        if add_rules is None:
            return
        if self._tmp_rule.get(key) is None:
            self._tmp_rule[key] = {}
        format_add_rule = self._format_rule(add_rules)
        for add_key, add_val in format_add_rule.items():
            logger.debug("add: %s: %s", add_key, add_val)
            if add_key not in self._tmp_rule:
                self._tmp_rule[key][add_key] = add_val
            else:
                logger.warning("This key has been written to the rule, "
                               "%s: %s should be written in the overwrite section", add_key, add_val)
                self._tmp_rule[key][add_key].update(add_val)

    def overwrite(self, key, overwrite_rules: dict):
        """重写函数, 重写已有规则库中已经存在的规则"""
        if overwrite_rules is None:
            return
        if self._tmp_rule.get(key) is None:
            self._tmp_rule[key] = {}
        format_overwrite_rules = self._format_rule(overwrite_rules)
        for overwrite_key, overwrite_val in format_overwrite_rules.items():
            logger.debug("overwrite: %s: %s", overwrite_key, overwrite_val)
            if overwrite_key not in self._tmp_rule:
                logger.warning("This key is not written to the rule. "
                               "%s: %s should be written in the add section", overwrite_key, overwrite_val)
                self._tmp_rule[key][overwrite_key] = overwrite_val
            else:
                self._tmp_rule[key][overwrite_key].update(overwrite_val)

    def exclude(self, key, exclude_rules: list):
        """除外函数, 将已有规则库已有的规则除外删除"""
        if exclude_rules is None:
            return
        for exclude_key in exclude_rules:
            logger.debug("exclude: %s", exclude_key)
            if isinstance(exclude_key, str):
                if exclude_key not in self._tmp_rule[key]:
                    logger.warning("This key is not written to the rule. "
                                   "do not need to exclude: %s.", exclude_key)
                    continue
                self._tmp_rule[key].pop(exclude_key)
            else:
                logger.warning("Error type rule in exclude: %s", exclude_key)

    def inherit_unique_id(self, key, inherit_unique_id):
        """局部继承函数, 将规则库中指定unique_id版本覆盖指定位置"""
        result_rule = self.timeline_op_rule_handler.get_tmp_timeline_op_rule_with_unique_id(inherit_unique_id)
        if result_rule is not None and result_rule.get(key) is not None:
            self._tmp_rule[key] = copy.deepcopy(result_rule.get(key))
            return
        logger.error("Rule library version %s does not exist. ", inherit_unique_id)

    def _restore_rule(self):
        for key, op_api_map in self._tmp_rule.items():
            self._rule[key] = [{op_combined: api} for op_combined, api in op_api_map.items()]
