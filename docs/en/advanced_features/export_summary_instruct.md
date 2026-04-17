# export_summary

## Overview

In cluster performance analysis scenarios, users must aggregate and compare operator information across ranks. The original cluster analysis features (which use profile data in .db format) lack a standalone capability for exporting operator information. Users must manually parse the database files for each rank to collect operator statistics.

The cluster operator information export feature (`export_summary`) allows users to export API statistics and kernel details for each rank into a tabular format. This enables users to quickly retrieve profile data for operators within the cluster.

## Preparations

**Environment Setup**

Install `msprof-analyze`. For details, see [MindStudio Profiler Analyze Installation Guide](../getting_started/install_guide.md).

**Data Preparation**

`msprof-analyze` requires an input directory containing the collected profile data. For instructions on how to collect such data, see [Data Preparation](./README.md#preparations).

## Cluster Operator Information Export

**Function**

The `export_summary` feature of the `msprof-analyze` tool exports operator information from collected cluster profile data. This process generates `apistatistic.csv` and `kerneldetails.csv` files for each rank.

**Syntax**

```bash
msprof-analyze cluster -m export_summary -d <cluster_data> 
```

**Command-line Options** 

| Option| Mandatory (Yes/No)| Description                                                    |
| ---- | --------- | -------------------------------------------------------- |
| -m   | Yes     | Specifies the analysis mode to execute. Set this it to `export_summary` to export cluster operator information.|
| -d   | Yes     | Specifies the cluster profile data directory.                                |

For details about more options, see [Command-line Options and Parameters](./README.md#command-line-options-and-parameters) of `msprof-analyze`.

**Example**

Export cluster operator information.

```bash
msprof-analyze cluster -m export_summary -d ./xxx/cluster_data 
```

**Output Description** 

* Storage location: The `api_statistic.csv` and `kernel_details.csv` files are generated in the `ASCEND_PROFILER_OUTPUT` directory of each rank.

* Files:
  * `api_statistic.csv`: API statistics
  * `kernel_details.csv`: kernel details

## Output File Description

### api_statistic.csv

The following table describes fields in the API statistics table.

| Field| Type| Description|
| --- | --- | --- |
| API Name | TEXT | API name|
| Count | INTEGER | Call count|
| Total Time(us) | REAL | Total duration (μs)|
| Avg Time(us) | REAL | Average duration (μs)|
| Min Time(us) | REAL | Minimum duration (μs)|
| Max Time(us) | REAL | Maximum duration (μs)|

### kernel_details.csv

The following table describes fields in the Kernel details table.

| Field| Type| Description|
| --- | --- | --- |
| op_name | TEXT | Operator name|
| op_type | TEXT | Operator type|
| task_type | TEXT | Task type|
| task_duration | REAL | Task duration (μs)|
| input_shapes | TEXT | Input shape|
| output_shapes | TEXT | Output shape|
| block_dim | TEXT | Block dimension|
| input_data_types | TEXT | Input data type|
| output_data_types | TEXT | Output data type|

## Precautions

1. If the `api_statistic.csv` or `kernel_details.csv` file already exists, the tool skips the generation and displays a prompt message.
2. This feature requires the input data to contain the `ascend_pytorch_profiler_{rank_id}.db` database file.
3. The exported CSV files can be used for subsequent performance analysis and comparison.

## Output Analysis

* Use `api_statistic.csv` to analyze API call frequency and execution duration distribution to identify high-frequency or time-consuming APIs.
* Use `kernel_details.csv` to analyze operator execution details, including input/output shapes and data types.
* Compare operator information across different ranks to identify inter-rank performance discrepancies.
