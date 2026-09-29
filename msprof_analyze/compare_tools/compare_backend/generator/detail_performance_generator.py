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
import os
from collections import OrderedDict
from datetime import datetime

from msprof_analyze.compare_tools.compare_backend.comparator.communication_comparator import CommunicationComparator
from msprof_analyze.compare_tools.compare_backend.comparator.module_comparetor import ModuleComparator
from msprof_analyze.compare_tools.compare_backend.comparator.module_statistic_comparator import (
    ModuleStatisticComparator,
)
from msprof_analyze.compare_tools.compare_backend.comparator.operator_comparator import OperatorComparator
from msprof_analyze.compare_tools.compare_backend.comparator.operator_statistic_comparator import (
    OperatorStatisticComparator,
)
from msprof_analyze.compare_tools.compare_backend.comparator.api_compare_comparator import ApiCompareComparator
from msprof_analyze.compare_tools.compare_backend.comparator.kernel_compare_comparator import KernelCompareComparator
from msprof_analyze.compare_tools.compare_backend.comparator.overall_metrics_comparator import OverallMetricsComparator
from msprof_analyze.compare_tools.compare_backend.compare_bean.communication_bean import CommunicationBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.memory_compare_bean import MemoryCompareBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.memory_statistic_bean import MemoryStatisticBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.module_compare_bean import ModuleCompareBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.module_statistic_bean import ModuleStatisticBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.operator_compare_bean import OperatorCompareBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.operator_statistic_bean import OperatorStatisticBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.api_compare_bean import ApiCompareBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.kernel_compare_bean import KernelCompareBean
from msprof_analyze.compare_tools.compare_backend.compare_bean.overall_metrics_bean import OverallMetricsBean
from msprof_analyze.compare_tools.compare_backend.data_prepare.module_data_prepare import ModuleDataPrepare
from msprof_analyze.compare_tools.compare_backend.data_prepare.operator_data_prepare import OperatorDataPrepare
from msprof_analyze.compare_tools.compare_backend.comparator.kernel_type_comparator import KernelTypeComparator
from msprof_analyze.compare_tools.compare_backend.compare_bean.kernel_type_compare_bean import KernelTypeCompareBean
from msprof_analyze.compare_tools.compare_backend.view.excel_view import ExcelView
from msprof_analyze.compare_tools.compare_backend.data_prepare.sequence_pre_matching import SequencePreMatching
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_common.path_manager import PathManager

logger = get_logger()


class DetailPerformanceGenerator:
    def __init__(self, profiling_data_dict: dict, args: any):
        self._profiling_data_dict = profiling_data_dict
        self._args = args
        self._result_data = OrderedDict()
        self._base_step_id = int(args.base_step) if args.base_step else Constant.VOID_STEP
        self._comparison_step_id = int(args.comparison_step) if args.comparison_step else Constant.VOID_STEP

    def run(self):
        self.compare()
        self.generate_view()

    def compare(self):
        enable_compare = [
            self._args.enable_operator_compare,
            self._args.enable_memory_compare,
            self._args.enable_communication_compare,
            self._args.enable_api_compare,
            self._args.enable_kernel_compare,
            self._args.enable_profiling_compare,
        ]
        if any(enable_compare):
            logger.info("Start to compare performance detail data, please wait.")
            comparator_list = self._create_comparator()
        else:
            comparator_list = []
        for comparator in comparator_list:
            self._result_data.update(comparator.generate_data())

    def generate_view(self):
        if not self._result_data:
            return
        dir_path = self._args.output_path if self._args.output_path else "./"
        dir_path = os.path.abspath(dir_path)
        PathManager.check_output_directory_path(dir_path)
        file_name = "performance_comparison_result_{}.xlsx".format(datetime.utcnow().strftime("%Y%m%d%H%M%S"))
        result_file_path = os.path.join(dir_path, file_name)
        ExcelView(self._result_data, result_file_path, self._args).generate_view()
        logger.info("The comparison result file has been generated: %s", result_file_path)

    def _create_comparator(self):
        comparator_list = []
        # 总体性能拆解
        if self._args.enable_profiling_compare:
            overall_data = {
                Constant.BASE_DATA: self._profiling_data_dict.get(Constant.BASE_DATA).overall_metrics,
                Constant.COMPARISON_DATA: self._profiling_data_dict.get(Constant.COMPARISON_DATA).overall_metrics,
            }
            comparator_list.append(OverallMetricsComparator(overall_data, OverallMetricsBean))
        # 通信性能比对
        if self._args.enable_communication_compare:
            communication_data = {
                Constant.BASE_DATA: self._profiling_data_dict.get(Constant.BASE_DATA).communication_dict,
                Constant.COMPARISON_DATA: self._profiling_data_dict.get(Constant.COMPARISON_DATA).communication_dict,
            }
            comparator_list.append(CommunicationComparator(communication_data, CommunicationBean))

        # 算子性能比对-module级
        enable_operator_compare = False
        if self._args.enable_operator_compare:
            module_compare_result = self._module_match() if not self._args.disable_module else []
            if module_compare_result:
                comparator_list.append(ModuleStatisticComparator(module_compare_result, ModuleStatisticBean))
                if not self._args.disable_details:
                    comparator_list.append(ModuleComparator(module_compare_result, ModuleCompareBean))
            else:
                enable_operator_compare = True

        # build tree for operator_compare memory_compare and api_compare
        base_op_prepare, comparison_op_prepare = None, None
        if self._args.enable_memory_compare or self._args.enable_api_compare or enable_operator_compare:
            base_op_prepare = OperatorDataPrepare(self._profiling_data_dict.get(Constant.BASE_DATA), self._base_step_id)
            comparison_op_prepare = OperatorDataPrepare(
                self._profiling_data_dict.get(Constant.COMPARISON_DATA), self._comparison_step_id
            )

        # 算子性能比对-operator级
        op_compare_result = []
        if enable_operator_compare:
            op_compare_result = self._operator_match(
                base_op_prepare.get_top_layer_ops(), comparison_op_prepare.get_top_layer_ops()
            )
            comparator_list.append(OperatorStatisticComparator(op_compare_result, OperatorStatisticBean))
            if not self._args.disable_details:
                comparator_list.append(OperatorComparator(op_compare_result, OperatorCompareBean))
        # 算子内存比对
        if self._args.enable_memory_compare:
            if not op_compare_result:
                op_compare_result = self._operator_match(
                    base_op_prepare.get_top_layer_ops(), comparison_op_prepare.get_top_layer_ops()
                )
            comparator_list.append(OperatorStatisticComparator(op_compare_result, MemoryStatisticBean))
            if not self._args.disable_details:
                comparator_list.append(OperatorComparator(op_compare_result, MemoryCompareBean))
        # host api比对
        if self._args.enable_api_compare:
            api_compare_result = {
                Constant.BASE_DATA: base_op_prepare.get_all_layer_ops(),
                Constant.COMPARISON_DATA: comparison_op_prepare.get_all_layer_ops(),
            }
            comparator_list.append(ApiCompareComparator(api_compare_result, ApiCompareBean))
        # kernel比对
        if self._args.enable_kernel_compare:
            kernel_compare_result = {
                Constant.BASE_DATA: self._profiling_data_dict.get(Constant.BASE_DATA).kernel_details,
                Constant.COMPARISON_DATA: self._profiling_data_dict.get(Constant.COMPARISON_DATA).kernel_details,
            }
            if self._args.use_kernel_type:
                comparator_list.append(KernelTypeComparator(kernel_compare_result, KernelTypeCompareBean))
            else:
                comparator_list.append(KernelCompareComparator(kernel_compare_result, KernelCompareBean))
        return comparator_list

    def _module_match(self):
        if (
            not self._profiling_data_dict.get(Constant.BASE_DATA).python_function_data
            or not self._profiling_data_dict.get(Constant.COMPARISON_DATA).python_function_data
        ):
            return []
        base_root_node = ModuleDataPrepare(self._profiling_data_dict.get(Constant.BASE_DATA)).build_module_tree()
        comparison_root_node = ModuleDataPrepare(
            self._profiling_data_dict.get(Constant.COMPARISON_DATA)
        ).build_module_tree()
        return SequencePreMatching(self._args).run(
            SequencePreMatching.MODULE_TYPE, base_root_node, comparison_root_node
        )

    def _operator_match(self, base_ops, comparison_ops):
        base_bwd_tid = self._profiling_data_dict.get(Constant.BASE_DATA).bwd_tid
        comparison_bwd_tid = self._profiling_data_dict.get(Constant.COMPARISON_DATA).bwd_tid
        return SequencePreMatching(self._args, base_bwd_tid, comparison_bwd_tid).run(
            SequencePreMatching.OP_TYPE, base_ops, comparison_ops
        )
