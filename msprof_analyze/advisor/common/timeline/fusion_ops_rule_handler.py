#  Copyright (c) Huawei Technologies Co., Ltd. 2024-2024. All rights reserved.
import copy
from msprof_analyze.prof_common.logger import get_logger

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.timeline.fusion_ops_rule import OpRule

logger = get_logger()


class TimelineOpRuleHandler:
    """基于线性规划思想保存OpRule，用于局部继承、全局继承等功能"""

    def __init__(self):
        self._db_content = None
        # 具体生成的timeline规则，key为unique_id
        self._all_tmp_timeline_op_rule = {}
        # 所有timeline规则的dict集合，key为unique_id
        self._all_origin_timeline_op_rule_dict = {}
        # 已生成timeline规则的id数组
        self._exist_timeline_op_rule_unique_id_list = []

    @staticmethod
    def _get_local_inherit_id_list(op_rule: dict):
        local_inherit_id_list = []
        for _, val in op_rule.items():
            if val.get("inherit_unique_id") is not None:
                local_inherit_id_list.append(val.get("inherit_unique_id"))
        return local_inherit_id_list

    @staticmethod
    def _is_duplicated_element_in_lists(list_a, list_b):
        """检查两个数组中是否存在重复的元素，若有任意元素重复，返回True"""
        if not isinstance(list_a, list):
            list_a = [list_a]
        if not isinstance(list_b, list):
            list_b = [list_b]
        # 将两个数组合并为一个列表，使用集合（set）判断列表中是否存在重复元素
        combined_list = list_a + list_b
        if len(combined_list) != len(set(combined_list)):
            return True
        return False

    def set_db_content(self, db_content):
        # 过滤非 dict 格式, 或 dict 中没有定义 unique_id 的数据, 并保存到 _all_origin_timeline_op_rule_dict 中
        self._db_content = copy.deepcopy(db_content)
        for rule_dic in self._db_content:
            if not isinstance(rule_dic, dict) or rule_dic.get("unique_id") is None:
                continue
            self._all_origin_timeline_op_rule_dict[rule_dic.get("unique_id")] = rule_dic
        if self._all_origin_timeline_op_rule_dict:
            self.generate_all_timeline_op_rule()

    def generate_basic_timeline_op_rules(self):
        """用于实现获取无全局继承规则, 无全局继承的规则认为是基础版本规则, 默认不会存在局部继承"""
        for _, rule_dic in self._all_origin_timeline_op_rule_dict.items():
            if rule_dic.get("inherit_unique_id") is None:
                self.add_basic_timeline_op_rule(rule_dic)

    def add_basic_timeline_op_rule(self, rule_dic):
        # 若基础规则中存在局部继承的规则，则跳过
        local_inherit_id_list = self._get_local_inherit_id_list(rule_dic.get("operator_rules"))
        if local_inherit_id_list:
            return

        temp_rule = OpRule()
        temp_rule.merge(rule_dic.get("operator_rules"))

        unique_id = rule_dic.get("unique_id")
        logger.debug("The rule of version %s is basic rule.", unique_id)
        self.add_new_timeline_op_rule(unique_id, temp_rule.tmp_rule)

    def add_empty_timeline_op_rule(self, unique_id):
        if self._all_origin_timeline_op_rule_dict.get(unique_id) is None:
            self._all_origin_timeline_op_rule_dict[unique_id] = {}
        tmp_rule = {}
        logger.debug("The rule of version %s is empty.", unique_id)
        self.add_new_timeline_op_rule(unique_id, tmp_rule)

    def add_new_timeline_op_rule(self, unique_id, tmp_rule):
        if unique_id not in self._exist_timeline_op_rule_unique_id_list:
            self._exist_timeline_op_rule_unique_id_list.append(unique_id)
        self._all_tmp_timeline_op_rule[unique_id] = tmp_rule
        logger.debug("The rule of version %s is successfully generated.", unique_id)

    def generate_specified_list_timeline_op_rule(self, specified_unique_id_list, kid_id_list=None):
        for specified_unique_id in specified_unique_id_list:
            if specified_unique_id in self._exist_timeline_op_rule_unique_id_list:
                self.generate_specified_timeline_op_rule(specified_unique_id, kid_id_list)

    def generate_specified_timeline_op_rule(self, specified_unique_id, kid_id_list=None):
        """用于实现生成特定版本规则

        若不存在相应specified_unique_id的规则、或是已生成、循环继承等情况，将该规则置空并返回
        规则库文件结构设置为多叉树, 结构决定了不断向下搜索最终应该是从基础版本开始继承, 递归生成，
        直到specified_unique_id规则依赖继承的规则库全部生成完毕, 再生成该指定规则库, 将specified_unique_id的规则库归档

        参数:
            specified_unique_id: 指定版本规则id
            kid_id_list: 子规则id数组, 用于防止循环继承, 如间接继承自身或直接继承自身等情况
        返回:
            None
        """
        if kid_id_list is None:
            kid_id_list = []

        # 若该unique_id规则在timeline_fusion_ops.yaml中没有相应的规则, 生成该id规则，置为空
        if self._all_origin_timeline_op_rule_dict.get(specified_unique_id) is None:
            logger.warning("The specified version %s does not exist in the rule library. "
                           "Ensure that the corresponding rule is configured in the YAML file. "
                           "The version %s is left blank.",
                           specified_unique_id,
                           specified_unique_id)
            self.add_empty_timeline_op_rule(specified_unique_id)
            return

        # 若该unique_id规则已经生成，则无需再次生成
        if specified_unique_id in self._exist_timeline_op_rule_unique_id_list:
            logger.warning("The rule has been generated and does not need to be generated again. "
                           "Check whether unique id %s in the YAML file is duplicate.",
                           specified_unique_id)
            return

        # 若kid_id_list不为空，且间接继承自身，则尝试生成空规则用于继承
        if kid_id_list and self._is_duplicated_element_in_lists(specified_unique_id, kid_id_list):
            logger.warning("It cannot be inherited indirectly. Ensure that the corresponding rules are correctly "
                           "configured in the YAML file and leave Version %s blank.",
                           specified_unique_id)
            self.add_empty_timeline_op_rule(specified_unique_id)
            return

        rule_dic = self._all_origin_timeline_op_rule_dict.get(specified_unique_id)
        if rule_dic is not None:
            kid_id_list.append(specified_unique_id)

            global_inherit_id = rule_dic.get("inherit_unique_id")
            if global_inherit_id and global_inherit_id not in self._exist_timeline_op_rule_unique_id_list:
                logger.debug("The rule of version %s global inherit the rule of version %s",
                             specified_unique_id, global_inherit_id)
                self.generate_specified_timeline_op_rule(global_inherit_id, kid_id_list)

            # 若局部继承的规则未生成, 生成该规则
            local_inherit_id_list = self._get_local_inherit_id_list(rule_dic.get("operator_rules"))
            if local_inherit_id_list:
                logger.debug("The rule of version %s local inherit the rule of version %s",
                             specified_unique_id, local_inherit_id_list)
                self.generate_specified_list_timeline_op_rule(specified_unique_id_list=local_inherit_id_list,
                                                              kid_id_list=kid_id_list)
            logger.debug("Start to generate rule of version %s", specified_unique_id)
            # 实现全局继承与局部继承
            temp_rule = OpRule(timeline_op_rule_handler=self,
                               rule=self._all_tmp_timeline_op_rule.get(global_inherit_id))
            temp_rule.merge(rule_dic.get("operator_rules"))
            # 将生成的规则归档保存
            self.add_new_timeline_op_rule(specified_unique_id, temp_rule.tmp_rule)
            return
        logger.error("Failed to generate the rule whose unique_id is %s. Ensure that the rule is configured in "
                     "the YAML file and the version %s is empty.", specified_unique_id, specified_unique_id)
        self.add_empty_timeline_op_rule(specified_unique_id)

    def generate_all_timeline_op_rule(self):
        """用于实现获取所有版本规则

        查找db_content中的规则库, 规则库文件结构设置为多叉树, 优先生成无继承的基础规则版本
        循环并生成其他版本, 文件结构决定了不断向下搜索最终应该是从基础版本开始继承, 递归生成，直到全部规则库生成后退出函数

        参数:
            None
        返回:
            None
        """
        self.generate_basic_timeline_op_rules()
        _unique_id_list = copy.deepcopy(list(self._all_origin_timeline_op_rule_dict.keys()))
        for unique_id in _unique_id_list:
            if unique_id in self._exist_timeline_op_rule_unique_id_list:
                continue
            self.generate_specified_timeline_op_rule(unique_id)

    def get_tmp_timeline_op_rule_with_unique_id(self, unique_id):
        if unique_id not in self._exist_timeline_op_rule_unique_id_list:
            logger.error("The specified unique_id does not exist in the rule library. Ensure that the "
                         "corresponding rule is configured in the YAML file and the version %s is empty."
                         "If the value of unique_id is a negative number, the version may not be supported.",
                         unique_id)
            self.add_empty_timeline_op_rule(unique_id)
        if unique_id < 0:
            logger.error("Advise to use a positive integer as the unique id of rules. "
                         "Negative numbers: %s are not recommended to use as unique id. "
                         "If specified invalid unique id: %s is used, an empty rule is returned by default.",
                         unique_id, Constant.TIMELINE_FUSION_OPS_INVALID_UNIQUE_ID)
        return self._all_tmp_timeline_op_rule.get(unique_id)
