# Recipe Analysis Rules

This chapter summarizes the advanced analysis features of MindStudio Profiler Analyze (`msprof-analyze`) for cluster scenarios. Key areas of focus include multi-dimensional information summaries, breakdown comparisons, communication bottleneck identification, and delivery issue analysis. You can also perform custom analysis by using `Recipe` rules. For more information, see the [Custom Analysis Rule Development Guide](./custom_analysis_guide.md).

## Preparations

The tool supports the following cluster data types:

* DB-format cluster data collected by Ascend PyTorch Profiler
* Lightweight cluster DB data collected by msMonitor

For details about profile data collection, see [Profile Data Collection Guides](../getting_started/profiling_data_guide.md).

When you use Ascend PyTorch Profiler, you must collect or parse `db` results offline. Example:

```python
experimental_config = torch_npu.profiler._ExperimentalConfig(
    export_type=[torch_npu.profiler.ExportType.Db]
)
```

You can also specify the export type during offline parsing.

```python
from torch_npu.profiler.profiler import analyse

if __name__ == "__main__":
    analyse(profiler_path="./result_data", export_type=["db"])
```

## Usage

Syntax for using `msprof-analyze`:

```bash
msprof-analyze -m <feature> -d <profiling_path> [options]
```

Example:

```bash
msprof-analyze -m cluster_time_summary -d ./cluster_data -o ./output
msprof-analyze -m free_analysis -d ./cluster_data -o ./output
```

Common options:

- `-m`: specifies the analysis feature.
- `-d`: specifies the directory of profile data.
- `-o`: specifies the output path. If this option is not specified, the tool saves the results in the `cluster_analysis_output` directory within the input path.

For more information, see [Command-line Options and Parameters](#command-line-options-and-parameters).

## Analysis Features

### Breakdown and Comparison

| Analysis Feature                    | Description                                                        | Document Link                                                    |
| ---------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| cluster_time_summary         | Provides a breakdown of iteration time during cluster training to help identify performance bottlenecks.    | [cluster_time_summary](./cluster_time_summary_instruct.md)|
| cluster_time_compare_summary | Provides cluster-level profile data comparison for AI task execution to help identify performance bottlenecks.| [cluster_time_compare_summary](./cluster_time_compare_summary_instruct.md)|
| module_statistic             | Analyzes model hierarchical structures automatically for PyTorch models to help accurately locate performance bottlenecks.| [module_statistic](./module_statistic_instruct.md)|
| calibrate_npu_gpu            | Compares NPU and GPU profile data automatically to assist with cross-platform performance calibration and bottleneck analysis.| [calibrate_npu_gpu](./calibrate_npu_gpu_instruct.md)|

### Computation

| Analysis Feature                     | Description         | Document Link|
|---------------------------|-------------|---|
| compute_op_sum            | Summarizes computation operators executed on the device.| - |
| freq_analysis             | Identifies whether the AI Core is idle (frequency at 800 MHz) or abnormal (frequency not at 1800 MHz or 800 MHz) and provides the analysis results.| - |
| ep_load_balance           | Summarizes and analyzes Mixture of Experts (MoE) load information.| - |
| computational_op_masking  | Calculates the overlap between operator execution durations during cluster training to help you identify performance bottlenecks.| [computational_op_masking](./computational_op_masking_instruct.md)|

### Communication

| Analysis Feature                | Description                                                        | Document Link                                                    |
| ------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| communication_group_map  | Displays the communication group and parallel strategy in cluster scenarios.                              | -                                                            |
| communication_time_sum   | Summarizes and analyzes communication durations and bandwidth in cluster scenarios.                            | -                                                            |
| communication_matrix_sum | Summarizes and analyzes the communication matrix in cluster scenarios.                                  | -                                                            |
| hccl_sum                 | Summarizes information for communication operators.                                        | -                                                            |
| pp_chart                 | Analyzes and visualizes the duration for each phase of pipeline parallelism (PP).| [pp_chart](./pp_chart_instruct.md)          |
| slow_rank                | Identifies the causes of slow ranks and shows how often each rank is affected based on the fast and slow rank statistics algorithm.| -                                                            |
| communication_bottleneck | Identifies fast and slow ranks for long-duration communication operators, and infers the host-side or device-side operations that cause communication waits.| [communication_bottleneck](./communication_bottleneck_instruct.md)|

### Host Delivery

| Analysis Feature     | Description                                                        | Document Link                                               |
| ------------- | ------------------------------------------------------------ | ------------------------------------------------------- |
| cann_api_sum  | Summarizes CANN APIs.                                           | -                                                       |
| mstx_sum      | Summarizes MSTX custom instrumentation.                                        | -                                                       |
| free_analysis | Automatically analyzes large idle periods on the device to identify their causes and help you locate performance issues.| [free_analysis](./free_analysis_instruct.md)|

### Other Features

| Analysis Feature  | Category| Description                                    | Document Link|
|---------|----| ------------------------------------|-----|
| export_summary | Data export| Exports API statistics and kernel details for each rank in the cluster to generate the `api_statistic.csv` and `kernel_details.csv` files.| [export_summary](./export_summary_instruct.md)|
| mstx2commop | Data processing| Converts communication information from MSTX built-in communication instrumentation into the communication operator table format.| -  |
| p2p_pairing | Data processing| Generates a global association index for P2P operators and attaches the output index to the `COMMUNICATION_OP` table as a new field `opConnectionId`.| -  |

## Output File Description

For details about the output deliverables of the `msprof-analyze` features, see [Table Structures of Recipe Results and cluster_analysis.db Deliverables](./recipe_output_format_introduct.md).

### Command-line Options and Parameters

#### Global Options and Parameters

The following table primarily describes the input, output, format, execution, and help options.

| Option/Parameter               | Mandatory (Yes/No)| Description                                                                                                                                                                                                    |
| --------------------- | -------- |--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| --profiling_path or -d | Yes    | Specifies the profile data collection directory. If the `-o` option is not specified, running the analysis script automatically creates the `cluster_analysis_output` folder in this directory to save the analysis data.                                                                                                                                |
| --output_path or -o    | No    | Specifies a custom output path. Running the analysis script automatically creates the `cluster_analysis_output` folder in this directory to save the analysis data.                                                                                                                                          |
| --mode or -m           | No    | Specifies the analysis mode to execute. For details, see [Analysis Features](#analysis-features).                                                                                 |
| --export_type         | No    | Sets the format for exported data. Valid values: `db` (.db file), `notebook` (Jupyter Notebook file), and `text` (text-based formats such as JSON, CSV, and Excel). Default value: `db`.                                                                                                                              |
| --force               | No    | Enables forced execution. The user assumes responsibility for the `force` action. This option bypasses the following checks:<br>&#8226; Ownership check: Proceed even if the current user is not the owner of the specified directory or files.<br>&#8226; File size check: Proceed even if a CSV file exceeds 5 GB, a JSON file exceeds 10 GB, or a DB file exceeds 8 GB.<br>&#8226; Permission check: Proceed directly by ignoring read and write permission checks on the specified directory and files.<br>Specifying this option enables forced execution, which is disabled if not specified.|
| --parallel_mode       | No    | Sets the concurrency mode for collecting multi-rank and multi-node database data. Set it to `concurrent` to use the `concurrent.feature` process pool.                                                                                                                                      |
| -v, -V<br> or --version | No| Displays the version number.                                                                                                                                                                                                |
| -h, -H<br> or --help     | No| Displays help information for command-line options.                                                                                                                                                                                            |
| auto-completion     | No| Enables automatic completion and allows you to use the **Tab** key to automatically complete all sub-parameters for the `msprof-analyze` tool in the current view.                                                     |

#### Analysis Feature Options

| Option               | Mandatory (Yes/No)| Description                                                                                                                                                                                                                                                                                            |
| --------------------- | -------- |------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| --rank_list           | No    | Specifies a list of rank IDs for which the tool parses profile data. The default value is `all`, which indicates that the tool parses data for all ranks. Specify this option by using actual rank IDs. These IDs must be integers greater than or equal to 0. If a specified ID is larger than the range of ranks used in training, the tool parses only the data for valid rank IDs. For example, if the environment has ranks 0–7 but the training uses only ranks 0–3, and you set this option to `0,3,4,10`, the tool parses only the data for rank 0 and rank 3. Configuration example: `--rank_list 0,1,2`.<br>**This option is supported only when `-m` is set to `cann_api_sum`, `compute_op_sum`, `hccl_sum`, or `mstx_sum`.**|
| --step_id             | No| Specifies the step ID for profile data analysis. Only profile data for the specified step is analyzed. The step ID must exist within the actual profile data. By default, this option is not specified, which triggers full analysis. Configuration example: `--step_id=1`.<br>**This option is supported only when `-m` is set to `cann_api_sum`, `compute_op_sum`, `hccl_sum`, or `mstx_sum`.**                                                                                                                        |
| --top_num             | No    | Sets the number of top-N time-consuming communication operators. Default value: `15`. Configuration example: `--top_num 20`.<br>**This option is available only when `-m` is set to `hccl_sum`.**                                                                                                                                                                                                                     |
| --exclude_op_name    | No    | Specifies whether to include the operator name in the `compute_op_name` results. Example: `--exclude_op_name` (no additional argument is required).<br>**This option is available only when `-m` is set to `compute_op_sum`.**                                                                                                                                                                                            |
| --bp                 | No    | Specifies the path to the benchmark cluster profile data for comparison. For example, `--bp {bp_cluster_profiling_path}` compares data from `profiling_path` with data from `bp_cluster_profiling_path`.<br>**This option is available only when `-m` is set to `cluster_time_compare_summary`.**                                                                                                                                          |
