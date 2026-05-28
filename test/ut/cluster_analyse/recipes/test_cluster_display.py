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
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from msprof_analyze.cluster_analyse.recipes import cluster_display
from msprof_analyze.cluster_analyse.recipes.cluster_display import (
    COLOR_PALETTE,
    create_legend_color_map,
    display_bar,
    display_box,
    display_boxplot,
    display_duration_boxplots,
    display_duration_boxplots_with_legend,
    display_graph,
    display_stats_optional_combobox,
    display_stats_per_operation,
    display_stats_per_rank_groups_combobox,
    display_stats_scatter,
    display_table_per_rank,
    get_stats_cols
)


class TestCreateLegendColorMap(unittest.TestCase):
    def test_get_stats_cols_should_prefer_us_columns_and_fallback_legacy_columns(self):
        full_df = pd.DataFrame(columns=["Q1(Us)", "Q3(Us)", "med(Us)", "stdev"])
        fallback_df = pd.DataFrame(columns=["name"])

        self.assertEqual(get_stats_cols(full_df), ("Q1(Us)", "Q3(Us)", "med(Us)", "stdev"))
        self.assertEqual(get_stats_cols(fallback_df), ("Q1~", "Q3~", "med~", "stdev~"))

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

    def test_create_legend_color_map_should_return_empty_when_legends_none(self):
        self.assertEqual(create_legend_color_map(None), {})


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


class TestBasicDisplayFunctions(unittest.TestCase):

    def setUp(self):
        self.stats_df = pd.DataFrame({
            "Name": ["op0", "op1"],
            "Q1(Us)": [1.0, 2.0],
            "Q3(Us)": [4.0, 5.0],
            "med(Us)": [2.0, 3.0],
            "stdev": [0.1, 0.2],
            "minRank": [0, 1],
            "maxRank": [2, 3]
        })

    @patch("plotly.graph_objects.Figure.show")
    def test_display_box_should_use_first_column_as_default_x_and_apply_layout(self, mock_show):
        display_box(self.stats_df, title="Box Title")

        mock_show.assert_called_once()

    @patch("plotly.graph_objects.Figure.show")
    def test_display_box_should_accept_explicit_x_series(self, mock_show):
        display_box(self.stats_df, x="Name", title="Explicit X")

        mock_show.assert_called_once()

    @patch("plotly.graph_objects.Figure.show")
    def test_display_stats_scatter_should_add_expected_five_traces(self, mock_show):
        created_figs = []
        original_figure = go.Figure

        def capture_figure(*args, **kwargs):
            fig = original_figure(*args, **kwargs)
            created_figs.append(fig)
            return fig

        with patch("msprof_analyze.cluster_analyse.recipes.cluster_display.go.Figure", side_effect=capture_figure):
            display_stats_scatter(self.stats_df, title="Scatter Title")

        mock_show.assert_called_once()
        self.assertEqual(len(created_figs[0].data), 5)
        self.assertEqual([trace.name for trace in created_figs[0].data],
                         ["Q1(Us)", "med(Us)", "Q3(Us)", "minRank", "maxRank"])

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display")
    def test_display_table_per_rank_should_display_empty_dataframe_directly(self, mock_display):
        empty_df = pd.DataFrame()

        display_table_per_rank(empty_df)

        mock_display.assert_called_once_with(empty_df)

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.interact")
    def test_display_table_per_rank_should_create_rank_dropdown_and_callback(self, mock_interact):
        df = pd.DataFrame({
            "rank": [0, 1],
            "value": [10, 20]
        })

        display_table_per_rank(df)

        mock_interact.assert_called_once()
        callback = mock_interact.call_args.args[0]
        dropdown = mock_interact.call_args.kwargs["name"]
        self.assertEqual(list(dropdown.options), [0, 1])

        with patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display") as mock_display:
            callback(1)

        displayed_df = mock_display.call_args.args[0]
        self.assertEqual(displayed_df.columns.tolist(), ["value"])
        self.assertEqual(displayed_df["value"].tolist(), [20])

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display")
    def test_display_stats_per_operation_should_display_empty_dataframe_directly(self, mock_display):
        empty_df = pd.DataFrame()

        display_stats_per_operation(empty_df)

        mock_display.assert_called_once_with(empty_df)

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display_stats_scatter")
    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display_box")
    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display")
    def test_display_stats_per_operation_should_display_single_operation_immediately(self, mock_display, mock_box,
                                                                                     mock_scatter):
        df = pd.DataFrame({
            "op": ["op0", "op0"],
            "rank": [0, 1],
            "Q1(Us)": [1, 2],
            "Q3(Us)": [3, 4],
            "med(Us)": [2, 3],
            "stdev": [0.1, 0.2],
            "minRank": [0, 0],
            "maxRank": [1, 1]
        })

        display_stats_per_operation(df, x="op", title="single")

        mock_display.assert_called_once()
        mock_box.assert_called_once()
        mock_scatter.assert_called_once()

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.interact")
    def test_display_stats_per_operation_should_create_dropdown_for_multiple_operations(self, mock_interact):
        df = pd.DataFrame({
            "op": ["op0", "op1"],
            "rank": [0, 1],
            "Q1(Us)": [1, 2],
            "Q3(Us)": [3, 4],
            "med(Us)": [2, 3],
            "stdev": [0.1, 0.2],
            "minRank": [0, 0],
            "maxRank": [1, 1]
        })

        display_stats_per_operation(df, x="op", box=False, scatter=False, table=False)

        mock_interact.assert_called_once()
        dropdown = mock_interact.call_args.kwargs["name"]
        self.assertEqual(tuple(dropdown.options), ("op0", "op1"))
        self.assertEqual(dropdown.value, "op0")

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display_boxplot")
    def test_display_duration_boxplots_should_delegate_columns_to_display_boxplot(self, mock_display_boxplot):
        stats_df = pd.DataFrame({
            "Mean(Us)": [10],
            "Min(Us)": [1],
            "Max(Us)": [20],
            "Q1(Us)": [5],
            "Median(Us)": [10],
            "Q3(Us)": [15]
        }, index=["op0"])
        figs = []

        display_duration_boxplots(figs, stats_df, orientation="h", title="duration",
                                  x_title="x", y_title="y", legend_title="legend")

        mock_display_boxplot.assert_called_once()
        self.assertIs(mock_display_boxplot.call_args.args[0], figs)
        self.assertEqual(mock_display_boxplot.call_args.kwargs["orientation"], "h")
        self.assertEqual(mock_display_boxplot.call_args.kwargs["title"], "duration")

    @patch("plotly.graph_objects.Figure.show")
    def test_display_boxplot_should_append_figure_when_figs_is_list(self, mock_show):
        figs = []

        display_boxplot(figs, ["op0"], [1], [2], [3], [4], [5], [3], orientation="h", title="boxplot")

        mock_show.assert_called_once()
        self.assertEqual(len(figs), 1)
        self.assertEqual(figs[0].data[0].orientation, "h")

    @patch("plotly.graph_objects.Figure.show")
    def test_display_boxplot_should_not_append_when_figs_not_list(self, mock_show):
        figs = ()

        display_boxplot(figs, ["op0"], [1], [2], [3], [4], [5], [3])

        mock_show.assert_called_once()


class FakeLineFigure:
    def __init__(self):
        self.layout_args = None
        self.show_called = False

    def update_layout(self, **kwargs):
        self.layout_args = kwargs

    def show(self):
        self.show_called = True


class FakeBar:
    def __init__(self):
        self.color = None

    def set_color(self, color):
        self.color = color


class FakeBarFigure:
    def __init__(self, patch_count):
        self.xlabel = None
        self.ylabel = None
        self.bar_label_arg = None
        self.containers = [["container"]]
        self.patches = [FakeBar() for _ in range(patch_count)]

    def set_xlabel(self, label):
        self.xlabel = label

    def set_ylabel(self, label):
        self.ylabel = label

    def bar_label(self, container):
        self.bar_label_arg = container


class TestGraphAndBarDisplayFunctions(unittest.TestCase):

    def test_display_graph_should_support_dataframe_dict_series_and_numpy_inputs(self):
        data_frame = pd.DataFrame({"x": ["a", "b"], "v": [1, 2]})
        data_dict = {"v": [1, 2]}
        data_series = pd.Series([1, 2])
        data_array = np.array([1, 2])

        for y_axes in [data_frame, data_dict, data_series, data_array]:
            fake_fig = FakeLineFigure()
            figs = []
            with patch("pandas.DataFrame.plot", new_callable=MagicMock) as mock_plot:
                mock_plot.line.return_value = fake_fig

                x_axis = "x" if isinstance(y_axes, pd.DataFrame) else ["a", "b"]
                display_graph(figs, x_axis, y_axes, title="line", x_title="x", y_title="y")

            self.assertEqual(len(figs), 1)
            self.assertIs(figs[0], fake_fig)
            self.assertTrue(fake_fig.show_called)
            self.assertEqual(fake_fig.layout_args["title"], "line")

    def test_display_graph_should_return_when_input_type_invalid(self):
        figs = []

        display_graph(figs, ["a"], object())

        self.assertEqual(figs, [])

    def test_display_graph_should_not_append_when_figs_not_list(self):
        fake_fig = FakeLineFigure()
        with patch("pandas.DataFrame.plot", new_callable=MagicMock) as mock_plot:
            mock_plot.line.return_value = fake_fig

            display_graph((), ["a"], {"v": [1]})

        self.assertTrue(fake_fig.show_called)

    def test_display_bar_should_support_dataframe_dict_series_and_numpy_inputs(self):
        cases = [
            (pd.DataFrame({"x": ["a", "b"], "score": [1, 3]}), "score"),
            ({"score": [1, 3]}, "score"),
            (pd.Series([1, 3]), None),
            (np.array([1, 3]), None)
        ]

        for y_axis, y_index in cases:
            fake_fig = FakeBarFigure(2)
            with patch("pandas.DataFrame.plot", new_callable=MagicMock) as mock_plot:
                mock_plot.bar.return_value = fake_fig

                x_axis = "x" if isinstance(y_axis, pd.DataFrame) else ["a", "b"]
                display_bar(x_axis, y_axis, title="bar", y_index=y_index, x_label="x", y_label="y")

            self.assertEqual(fake_fig.xlabel, "x")
            self.assertEqual(fake_fig.ylabel, "y")
            self.assertEqual(fake_fig.bar_label_arg, ["container"])
            if y_index:
                self.assertEqual([bar.color for bar in fake_fig.patches], [None, "#FFA500"])

    def test_display_bar_should_return_when_input_type_invalid(self):
        with patch("pandas.DataFrame.plot", new_callable=MagicMock) as mock_plot:
            display_bar(["a"], object())

        mock_plot.bar.assert_not_called()


class TestComboboxDisplayFunctions(unittest.TestCase):

    def _rank_stats_df(self):
        return pd.DataFrame({
            "Group": ["g0", "g0", "g1"],
            "Rank": [0, 1, 2],
            "Mean(Us)": [10.0, 20.0, 30.0],
            "Min(Us)": [5.0, 15.0, 25.0],
            "Max(Us)": [15.0, 25.0, 35.0],
            "Q1(Us)": [7.0, 17.0, 27.0],
            "Median(Us)": [10.0, 20.0, 30.0],
            "Q3(Us)": [12.0, 22.0, 32.0]
        })

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.interact")
    def test_display_stats_per_rank_groups_combobox_should_create_dropdown_when_multiple_groups(self, mock_interact):
        grouped = self._rank_stats_df().groupby("Group")

        display_stats_per_rank_groups_combobox(grouped)

        mock_interact.assert_called_once()
        dropdown = mock_interact.call_args.kwargs["selected"]
        self.assertEqual(tuple(dropdown.options), ("g0", "g1"))
        self.assertEqual(dropdown.value, "g0")

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display_graph")
    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display_duration_boxplots")
    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.display")
    def test_display_stats_per_rank_groups_combobox_should_display_single_group(self, mock_display,
                                                                                mock_display_duration_boxplots,
                                                                                mock_display_graph):
        grouped = self._rank_stats_df()[lambda df: df["Group"] == "g0"].groupby("Group")

        display_stats_per_rank_groups_combobox(grouped)

        mock_display.assert_called_once()
        mock_display_duration_boxplots.assert_called_once()
        mock_display_graph.assert_called_once()

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.logger")
    def test_display_stats_per_rank_groups_combobox_should_log_when_no_groups(self, mock_logger):
        grouped = pd.DataFrame({"Group": [], "Rank": []}).groupby("Group")

        display_stats_per_rank_groups_combobox(grouped)

        mock_logger.info.assert_called_once()

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.interact")
    def test_display_stats_optional_combobox_should_create_dropdown_when_multiple_options(self, mock_interact):
        display_func = MagicMock()
        args = {"value": 1}

        display_stats_optional_combobox(["opt0", "opt1"], display_func, args, description="Choice:")

        display_func.assert_not_called()
        mock_interact.assert_called_once()
        dropdown = mock_interact.call_args.kwargs["selected"]
        self.assertEqual(tuple(dropdown.options), ("opt0", "opt1"))
        self.assertEqual(dropdown.value, "opt0")
        self.assertEqual(dropdown.description, "Choice:")

    def test_display_stats_optional_combobox_should_call_func_when_single_option(self):
        display_func = MagicMock()
        args = {"value": 1}

        display_stats_optional_combobox(["only"], display_func, args)

        display_func.assert_called_once_with("only", args)

    @patch("msprof_analyze.cluster_analyse.recipes.cluster_display.interact")
    def test_display_stats_optional_combobox_should_do_nothing_when_no_options(self, mock_interact):
        display_func = MagicMock()

        display_stats_optional_combobox([], display_func, {})

        display_func.assert_not_called()
        mock_interact.assert_not_called()
