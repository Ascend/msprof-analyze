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
from math import isclose

from msprof_analyze.compare_tools.compare_backend.compare_bean.profiling_info import ProfilingInfo
from msprof_analyze.compare_tools.compare_backend.utils.common_func import calculate_diff_ratio
from msprof_analyze.compare_tools.compare_backend.utils.excel_config import ExcelConfig, CellFormatType
from msprof_analyze.prof_common.constant import Constant


class OverallMetricsBean:
    TABLE_NAME = Constant.OVERALL_METRICS_TABLE
    HEADERS = ExcelConfig.HEADERS.get(TABLE_NAME)
    OVERHEAD = ExcelConfig.OVERHEAD.get(TABLE_NAME)
    DEFAULT_VALUE = [0, 0, "/"]

    def __init__(self, base_info: ProfilingInfo, comparison_info: ProfilingInfo):
        self._base_data = OverallMetricsInfo(base_info).overall_metrics
        self._comparison_data = OverallMetricsInfo(comparison_info).overall_metrics
        if not any((base_info.is_not_minimal_profiling(), comparison_info.is_not_minimal_profiling())):
            OverallMetricsBean.TABLE_NAME += ' (Minimal Prof)'

    @property
    def rows(self):
        rows_data = []
        rows_data.extend(
            self._get_rows(self._base_data.get("before_mc2", {}), self._comparison_data.get("before_mc2", {}))
        )

        base_mc2_data = self._base_data.get("mc2", {})
        comparison_mc2_data = self._comparison_data.get("mc2", {})
        for kernel_name, base_data in base_mc2_data.items():
            comparison_data = comparison_mc2_data.pop(kernel_name, {})
            self._append_data(
                rows_data,
                self._get_row_data(
                    kernel_name,
                    base_data.get("mc2", self.DEFAULT_VALUE),
                    comparison_data.get("mc2", self.DEFAULT_VALUE),
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.MC2_COMPUTING_TIME,
                    base_data.get(ExcelConfig.MC2_COMPUTING_TIME, self.DEFAULT_VALUE),
                    comparison_data.get(ExcelConfig.MC2_COMPUTING_TIME, self.DEFAULT_VALUE),
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.MC2_COMMUNICATION_TIME,
                    base_data.get(ExcelConfig.MC2_COMMUNICATION_TIME, self.DEFAULT_VALUE),
                    comparison_data.get(ExcelConfig.MC2_COMMUNICATION_TIME, self.DEFAULT_VALUE),
                ),
            )
        for kernel_name, comparison_data in comparison_mc2_data.items():
            self._append_data(
                rows_data,
                self._get_row_data(kernel_name, self.DEFAULT_VALUE, comparison_data.get("mc2", self.DEFAULT_VALUE)),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.MC2_COMPUTING_TIME,
                    self.DEFAULT_VALUE,
                    comparison_data.get(ExcelConfig.MC2_COMPUTING_TIME, self.DEFAULT_VALUE),
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.MC2_COMMUNICATION_TIME,
                    self.DEFAULT_VALUE,
                    comparison_data.get(ExcelConfig.MC2_COMMUNICATION_TIME, self.DEFAULT_VALUE),
                ),
            )

        rows_data.extend(
            self._get_rows(self._base_data.get("before_group", {}), self._comparison_data.get("before_group", {}))
        )

        base_group_data = self._base_data.get("group", {})
        comparison_group_data = self._comparison_data.get("group", {})
        base_pg_name_dict = self._base_data.get("pg_name_dict", {})
        comparison_pg_name_dict = self._comparison_data.get("pg_name_dict", {})
        # deal base and comparsion data which can match with pg_name
        for base_pg_name, base_group_name_list in base_pg_name_dict.items():
            if len(base_group_name_list) != 1 or base_pg_name == Constant.UNKNOWN:
                continue
            comparison_group_name_list = comparison_pg_name_dict.get(base_pg_name, [])
            if len(comparison_group_name_list) != 1:
                continue

            base_data = base_group_data.pop(base_group_name_list[0], {})
            comparison_data = comparison_group_data.pop(comparison_group_name_list[0], {})
            description = f"\t{base_pg_name}: Communication"
            ExcelConfig.ROW_STYLE_MAP[description] = CellFormatType.LIGHT_BLUE_NORMAL
            self._append_data(
                rows_data,
                self._get_row_data(
                    description,
                    base_data.get(ExcelConfig.COMMUNICATION_TIME, self.DEFAULT_VALUE),
                    comparison_data.get(ExcelConfig.COMMUNICATION_TIME, self.DEFAULT_VALUE),
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.WAIT,
                    base_data.get(ExcelConfig.WAIT, self.DEFAULT_VALUE),
                    comparison_data.get(ExcelConfig.WAIT, self.DEFAULT_VALUE),
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.TRANSMIT,
                    base_data.get(ExcelConfig.TRANSMIT, self.DEFAULT_VALUE),
                    comparison_data.get(ExcelConfig.TRANSMIT, self.DEFAULT_VALUE),
                ),
            )

        for group_name, base_data in base_group_data.items():
            comparison_data = comparison_group_data.pop(group_name, {})
            self._append_data(
                rows_data,
                self._get_row_data(
                    base_data.get("description", group_name),
                    base_data.get(ExcelConfig.COMMUNICATION_TIME, self.DEFAULT_VALUE),
                    comparison_data.get(ExcelConfig.COMMUNICATION_TIME, self.DEFAULT_VALUE),
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.WAIT,
                    base_data.get(ExcelConfig.WAIT, self.DEFAULT_VALUE),
                    comparison_data.get(ExcelConfig.WAIT, self.DEFAULT_VALUE),
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.TRANSMIT,
                    base_data.get(ExcelConfig.TRANSMIT, self.DEFAULT_VALUE),
                    comparison_data.get(ExcelConfig.TRANSMIT, self.DEFAULT_VALUE),
                ),
            )
        for group_name, comparison_data in comparison_group_data.items():
            self._append_data(
                rows_data,
                self._get_row_data(
                    comparison_data.get("description", group_name),
                    self.DEFAULT_VALUE,
                    comparison_data.get(ExcelConfig.COMMUNICATION_TIME, self.DEFAULT_VALUE),
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.WAIT, self.DEFAULT_VALUE, comparison_data.get(ExcelConfig.WAIT, self.DEFAULT_VALUE)
                ),
            )
            self._append_data(
                rows_data,
                self._get_row_data(
                    ExcelConfig.TRANSMIT,
                    self.DEFAULT_VALUE,
                    comparison_data.get(ExcelConfig.TRANSMIT, self.DEFAULT_VALUE),
                ),
            )

        rows_data.extend(
            self._get_rows(self._base_data.get("group_overlap", {}), self._comparison_data.get("group_overlap", {}))
        )
        rows_data.extend(
            self._get_rows(self._base_data.get("after_group", {}), self._comparison_data.get("after_group", {}))
        )
        return rows_data

    @classmethod
    def _get_rows(cls, base_data_dict, comparison_data_dict):
        rows_data = []
        for index, base_data in base_data_dict.items():
            comparison_data = comparison_data_dict.pop(index, cls.DEFAULT_VALUE)
            row = cls._get_row_data(index, base_data, comparison_data)
            if row:
                rows_data.append(row)
        for index, comparison_data in comparison_data_dict.items():
            row = cls._get_row_data(index, cls.DEFAULT_VALUE, comparison_data)
            if row:
                rows_data.append(row)
        return rows_data

    @classmethod
    def _get_row_data(cls, index, base_data, comparison_data):
        if isclose(base_data[0], 0) and isclose(comparison_data[0], 0):
            return []
        row_data = [index]
        row_data.extend(base_data)
        row_data.extend(comparison_data)
        row_data.extend(calculate_diff_ratio(base_data[0], comparison_data[0]))
        return row_data

    @classmethod
    def _append_data(cls, all_data, data):
        if not data:
            return
        all_data.append(data)


class OverallMetricsInfo:
    __slots__ = ['_profiling_info', '_comm_group_list', '_overall_metrics_data']

    def __init__(self, profiling_info: ProfilingInfo):
        self._profiling_info = profiling_info
        self._comm_group_list = list(profiling_info.communication_group_time.keys())
        self._overall_metrics_data = self._init_overall_metrics_data()

    @property
    def e2e_time(self):
        if isclose(self._profiling_info.e2e_time_ms, 0):
            return float("inf")
        return self._profiling_info.e2e_time_ms

    @property
    def overall_metrics(self):
        return self._overall_metrics_data

    @property
    def computing_data(self):
        return [
            self._profiling_info.compute_time_ms,
            self._profiling_info.compute_time_ms / self.e2e_time,
            sum(
                (
                    self._profiling_info.fa_fwd_num,
                    self._profiling_info.fa_bwd_num,
                    self._profiling_info.conv_fwd_num,
                    self._profiling_info.conv_bwd_num,
                    self._profiling_info.mm_total_num,
                    self._profiling_info.vector_total_num,
                    self._profiling_info.sdma_num_tensor_move,
                    self._profiling_info.other_cube_num,
                    self._profiling_info.page_attention_num,
                )
            ),
        ]

    @property
    def fa_fwd_data(self):
        return [
            self._profiling_info.fa_fwd_time,
            self._profiling_info.fa_fwd_time / self.e2e_time,
            self._profiling_info.fa_fwd_num,
        ]

    @property
    def fa_bwd_data(self):
        return [
            self._profiling_info.fa_bwd_time,
            self._profiling_info.fa_bwd_time / self.e2e_time,
            self._profiling_info.fa_bwd_num,
        ]

    @property
    def fa_fwd_cube_data(self):
        return [
            self._profiling_info.fa_time_fwd_cube,
            self._profiling_info.fa_time_fwd_cube / self.e2e_time,
            self._profiling_info.fa_num_fwd_cube,
        ]

    @property
    def fa_fwd_vector_data(self):
        return [
            self._profiling_info.fa_time_fwd_vector,
            self._profiling_info.fa_time_fwd_vector / self.e2e_time,
            self._profiling_info.fa_num_fwd_vector,
        ]

    @property
    def fa_bwd_cube_data(self):
        return [
            self._profiling_info.fa_time_bwd_cube,
            self._profiling_info.fa_time_bwd_cube / self.e2e_time,
            self._profiling_info.fa_num_bwd_cube,
        ]

    @property
    def fa_bwd_vector_data(self):
        return [
            self._profiling_info.fa_time_bwd_vector,
            self._profiling_info.fa_time_bwd_vector / self.e2e_time,
            self._profiling_info.fa_num_bwd_vector,
        ]

    @property
    def conv_fwd_data(self):
        return [
            self._profiling_info.conv_fwd_time,
            self._profiling_info.conv_fwd_time / self.e2e_time,
            self._profiling_info.conv_fwd_num,
        ]

    @property
    def conv_bwd_data(self):
        return [
            self._profiling_info.conv_bwd_time,
            self._profiling_info.conv_bwd_time / self.e2e_time,
            self._profiling_info.conv_bwd_num,
        ]

    @property
    def conv_fwd_cube_data(self):
        return [
            self._profiling_info.conv_time_fwd_cube,
            self._profiling_info.conv_time_fwd_cube / self.e2e_time,
            self._profiling_info.conv_num_fwd_cube,
        ]

    @property
    def conv_fwd_vector_data(self):
        return [
            self._profiling_info.conv_time_fwd_vector,
            self._profiling_info.conv_time_fwd_vector / self.e2e_time,
            self._profiling_info.conv_num_fwd_vector,
        ]

    @property
    def conv_bwd_cube_data(self):
        return [
            self._profiling_info.conv_time_bwd_cube,
            self._profiling_info.conv_time_bwd_cube / self.e2e_time,
            self._profiling_info.conv_num_bwd_cube,
        ]

    @property
    def conv_bwd_vector_data(self):
        return [
            self._profiling_info.conv_time_bwd_vector,
            self._profiling_info.conv_time_bwd_vector / self.e2e_time,
            self._profiling_info.conv_num_bwd_vector,
        ]

    @property
    def mm_data(self):
        return [
            self._profiling_info.mm_total_time,
            self._profiling_info.mm_total_time / self.e2e_time,
            self._profiling_info.mm_total_num,
        ]

    @property
    def mm_cube_data(self):
        return [
            self._profiling_info.matmul_time_cube,
            self._profiling_info.matmul_time_cube / self.e2e_time,
            self._profiling_info.matmul_num_cube,
        ]

    @property
    def mm_vector_data(self):
        return [
            self._profiling_info.matmul_time_vector,
            self._profiling_info.matmul_time_vector / self.e2e_time,
            self._profiling_info.matmul_num_vector,
        ]

    @property
    def pa_data(self):
        return [
            self._profiling_info.page_attention_time,
            self._profiling_info.page_attention_time / self.e2e_time,
            self._profiling_info.page_attention_num,
        ]

    @property
    def vector_data(self):
        return [
            self._profiling_info.vector_total_time,
            self._profiling_info.vector_total_time / self.e2e_time,
            self._profiling_info.vector_total_num,
        ]

    @property
    def vector_trans_data(self):
        return [
            self._profiling_info.vector_time_trans,
            self._profiling_info.vector_time_trans / self.e2e_time,
            self._profiling_info.vector_num_trans,
        ]

    @property
    def vector_no_trans_data(self):
        return [
            self._profiling_info.vector_time_notrans,
            self._profiling_info.vector_time_notrans / self.e2e_time,
            self._profiling_info.vector_num_notrans,
        ]

    @property
    def cube_data(self):
        return [
            self._profiling_info.other_cube_time,
            self._profiling_info.other_cube_time / self.e2e_time,
            self._profiling_info.other_cube_num,
        ]

    @property
    def sdma_tm_data(self):
        return [
            self._profiling_info.sdma_time_tensor_move,
            self._profiling_info.sdma_time_tensor_move / self.e2e_time,
            self._profiling_info.sdma_num_tensor_move,
        ]

    @property
    def other_data(self):
        other_time = max(
            (
                0,
                self._profiling_info.compute_time_ms
                - self._profiling_info.fa_fwd_time
                - self._profiling_info.fa_bwd_time
                - self._profiling_info.conv_fwd_time
                - self._profiling_info.conv_bwd_time
                - self._profiling_info.mm_total_time
                - self._profiling_info.vector_total_time
                - self._profiling_info.sdma_time_tensor_move
                - self._profiling_info.other_cube_time
                - self._profiling_info.page_attention_time
                - self._profiling_info.all_mc2_time,
            )
        )
        return [other_time, other_time / self.e2e_time, "/"]

    @property
    def communication_data(self):
        return [
            self._profiling_info.communication_not_overlapped_ms,
            self._profiling_info.communication_not_overlapped_ms / self.e2e_time,
            "/",
        ]

    @property
    def free_time_data(self):
        return [self._profiling_info.free_time_ms, self._profiling_info.free_time_ms / self.e2e_time, "/"]

    @property
    def sdma_data(self):
        return [self._profiling_info.sdma_time_stream, self._profiling_info.sdma_time_stream / self.e2e_time, "/"]

    @property
    def free_data(self):
        free = self._profiling_info.free_time_ms - self._profiling_info.sdma_time_stream
        return [free, free / self.e2e_time, "/"]

    @property
    def e2e_time_data(self):
        return [self.e2e_time, 1, "/"]

    def communication_data_by_group(self, group_name: str):
        return [
            self._profiling_info.get_communication_time_by_group(group_name),
            self._profiling_info.get_communication_time_by_group(group_name) / self.e2e_time,
            "/",
        ]

    def wait_data_by_group(self, group_name: str):
        return [
            self._profiling_info.get_wait_time_by_group(group_name),
            self._profiling_info.get_wait_time_by_group(group_name) / self.e2e_time,
            "/",
        ]

    def transmit_data_by_group(self, group_name: str):
        return [
            self._profiling_info.get_transmit_time_by_group(group_name),
            self._profiling_info.get_transmit_time_by_group(group_name) / self.e2e_time,
            "/",
        ]

    def mc2_data_by_name(self, kernel_name: str):
        return [
            self._profiling_info.get_mc2_time_by_name(kernel_name),
            self._profiling_info.get_mc2_time_by_name(kernel_name) / self.e2e_time,
            self._profiling_info.get_mc2_number_by_name(kernel_name),
        ]

    def mc2_computing_data_by_name(self, kernel_name: str):
        return [
            self._profiling_info.get_mc2_computing_time_by_name(kernel_name),
            self._profiling_info.get_mc2_computing_time_by_name(kernel_name) / self.e2e_time,
            "/",
        ]

    def mc2_communication_data_by_name(self, kernel_name: str):
        return [
            self._profiling_info.get_mc2_communication_time_by_name(kernel_name),
            self._profiling_info.get_mc2_communication_time_by_name(kernel_name) / self.e2e_time,
            "/",
        ]

    def _init_overall_metrics_data(self):
        overall_metrics_data = {
            "before_mc2": {ExcelConfig.COMPUTING: self.computing_data},
            "before_group": {
                ExcelConfig.FA_FWD: self.fa_fwd_data,
                ExcelConfig.FA_FWD_CUBE: self.fa_fwd_cube_data,
                ExcelConfig.FA_FWD_VECTOR: self.fa_fwd_vector_data,
                ExcelConfig.FA_BWD: self.fa_bwd_data,
                ExcelConfig.FA_BWD_CUBE: self.fa_bwd_cube_data,
                ExcelConfig.FA_BWD_VECTOR: self.fa_bwd_vector_data,
                ExcelConfig.CONV_FWD: self.conv_fwd_data,
                ExcelConfig.CONV_FWD_CUBE: self.conv_fwd_cube_data,
                ExcelConfig.CONV_FWD_VECTOR: self.conv_fwd_vector_data,
                ExcelConfig.CONV_BWD: self.conv_bwd_data,
                ExcelConfig.CONV_BWD_CUBE: self.conv_bwd_cube_data,
                ExcelConfig.CONV_BWD_VECTOR: self.conv_bwd_vector_data,
                ExcelConfig.MM: self.mm_data,
                ExcelConfig.MM_CUBE: self.mm_cube_data,
                ExcelConfig.MM_VECTOR: self.mm_vector_data,
                ExcelConfig.PA: self.pa_data,
                ExcelConfig.VECTOR: self.vector_data,
                ExcelConfig.VECTOR_TRANS: self.vector_trans_data,
                ExcelConfig.VECTOR_NO_TRANS: self.vector_no_trans_data,
                ExcelConfig.CUBE: self.cube_data,
                ExcelConfig.SDMA_TM: self.sdma_tm_data,
                ExcelConfig.OTHER: self.other_data,
                ExcelConfig.COMMUNICATION_TIME: self.communication_data,
            },
            "after_group": {
                ExcelConfig.FREE_TIME: self.free_time_data,
                ExcelConfig.SDMA: self.sdma_data,
                ExcelConfig.FREE: self.free_data,
                ExcelConfig.E2E_TIME: self.e2e_time_data,
            },
        }
        if self._comm_group_list:
            for group_name in self._comm_group_list:
                pg_name = self._profiling_info.get_pg_name_by_group(group_name)
                description = " ".join([pg_name + ":" if pg_name != Constant.UNKNOWN else "", group_name]).strip()
                ExcelConfig.ROW_STYLE_MAP[f"\t{description}"] = CellFormatType.LIGHT_BLUE_NORMAL
                overall_metrics_data.setdefault("group", {})[group_name] = {
                    "description": f"\t{description}",
                    ExcelConfig.COMMUNICATION_TIME: self.communication_data_by_group(group_name),
                    ExcelConfig.WAIT: self.wait_data_by_group(group_name),
                    ExcelConfig.TRANSMIT: self.transmit_data_by_group(group_name),
                }
                overall_metrics_data.setdefault("pg_name_dict", {}).setdefault(pg_name, []).append(group_name)

        if self._profiling_info.communication_overlap_time:
            ExcelConfig.ROW_STYLE_MAP[ExcelConfig.UNCOVERED_COMM_OVERLAP] = CellFormatType.LIGHT_BLUE_NORMAL
            comm_overlap_time = sum(self._profiling_info.communication_overlap_time.values())
            overall_metrics_data.setdefault("group_overlap", {})[ExcelConfig.UNCOVERED_COMM_OVERLAP] = [
                comm_overlap_time,
                comm_overlap_time / self.e2e_time,
                "/",
            ]
            for group_set, overlap_time in self._profiling_info.communication_overlap_time.items():
                pg_name_1 = self._profiling_info.get_pg_name_by_group(group_set[0])
                pg_name_2 = self._profiling_info.get_pg_name_by_group(group_set[1])
                pg_name = (
                    f"\t\t{pg_name_1 if pg_name_1 != Constant.UNKNOWN else group_set[0]} & "
                    f"{pg_name_2 if pg_name_2 != Constant.UNKNOWN else group_set[1]}"
                )
                overall_metrics_data.setdefault("group_overlap", {})[pg_name] = [
                    overlap_time,
                    overlap_time / self.e2e_time,
                    "/",
                ]

        for kernel_name in self._profiling_info.mc2_time_dict.keys():
            mc2_name_index = f"\t{kernel_name}"
            ExcelConfig.ROW_STYLE_MAP[mc2_name_index] = CellFormatType.LIGHT_BLUE_NORMAL
            overall_metrics_data.setdefault("mc2", {})[mc2_name_index] = {
                "mc2": self.mc2_data_by_name(kernel_name),
                ExcelConfig.MC2_COMPUTING_TIME: self.mc2_computing_data_by_name(kernel_name),
                ExcelConfig.MC2_COMMUNICATION_TIME: self.mc2_communication_data_by_name(kernel_name),
            }
        return overall_metrics_data
