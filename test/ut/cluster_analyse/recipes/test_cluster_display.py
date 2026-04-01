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

import unittest
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go

from msprof_analyze.cluster_analyse.recipes.cluster_display import (
    COLOR_PALETTE,
    create_legend_color_map,
    display_duration_boxplots_with_legend
)


class TestCreateLegendColorMap(unittest.TestCase):
    def test_create_legend_color_map_when_pandas_series_then_return_correct(self):
        """测试传入pandas Series时的行为"""
        # 创建测试数据
        legends = pd.Series(['A', 'B', 'C', 'A', 'B'])
        color_map = create_legend_color_map(legends)

        # 验证返回结果
        expected_legends = ['A', 'B', 'C']
        self.assertEqual(len(color_map), len(expected_legends))

        # 验证颜色分配
        for i, legend in enumerate(expected_legends):
            expected_color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
            self.assertEqual(color_map[legend], expected_color)

    def test_create_legend_color_map_when_more_than_palette_when_warning_and_repeat(self):
        """测试当legend数量超过调色板时的颜色循环"""
        # 创建超过调色板数量的legend
        many_legends = pd.Series([f'Legend_{i}' for i in range(len(COLOR_PALETTE) + 5)])
        color_map = create_legend_color_map(many_legends)

        # 验证颜色循环
        expected_legends = sorted(many_legends.unique())
        for i, legend in enumerate(expected_legends):
            expected_color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
            self.assertEqual(color_map[legend], expected_color)


class TestDisplayDurationBoxplotsWithLegend(unittest.TestCase):

    def setUp(self):
        """在每个测试方法之前运行，用于设置测试数据"""
        # 创建样本统计数据DataFrame（有legend列）
        data_with_legend = {
            "Mean(Us)": [10.0, 20.0, 30.0],
            "Min(Us)": [5.0, 15.0, 25.0],
            "Max(Us)": [15.0, 25.0, 35.0],
            "Q1(Us)": [7.0, 17.0, 27.0],
            "Median(Us)": [10.0, 20.0, 30.0],
            "Q3(Us)": [12.0, 22.0, 32.0],
            "Legend": ["A", "B", "A"]
        }
        self.sample_stats_df = pd.DataFrame(data_with_legend, index=["Test1", "Test2", "Test3"])

        # 创建无legend列的样本DataFrame
        data_no_legend = {
            "Mean(Us)": [10.0, 20.0],
            "Min(Us)": [5.0, 15.0],
            "Max(Us)": [15.0, 25.0],
            "Q1(Us)": [7.0, 17.0],
            "Median(Us)": [10.0, 20.0],
            "Q3(Us)": [12.0, 22.0]
        }
        self.sample_stats_df_no_legend = pd.DataFrame(data_no_legend, index=["Test1", "Test2"])

    @patch('plotly.graph_objects.Figure.show')
    def test_display_duration_boxplots_when_with_same_legend_then_in_legend_group(self, mock_show):
        """测试完整的箱线图生成函数"""
        figs = []

        # 调用函数
        display_duration_boxplots_with_legend(
            figs=figs,
            stats_df=self.sample_stats_df,
            legend_col_name="Legend",
            orientation="v",
            title="Test Title",
            x_title="X Title",
            y_title="Y Title",
        )

        # 验证figs列表被更新
        self.assertEqual(len(figs), 1)
        self.assertIsInstance(figs[0], go.Figure)

        # 验证图表数据
        fig = figs[0]
        self.assertEqual(len(fig.data), 3)  # 3个箱线图trace

        # 验证图例处理（A出现两次，但只在第一次显示图例）
        legend_show_states = [trace.showlegend for trace in fig.data]
        self.assertTrue(legend_show_states[0])
        self.assertTrue(legend_show_states[1])
        self.assertFalse(legend_show_states[2])

    @patch('plotly.graph_objects.Figure.show')
    def test_display_duration_boxplots_when_no_legend_column_then_color_gray(self, mock_show):
        """测试没有legend列的情况"""
        figs = []

        display_duration_boxplots_with_legend(
            figs=figs,
            stats_df=self.sample_stats_df_no_legend,
            legend_col_name=None,
            orientation="h"
        )

        self.assertEqual(len(figs), 1)
        fig = figs[0]

        # 验证所有trace都使用灰色
        for trace in fig.data:
            self.assertEqual(trace.marker.color, 'gray')
            self.assertEqual(trace.line.color, 'gray')

    @patch('plotly.graph_objects.Figure.show')
    def test_display_duration_boxplots_horizontal_orientation(self, mock_show):
        """测试水平方向"""
        figs = []

        display_duration_boxplots_with_legend(
            figs=figs,
            stats_df=self.sample_stats_df,
            legend_col_name="Legend",
            orientation="h"
        )

        fig = figs[0]

        # 验证方向设置
        for trace in fig.data:
            self.assertEqual(trace.orientation, "h")

    @patch('plotly.graph_objects.Figure.show')
    def test_display_duration_boxplots_when_invalid_legend_column_then_color_gray(self, mock_show):
        """测试无效的legend列"""
        figs = []

        # 传入不存在的legend列
        display_duration_boxplots_with_legend(
            figs=figs,
            stats_df=self.sample_stats_df_no_legend,
            legend_col_name="NonExistentColumn"
        )

        fig = figs[0]

        # 使用默认的灰色
        for trace in fig.data:
            self.assertEqual(trace.marker.color, 'gray')

    @patch('msprof_analyze.cluster_analyse.recipes.cluster_display.logger')
    def test_display_duration_boxplots_when_missing_columns_then_logger_error(self, mock_logger):
        """测试缺少必要列的情况"""
        # 创建缺少某些列的DataFrame
        incomplete_df = pd.DataFrame({
            "Mean(Us)": [10.0, 20.0],
            "Min(Us)": [5.0, 15.0],
            # 缺少其他必要列
        }, index=["Test1", "Test2"])

        figs = []

        display_duration_boxplots_with_legend(
            figs=figs,
            stats_df=incomplete_df,
            legend_col_name=None
        )
        mock_logger.error.assert_called_once()