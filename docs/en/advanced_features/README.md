# msprof-analyze Advanced Analysis

## 1. Overview

This chapter summarizes the advanced analysis features of `msprof-analyze` for cluster scenarios, covering topics such as multi-dimensional cluster information summaries, breakdown and comparison, communication bottleneck identification, and Host-side delivery issue analysis. It also supports custom analysis based on `Recipe` rules. For more information, see the [Custom Analysis Rule Development Guide](./custom_analysis_guide.md).

## 2. Preparations

The following two types of cluster data are supported:

* DB-format cluster data collected by Ascend PyTorch Profiler. For details, see [Ascend PyTorch Profiler](https://gitcode.com/Ascend/pytorch/blob/master/docs/en/developer_notes/ascend_pytorch_profiler_user_guide.md).
* Lightweight cluster DB data collected by msMonitor. For details, see [msMonitor](https://gitcode.com/Ascend/msmonitor/blob/master/docs/en/quick_start/msmonitor_quick_start.md).

When using Ascend PyTorch Profiler, you must collect or parse `db`-format results offline. Example:

```python
experimental_config = torch_npu.profiler._ExperimentalConfig(
    export_type=[torch_npu.profiler.ExportType.Db]
)
```

Alternatively, specify the export type during offline parsing:

```python
from torch_npu.profiler.profiler import analyse

if __name__ == "__main__":
    analyse(profiler_path="./result_data", export_type=["db"])
```

## 3. Feature Overview

**Feature Description**

Performs advanced analysis using `msprof-analyze`.

**Syntax**

```bash
msprof-analyze -m <feature> -d <profiling_path> [options]
```

**Parameters**

For detailed parameter descriptions, see [Command-line Options and Parameters](#51-command-line-options-and-parameters).

**Example**

```bash
msprof-analyze -m cluster_time_summary -d ./cluster_data -o ./output
msprof-analyze -m free_analysis -d ./cluster_data -o ./output
```

The command-line options in the example commands are described as follows:

- `-m`: Specifies the analysis feature.
- `-d`: Specifies the path to the profiling data.
- `-o`: Specifies the output path. If not configured, the results are saved by default in the `cluster_analysis_output` directory under the input path.

## 4. Output File Description

For details about the output deliverables of `msprof-analyze` features, see the [Recipe Result Deliverables](./recipe_output_format_introduct.md) document.

## 5. Appendix

### 5.1 Command-line Options and Parameters

#### 5.1.1 Analysis Features

##### 5.1.1.1 Breakdown and Comparison

| Analysis Feature | Description | Document Link |
| --- | --- | --- |
| cluster_time_summary | Provides a breakdown of iteration time during cluster training to help users identify performance bottlenecks. | [cluster_time_summary](./cluster_time_summary_instruct.md) |
| cluster_time_compare_summary | Provides cluster-level performance data comparison during AI execution to help users identify performance bottlenecks. | [cluster_time_compare_summary](./cluster_time_compare_summary_instruct.md) |
| module_statistic | Automatically analyzes the hierarchical structure of PyTorch models to help users accurately identify performance bottlenecks. | [module_statistic](./module_statistic_instruct.md) |
| calibrate_npu_gpu | Automatically compares NPU and GPU performance data to assist users with cross-platform performance calibration and bottleneck analysis. | [calibrate_npu_gpu](./calibrate_npu_gpu_instruct.md) |

##### 5.1.1.2 Computation

| Analysis Feature | Description | Document Link |
| --- | --- | --- |
| compute_op_sum | Summarizes computation operators executed on the device side. | - |
| freq_analysis | Identifies whether the AI Core is idle (frequency of 800 MHz) or abnormal (frequency other than 1800 MHz or 800 MHz) and provides the analysis results. | - |
| ep_load_balance | Summarizes and analyzes MoE load information. | - |
| computational_op_masking | Provides computation-communication operator overlap calculations during cluster training to help users identify performance bottlenecks. | [computational_op_masking](./computational_op_masking_instruct.md) |
| operator_mfu | Calculates kernel-level and module-level MFU based on operator FLOPs recorded on the collection side and device-side kernel durations. | [operator_mfu](./operator_mfu_instruct.md) |

##### 5.1.1.3 Communication

> [!NOTE]
>
> For CCU scenarios on the Ascend 950 products, the `communication_time_sum` and `communication_matrix_sum` analysis features are not meaningful because communication matrix and communication operator bandwidth data are not supported for collection.

| Analysis Feature | Description | Document Link |
| --- | --- | --- |
| communication_group_map | Displays communication groups and parallel strategies in cluster scenarios. | - |
| communication_time_sum | Summarizes and analyzes communication time and bandwidth in cluster scenarios. | - |
| communication_matrix_sum | Summarizes and analyzes communication matrices in cluster scenarios. | - |
| hccl_sum | Summarizes information about communication operators. | - |
| pp_chart | Analyzes and visualizes the duration for each phase of pipeline parallelism (PP). | [pp_chart](./pp_chart_instruct.md) |
| slow_rank | Displays the number of times each rank is affected by fast and slow ranks based on the current fast/slow rank statistics algorithm and identifies the causes of slow ranks. | - |
| slow_link | Summarizes operators with abnormal durations in cluster scenarios to identify slow ranks. | - |
| communication_bottleneck | For long-duration communication operators, identifies fast and slow ranks and infers the host- and device-side operations that cause communication waits. | [communication_bottleneck](./communication_bottleneck_instruct.md) |

##### 5.1.1.4 Host Delivery

| Analysis Feature | Description | Document Link |
| --- | --- | --- |
| cann_api_sum | Summarizes CANN APIs. | - |
| mstx_sum | Summarizes MSTX custom instrumentation. | - |
| free_analysis | Automatically analyzes large idle periods on the device, identifies their causes, and helps users locate performance issues. | [free_analysis](./free_analysis_instruct.md) |

##### 5.1.1.5 Other Features

| Analysis Feature | Category | Description | Document Link |
| --- | --- | --- | --- |
| export_summary | Data export | Exports API statistics and kernel details for each rank in the cluster to generate the `api_statistic.csv` and `kernel_details.csv` files. | [export_summary](./export_summary_instruct.md) |
| mstx2commop | Data processing | Converts communication information instrumented using built-in MSTX communication instrumentation into the communication operator table format. | - |
| p2p_pairing | Data processing | Generates a global association index for P2P operators and adds the output index as a new `opConnectionId` field to the `COMMUNICATION_OP` table. | - |

#### 5.1.2 Global Options and Parameters

The following table primarily describes the input, output, format, execution, and help options.

| Option/Parameter | Required (Yes/No) | Description |
| --- | --- | --- |
| `--profiling_path` or `-d` | Yes | Specifies the directory containing the collected performance data. If `-o` is not configured, running the analysis script automatically creates a `cluster_analysis_output` folder in this directory to save the analysis data. |
| `--output_path` or `-o` | No | Specifies a custom output path. Running the analysis script automatically creates a `cluster_analysis_output` folder in this directory to save the analysis data. |
| `--mode` or `-m` | No | Specifies the analysis feature. For supported values, see the [Analysis Features](#511-analysis-features) tables. |
| `--export_type` | No | Specifies the output file type. Valid values are `db` (a `.db` file), `notebook` (a Jupyter Notebook file), and `text` (text-based formats such as JSON, CSV, and Excel). The default value is `db`. |
| `--force` | No | Enables forced execution. The user assumes responsibility for the force action. When configured, this option forcibly skips the following checks:<br/>&#8226; If the specified directory or file is not owned by the current user, the ownership check is ignored and execution proceeds.<br/>&#8226; If a CSV file exceeds 5 GB, a JSON file exceeds 10 GB, or a DB file exceeds 8 GB, the file size check is ignored and execution proceeds.<br/>&#8226; Read and write permission checks for the specified directory or file are ignored and execution proceeds.<br/>Configuring this parameter enables forced execution. It is disabled by default. |
| `--parallel_mode` | No | Sets the concurrency mode for collecting multi-rank and multi-node DB data. Set it to `concurrent` to use a `concurrent.futures` process pool for concurrent execution. |
| `-v`, `-V`, or `--version` | No | Displays the version number. |
| `-h`, `-H`, or `--help` | No | Displays help information. |
| `auto-completion` | No | Enables automatic completion. After this parameter is configured, you can press **Tab** to automatically complete all sub-parameters of the `msprof-analyze` tool in the current view. |

#### 5.1.3 Basic Analysis Feature Options

| Option | Required (Yes/No) | Description |
| --- | --- | --- |
| `--rank_list` | No | Analyzes data for specified ranks. The default value is `all`, indicating that data for all ranks is analyzed. Configure this parameter based on the actual rank IDs of the ranks. The value must be an integer greater than or equal to `0`. If a specified value exceeds the rank IDs actually used for training, only data for valid rank IDs is parsed. For example, if the current environment has rank IDs `0` to `7` but the actual training uses ranks `0` to `3`, and `--rank_list` is configured as `0,3,4` or `10`, only the data for ranks `0` and `3` is parsed. Example: `--rank_list 0,1,2`.<br/>**This parameter can be used only when the corresponding analysis feature supports it. Currently, it is supported when the analysis feature is set to `cann_api_sum`, `compute_op_sum`, `hccl_sum`, or `mstx_sum`.** |
| `--step_id` | No | Specifies the performance data Step ID for analysis. The performance data for the specified Step ID is analyzed. The specified Step ID must exist in the performance data. If not configured, all data is analyzed by default. Example: `--step_id=1`.<br/>**This parameter can be used only when the corresponding analysis feature supports it. Currently, it is supported when the analysis feature is set to `cann_api_sum`, `compute_op_sum`, `hccl_sum`, or `mstx_sum`.** |
| `--top_num` | No | Sets the number of top-N time-consuming communication operators. The default value is `15`. Example: `--top_num 20`.<br/>**This parameter can be configured only when `-m` is set to `hccl_sum`.** |
| `--exclude_op_name` | No | Controls whether `op_name` is included in the `compute_op_name` results. Example: `--exclude_op_name`; no argument is required after it.<br/>**This parameter can be configured only when `-m` is set to `compute_op_sum`.** |
| `--bp` | No | Specifies the benchmark cluster data to be compared. Example: `--bp {bp_cluster_profiling_path}` compares the data in `profiling_path` with the data in `bp_cluster_profiling_path`.<br/>**This parameter can be configured only when `-m` is set to `cluster_time_compare_summary`.** |
