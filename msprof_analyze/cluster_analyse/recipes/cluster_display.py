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
import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from IPython.display import display, HTML
from ipywidgets import Dropdown, fixed, interact

logger = logging.getLogger("cluster_display")


def get_stats_cols(df):
    cols = df.columns.tolist()
    q1 = "Q1(Us)" if "Q1(Us)" in cols else "Q1~"
    q3 = "Q3(Us)" if "Q3(Us)" in cols else "Q3~"
    med = "med(Us)" if "med(Us)" in cols else "med~"
    std = "stdev" if "stdev" in cols else "stdev~"
    return q1, q3, med, std


def display_box(df, x=None, **layout_args):
    if x is None:
        x = df.columns[0]
    q1, q3, med, std = get_stats_cols(df)
    fig = go.Figure()
    fig.add_trace(
        go.Box(
            x=df[x],
            q1=df[q1],
            median=df[med],
            q3=df[q3],
            sd=df[std],
            lowerfence=df["minRank"],
            upperfence=df["maxRank"]
        )
    )
    fig.update_layout(**layout_args)
    fig.show()


def display_stats_scatter(df, x=None, **layout_args):
    if x is None:
        x = df.columns[0]
    q1, q3, med, _ = get_stats_cols(df)
    fig = go.Figure()
    col_names = [q1, med, q3, "minRank", "maxRank"]
    for name in col_names:
        fig.add_trace(
            go.Scatter(
                x=df[x],
                y=df[name],
                name=name
            )
        )
    fig.update_layout(**layout_args)
    fig.show()


def display_table_per_rank(df):
    if df.empty:
        display(df)
        return

    rank_groups = df.groupby("rank")

    def display_table(name):
        rank_df = rank_groups.get_group(name)
        rank_df = rank_df.drop(columns=["rank"])
        display(rank_df)

    dropdown = Dropdown(
        options=rank_groups.groups.keys(),
        description="rank:",
        disabled=False,
    )
    interact(
        display_table,
        name=dropdown
    )


def display_stats_per_operation(df, x=None, box=True, scatter=True, table=True, **layout_args):
    if df.empty:
        display(df)
        return

    if x is None:
        x = df.columns[0]

    op_groups = df.groupby(x)

    def display_graphs(name):
        op_df = op_groups.get_group(name)
        if table:
            display(op_df.reset_index(drop=True).set_index("rank"))
        if box:
            display_box(op_df, x=op_df["rank"], **layout_args)
        if scatter:
            display_stats_scatter(op_df, x=op_df["rank"], **layout_args)

    operations = list(op_groups.groups.keys())

    if len(operations) > 1:
        dropdown = Dropdown(
            options=operations,
            description="Operation:",
            disabled=False,
            value=operations[1]
        )
        interact(
            display_graphs,
            name=dropdown
        )
        dropdown.value = operations[0]
    else:
        display_graphs(operations[0])


def display_duration_boxplots(figs, stats_df: pd.DataFrame, orientation="v", title=None,
                              x_title="Names", y_title="Time", legend_title="Legend"):
    mean_ds = stats_df.get("Mean(Us)", None)
    min_ds = stats_df.get("Min(Us)", None)
    max_ds = stats_df.get("Max(Us)", None)
    q1_ds = stats_df.get("Q1(Us)", None)
    median_ds = stats_df.get('Median(Us)', None)
    q3_ds = stats_df.get('Q3(Us)', None)
    display_boxplot(figs, stats_df.index, min_ds, q1_ds, median_ds, q3_ds, max_ds, mean_ds,
                    orientation=orientation, title=title, x_title=x_title, y_title=y_title,
                    legend_title=legend_title)


def display_boxplot(figs, x_axis, min_ds, q1_ds, median_ds, q3_ds, max_ds, mean_ds, orientation="v",
                    title=None, x_title=None, y_title="Time", legend_title="Legend"):
    fig = go.Figure()
    fig.add_trace(
        go.Box(
            x=x_axis,
            lowerfence=min_ds,
            q1=q1_ds,
            median=median_ds,
            q3=q3_ds,
            upperfence=max_ds,
            mean=mean_ds
        )
    )
    fig.update_traces(orientation=orientation)
    fig.update_layout(
        xaxis_title=x_title, yaxis_title=y_title, legend_title=legend_title,
        title=title, height=1024
    )
    fig.show()
    if isinstance(figs, list):
        figs.append(fig)


def display_graph(figs, x_axis, y_axes, title=None,
                  x_title=None, y_title=None, legend_title="Legend"):
    if isinstance(y_axes, pd.DataFrame):
        data = y_axes.set_index(x_axis)
    elif isinstance(y_axes, dict):
        data = pd.DataFrame(y_axes, index=x_axis)
    elif isinstance(y_axes, pd.Series):
        data = pd.DataFrame({"": y_axes}, index=x_axis)
    elif isinstance(y_axes, np.ndarray):
        data = pd.DataFrame({"": pd.Series(y_axes)}, index=x_axis)
    else:
        return

    fig = data.plot.line()
    fig.update_layout(
        title=title, xaxis_title=x_title, yaxis_title=y_title, legend_title=legend_title
    )
    fig.show()
    if isinstance(figs, list):
        figs.append(fig)


def display_bar(x_axis, y_axis, title=None, y_index=None, x_label=None, y_label=None):
    if isinstance(y_axis, pd.DataFrame):
        data = y_axis.set_index(x_axis)
    elif isinstance(y_axis, dict):
        data = pd.DataFrame(y_axis, index=x_axis)
    elif isinstance(y_axis, pd.Series):
        data = pd.DataFrame({"": y_axis}, index=x_axis)
    elif isinstance(y_axis, np.ndarray):
        data = pd.DataFrame({"": pd.Series(y_axis)}, index=x_axis)
    else:
        return

    fig = data.plot.bar(title=title)
    fig.set_xlabel(x_label)
    fig.set_ylabel(y_label)
    fig.bar_label(fig.containers[0])
    if y_index is not None and y_index in y_axis:
        # get index of the top1
        top1_indices = data[y_index].nlargest(1).index
        # change the color for the top1
        for i, bar in enumerate(fig.patches):
            if data.index[i] in top1_indices:
                bar.set_color('#FFA500')  # highlight in orange


def display_stats_per_rank_groups_combobox(rank_stats_gdf):
    names = list(rank_stats_gdf.groups.keys())
    if len(names) > 1:
        dropdown = Dropdown(
            options=names, layout={"width": "max-content"}, value=names[1]
        )
        interact(
            __display_stats_per_rank_group,
            selected=dropdown,
            rank_stats_gdf=fixed(rank_stats_gdf)
        )
        dropdown.value = names[0]
    elif len(names) == 1:
        __display_stats_per_rank_group(names[0], rank_stats_gdf)
    else:
        logger.info("cluster_display func:input rank_stats_gdf groups is null so no need to display")


def __display_stats_per_rank_group(selected, rank_stats_gdf):
    df = rank_stats_gdf.get_group(selected)
    df = df.reset_index(drop=True)
    df = df.set_index(df["Rank"])
    display(df)

    figs = []
    display_duration_boxplots(figs, df, x_title="Ranks")
    display_graph(
        figs,
        df.index,
        df[["Q1(Us)", "Median(Us)", "Q3(Us)"]],
        title="50% of Distribution",
        x_title="Ranks"
    )


def display_stats_optional_combobox(options, display_func, args, description="Option:"):
    if len(options) > 1:
        dropdown = Dropdown(
            options=options, layout={"width": "max-content"}, value=options[1],
            description=description
        )
        interact(
            display_func,
            selected=dropdown,
            args=fixed(args)
        )
        dropdown.value = options[0]
    elif len(options) == 1:
        display_func(options[0], args)


COLOR_PALETTE = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
    '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5'
]


def create_legend_color_map(legends, color_palette=None):
    """创建 Rank 到颜色的映射"""
    if not color_palette:
        color_palette = COLOR_PALETTE
    unique_legends = sorted(legends.unique()) if legends is not None else []
    legend_color_map = {}
    if len(unique_legends) > len(color_palette):
        logger.warning(f"Number of unique legends exceeds the number of colors. Colors will be repeated.")
    for i, rank in enumerate(unique_legends):
        legend_color_map[rank] = color_palette[i % len(color_palette)]

    return legend_color_map


def display_duration_boxplots_with_legend(figs, stats_df: pd.DataFrame, legend_col_name=None,
                                          orientation="v", title=None, x_title="Names", y_title="Time",
                                          color_palette=None):
    # 提取统计数据
    x_axis = stats_df.index
    mean_ds = stats_df.get("Mean(Us)", None)
    min_ds = stats_df.get("Min(Us)", None)
    max_ds = stats_df.get("Max(Us)", None)
    q1_ds = stats_df.get("Q1(Us)", None)
    median_ds = stats_df.get('Median(Us)', None)
    q3_ds = stats_df.get('Q3(Us)', None)

    # 验证必要的统计列存在
    required_columns = [mean_ds, min_ds, max_ds, q1_ds, median_ds, q3_ds]
    if any(col is None for col in required_columns):
        logger.error(f"Missing required columns. Please ensure the input DataFrame contains the following columns: "
                     f"Mean(Us), Min(Us), Max(Us), Q1(Us), Median(Us), Q3(Us)")
        return

    # 创建颜色映射
    legend_ds = None
    legend_color_map = {}
    if legend_col_name is not None and legend_col_name in stats_df.columns:
        legend_ds = stats_df[legend_col_name]
        legend_color_map = create_legend_color_map(legend_ds, color_palette=color_palette)

    fig = go.Figure()
    added_legend = set()

    # 按原始顺序添加 traces
    for i, name in enumerate(x_axis):
        legend_value = legend_ds.iloc[i] if legend_ds is not None else "N/A"
        color = legend_color_map.get(legend_value, 'gray')

        # 只在第一次遇到该 legend 时显示图例
        show_legend = legend_value not in added_legend
        if show_legend:
            added_legend.add(legend_value)

        # 创建并添加 trace
        fig.add_trace(
            go.Box(
                x=[name] if orientation == "v" else None,
                y=[name] if orientation == "h" else None,
                lowerfence=[min_ds.iloc[i]],
                q1=[q1_ds.iloc[i]],
                median=[median_ds.iloc[i]],
                q3=[q3_ds.iloc[i]],
                upperfence=[max_ds.iloc[i]],
                mean=[mean_ds.iloc[i]],
                boxpoints=False,
                name=f"{legend_col_name} {legend_value}",
                showlegend=show_legend,
                marker_color=color,
                line_color=color,
                legendgroup=str(legend_value)
            )
        )

    # 更新图表布局
    axis_config = {
        'categoryorder': 'array',
        'categoryarray': list(x_axis)
    }

    fig.update_traces(orientation=orientation)
    fig.update_layout(
        xaxis_title=x_title,
        yaxis_title=y_title,
        title=title,
        height=1024,
        xaxis=axis_config if orientation == "v" else {},
        yaxis=axis_config if orientation == "h" else {}
    )

    fig.show()

    if isinstance(figs, list):
        figs.append(fig)
