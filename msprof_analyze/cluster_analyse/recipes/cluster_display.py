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


def display_bar(x_axis, y_axes, title=None, y_index=None):
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

    fig = data.plot.bar(title=title)
    fig.bar_label(fig.containers[0])
    if y_index is not None and y_index in y_axes:
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

class DPAnalysisDisplay:
    '''Display plots for DP analysis results'''
    def __init__(self, df: pd.DataFrame):
        DPAnalysisDisplay._validate_input_df(df)
        self.df = df
        self.config = PlotConfig()
        self.unique_ranks = sorted(self.df['RankId'].unique())
        if len(self.unique_ranks) < 2:
            raise ValueError("At least two ranks are required for DP analysis visualization.")
        self.rank_color_map = self._init_rank_colors()
        self.rank_step_stats = self._calc_rank_step_stats()
        self.metrics_dict = self._calc_rank_metrics()
        logger.info("DP analysis visualization initialized successfully.")

    @staticmethod
    def _validate_input_df(df: pd.DataFrame):
        '''Validate input DataFrame structure'''
        required_columns = ['RankId', 'StepId', 'StartTimeMs', 'EndTimeMs', 'DurationMs', 'OutTokens']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Input DataFrame is missing required columns: {', '.join(missing_columns)}")
    
    @staticmethod
    def _get_y_bounds(token_series: pd.Series):
        '''Get y-axis bounds with some padding'''
        y_min = max(0, token_series.min() * 0.9)
        y_max = token_series.max() * 1.1
        return y_min, y_max
    
    @staticmethod
    def _validate_output_path(output_path: str):
        '''Validate output path'''
        if os.path.islink(output_path):
            raise ValueError(f"Output path cannot be a symbolic link:{output_path}")
        dir_name = os.path.dirname(output_path)
        if dir_name and not os.path.exists(dir_name):
            try:
                os.makedirs(dir_name, exist_ok=True)
            except OSError as e:
                raise OSError(f"Failed to create directory {dir_name}: {str(e)}") from e
        if os.path.exists(output_path):
            if not os.path.isfile(output_path):
                raise ValueError(f"Output path exists but is not a file: {output_path}")
            
    def plot_out_tokens_step(self,
                            output_path: str = None,
                            chart_title: str = 'OutTokens Variation Over Steps'):
        '''plot main chart of out tokens vs step id'''
        #1. get key steps for annotations(earliest and latest steps)
        earliest_rank = self.rank_step_stats.loc[self.rank_step_stats['MaxStep'].idxmin()]
        latest_rank = self.rank_step_stats.loc[self.rank_step_stats['MaxStep'].idxmax()]
        earliest_step, latest_step = int(earliest_rank['MaxStep']), int(latest_rank['MaxStep'])
        step_diff = latest_step - earliest_step
        #2. basic plot configuration
        plt.rcParams.update({
            'font.size': 12, 'axes.titlesize': 14, 'axes.labelsize': 12,
            'legend.fontsize': 10, 'figure.titlesize': 16, 'xtick.labelsize': 9,
            'ytick.labelsize': 9, 'figure.facecolor': 'white'
        })
        fig, ax = plt.subplots(figsize=(16, 10), dpi=self.config.dpi)
        y_min, y_max = DPAnalysisDisplay._get_y_bounds(self.df['OutTokens'])
        unique_steps = sorted(self.df['StepId'].unique())
        
        #3. plot trends for each rank
        for rank in tqdm(self.unique_ranks, desc="Plotting ranks"):
            rank_df = self.df[self.df['RankId'] == rank].sort_values(by='StepId')
            max_step = int(self.rank_step_stats[self.rank_step_stats['RankId'] == rank]['MaxStep'].iloc[0])
            ax.plot(
                rank_df['StepId'], rank_df['OutTokens'], 
                label=f'Rank {rank} (MaxStep={max_step})', color=self._get_rank_color(rank),
                marker='o', markersize=self.config.marker_size, linewidth=self.config.line_width,
                alpha=0.8, zorder=5
            )
        
        #4. plot vertical lines for earliest and latest steps
        def add_key_line(step: int, label: str, color: str, is_earliest: bool):
            ax.axvline(
                x=step, color=color, linestyle='--', 
                linewidth=2.0, alpha=0.8,
                label=label, zorder=6
            )
            ax.text(
                step, y_max * 0.95, label, 
                color=color, fontsize=9, fontweight='bold',
                ha='right' if is_earliest else 'left', va='center'
            )
        
        add_key_line(earliest_step, f'Earliest End Step: {earliest_step}', '#D62728', True)
        add_key_line(latest_step, f'Latest End Step: {latest_step}', '#1F77B4', False)

        #5. plot mark points for earliest and latest steps
        def mark_key_point(rank_stats: pd.Series, is_earliest: bool):
            rank_id = int(rank_stats['RankId'])
            step_id = int(rank_stats['MaxStep'])
            out_tokens = self.df[(self.df['RankId'] == rank_id) & (self.df['StepId'] == step_id)]['OutTokens'].values[0]
            
            color = '#FF7F0E' if is_earliest else '#2CA02C'
            marker = 'o' if is_earliest else 's'
            label = 'Earliest End Step' if is_earliest else 'Latest End Step'
            
            ax.plot(
                step_id, out_tokens, marker=marker, color=color, markersize=12,
                markeredgecolor='white', markeredgewidth=2, label=label, zorder=10
            )

            bubble_rate = self.metrics_dict[rank_id]['bubble_rate']
            throughput = self.metrics_dict[rank_id]['throughput']
            annot_text = (
                f'Rank {rank_id}\nStep {step_id}\nBubble Rate {bubble_rate}%\nThroughput {throughput}tokens/s'
            )
            x_offset = -4 if is_earliest else 4
            ax.annotate(
                annot_text, xy=(step_id, out_tokens), 
                xytext=(step_id + x_offset, out_tokens + y_max * 0.05),
                textcoords='data', fontsize=9, color=color, ha='right' if is_earliest else 'left',
                arrowprops=dict(arrowstyle='->', color=color, lw=1.2, alpha=0.8),
                bbox=dict(boxstyle='round,pad=0.3', fc='white', ec=color, lw=1),
                zorder=10
            )
        
        mark_key_point(earliest_rank, is_earliest=True)
        mark_key_point(latest_rank, is_earliest=False)
        
        #6. plot step difference arrow
        if step_diff > 0:
            arrow_y = y_min + (y_max - y_min) * 0.85
            text_y = arrow_y - (y_max - y_min) * 0.02

            ax.annotate(
                '', xy=(latest_step, arrow_y), xytext=(earliest_step, arrow_y),
                arrowprops=dict(arrowstyle='<->', color='#7F7F7F', 
                                linewidth=2.0, alpha=0.8, shrinkA=0, shrinkB=0),
                zorder=9
            )
            
            ax.text(
                (earliest_step + latest_step) / 2, text_y,
                f'Step Difference: {step_diff}', 
                fontsize=10, fontweight='bold', color='#7F7F7F',
                bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.95, ec='#7F7F7F', lw=1),
                ha='center', va='top', zorder=9
            )
        
        #7. plot final configuration
        ax.set_title(chart_title, fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Step ID', fontsize=14, labelpad=15)
        ax.set_ylabel('Output Tokens', fontsize=14, labelpad=15)
        
        ax.legend(loc='upper left', fontsize=10)
        ax.set_ylim(y_min, y_max)
        
        tick_interval = max(1, math.ceil(len(unique_steps) // 20)) if len(unique_steps) > 40 else 1
        ax.set_xticks(unique_steps[::tick_interval])
        ax.tick_params(axis='x', rotation=45)
        
        ax.legend(loc='center left', bbox_to_anchor=(1.01, 0.5), fontsize=10, framealpha=0.9, ncol=1, frameon=True)
        ax.grid(True, linestyle='-', alpha=0.3, linewidth=0.5)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        #8. save or show chart
        plt.tight_layout()
        plt.subplots_adjust(right=0.85)
        if output_path:
            DPAnalysisDisplay._validate_output_path(output_path)  # Validate output path if provided
            plt.savefig(output_path, dpi=self.config.dpi, bbox_inches='tight', facecolor='white')
            logger.info(f"OutTokens vs Steps chart saved to {output_path}")
        if self.config.show_chart:
            plt.show()
        plt.close(fig)
        
    def plot_rank_subplots(self,
                            output_path: str = None,
                            ncols: int = 2):
        '''plot sub charts for each rank'''
        global_earliest_step = int(self.rank_step_stats['MaxStep'].min())
        global_latest_step = int(self.rank_step_stats['MaxStep'].max())
        
        #1. subplot layout configuration
        if ncols <= 0:
            raise ValueError("ncols must be a positive integer.")
        else:
            nrows = math.ceil(len(self.unique_ranks) / ncols)
        fig, axes = plt.subplots(
            nrows=nrows, 
            ncols=ncols, 
            figsize=(10 * ncols, 6 * nrows), 
            squeeze=False, 
            dpi=self.config.dpi
            )
        fig.suptitle(
            f'Output Tokens Variation Per Rank (Earliest End Step: {global_earliest_step}, '
            f'Latest End Step: {global_latest_step})', 
            fontsize=16, fontweight='bold', y=0.98
        )
        
        #2. basic style configuration
        plt.rcParams.update({
            "font.size": 9, "axes.titlesize": 12, "axes.labelsize": 10,
            "legend.fontsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8, 
            "figure.facecolor": "white"
        })
        
        #3. Iterate over ranks to plot each subplot
        for idx, rank in enumerate(tqdm(self.unique_ranks, desc="Plotting Subplots")):
            row, col = divmod(idx, ncols)
            ax = axes[row][col]
            rank_df = self.df[self.df['RankId'] == rank].sort_values(by='StepId')
            step_stats = self.rank_step_stats[self.rank_step_stats['RankId'] == rank].iloc[0]
            step_count = int(step_stats['StepCount'])
            y_min, y_max = DPAnalysisDisplay._get_y_bounds(rank_df['OutTokens'])
            unique_steps = sorted(rank_df['StepId'].unique())
            
            # Plot line and markers
            ax.plot(
                rank_df['StepId'], rank_df['OutTokens'], 
                label=f'Rank {rank} (Steps: {step_count})',
                color=self._get_rank_color(rank),
                marker='o', markersize=self.config.marker_size, linewidth=self.config.line_width,
                alpha=0.8, zorder=5
            )
            
            ax.axvline(
                x=global_earliest_step, color='#D62728', linestyle='--',
                linewidth=2.0, alpha=0.8,
                label=f'Global Earliest End\nStep: {global_earliest_step}', zorder=6
            )
            ax.axvline(
                x=global_latest_step, color='#1F77B4', linestyle='--',
                linewidth=2.0, alpha=0.8,
                label=f'Global Latest End\nStep: {global_latest_step}', zorder=6
            )
            
            metrics = self.metrics_dict[rank]
            metrics_text = (
                f'Performance Metrics:\n'
                f'Bubble Rate: {metrics["bubble_rate"]}%\n'
                f'Throughput: {metrics["throughput"]} tokens/s\n'
                f"Total Duration: {metrics['duration']} s\n"
            )
            
            ax.text(
                x=1.05, y=0.5, s=metrics_text, 
                fontsize=8, color='#D32F2F', fontweight='bold',
                transform=ax.transAxes, va='center', ha='left', 
                bbox=dict(boxstyle='round,pad=0.4', fc='white', ec='#BDBDBD', alpha=0.9),
                zorder=10
            )
            
            ax.legend(loc='upper right', bbox_to_anchor=(0.99, 0.99), framealpha=0.95, frameon=True)
            ax.set_xlabel('Step ID', labelpad=6)
            ax.set_ylabel('Output Tokens', labelpad=6)
            ax.set_title(f'Rank {rank} Trend', fontweight='bold', pad=8)
            ax.set_ylim(y_min, y_max)
            
            tick_interval = max(1, math.ceil(len(unique_steps) // 20)) if len(unique_steps) > 40 else 1
            ax.set_xticks(unique_steps[::tick_interval])
            ax.tick_params(axis='x', rotation=45)
            
            ax.grid(True, linestyle='-', alpha=0.3, linewidth=0.5)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
        
        #4. hide unused subplots
        for idx in range(len(self.unique_ranks), nrows * ncols):
            fig.delaxes(axes[idx // ncols][idx % ncols])

        #5. save or show chart
        plt.tight_layout()
        plt.subplots_adjust(top=0.93, hspace=0.45, wspace=0.35)
        if output_path:
            DPAnalysisDisplay._validate_output_path(output_path)  # Validate output path if provided
            plt.savefig(output_path, dpi=self.config.dpi, bbox_inches='tight', facecolor='white')
            logger.info(f"Rank subplots chart saved to {output_path}")
        if self.config.show_chart:
            plt.show()
        plt.close(fig)
    
    def _init_rank_colors(self):
        '''Initialize a color map for ranks'''
        colors = list(TABLEAU_COLORS.values())
        rank_color_map = {}
        for i, rank in enumerate(self.unique_ranks):
            rank_color_map[rank] = colors[i % len(colors)]
        return rank_color_map
    
    def _calc_rank_step_stats(self):
        '''Calculate step statistics per rank'''
        rank_stats = self.df.groupby('RankId')['StepId'].agg(
            MinStep='min', 
            MaxStep='max', 
            StepCount='count'
        ).reset_index()
        return rank_stats
    
    def _calc_rank_metrics(self):
        '''
        Calculate performance metrics for each rank
        bubble rate = (global_max_step - rank_max_step) / global_max_step * 100%
        throughput = total_out_tokens / total_duration_seconds
        duration = (rank_max_end_time - rank_min_start_time) / 1000 (in seconds)
        '''
        metrics_dict = {}
        global_max_step = int(self.rank_step_stats['MaxStep'].max())
        for rank in self.unique_ranks:
            rank_df = self.df[self.df['RankId'] == rank]
            rank_stats = self.rank_step_stats[self.rank_step_stats['RankId'] == rank].iloc[0]
            rank_min_step, rank_max_step = int(rank_stats['MinStep']), int(rank_stats['MaxStep'])
            rank_min_start_time = rank_df[rank_df['StepId'] == rank_min_step]['StartTimeMs'].values[0]
            rank_max_end_time = rank_df[rank_df['StepId'] == rank_max_step]['EndTimeMs'].values[0]
            total_out_tokens = rank_df['OutTokens'].sum()
            total_duration_seconds = (rank_max_end_time - rank_min_start_time) / 1000.0
            
            if global_max_step == 0:
                bubble_rate = 0.0
            else:
                bubble_rate = round((global_max_step - rank_max_step) / global_max_step * 100, 2)
            throughput = round(total_out_tokens / total_duration_seconds, 2) if total_duration_seconds > 0 else 0.0
            duration = round(total_duration_seconds, 2)
            
            metrics_dict[rank] = {
                'bubble_rate': bubble_rate,
                'throughput': throughput,
                'duration': duration
            }
            
        return metrics_dict
    
    def _get_rank_color(self, rank_id):
        '''Get color for a given rank'''
        return self.rank_color_map.get(rank_id, '#7F7F7F')  # default gray if not found