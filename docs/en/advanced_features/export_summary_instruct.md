# export_summary

## 1. Overview

In cluster performance analysis scenarios, users must aggregate and compare operator information across ranks. The original cluster analysis features (which use profile data in .db format) lack a standalone capability for exporting operator information. Users must manually parse the database files for each rank to collect operator statistics.

The cluster operator information export feature (`export_summary`) allows users to export API statistics and kernel details for each rank into a tabular format. This enables users to quickly retrieve profile data for operators within the cluster.

## 2. Preparations

**Environment Setup**

Install `msprof-analyze`. For details, see [msprof-analyze Installation Guide](../install_guide/msprof-analyze_install_guide.md).

**Data Preparation**

`msprof-analyze` requires an input directory containing the collected profile data. For instructions on how to collect such data, see [Preparations](./README.md#2-preparations).

> [!NOTE]
>
> This feature requires the input data to contain the `ascend_pytorch_profiler_{rank_id}.db` database file.

## 3. Function

**Description**

Exports operator information from collected cluster profile data. This process generates `apistatistic.csv` and `kerneldetails.csv` files for each rank.

**Syntax**

```bash
msprof-analyze cluster -m export_summary -d <cluster_data> 
```

**Command-line Options** 

| Option | Required (Yes/No) | Description |
| --- | --- | --- |
| -m | Yes | Specifies the analysis feature. Set this to `export_summary` to export cluster operator information. |
| -d | Yes | Specifies the parent directory of the cluster profile data files. |

For details about more options, see [Command-line Options and Parameters](./README.md#51-command-line-options-and-parameters) of `msprof-analyze`.

**Example**

Export cluster operator information.

```bash
msprof-analyze cluster -m export_summary -d ./xxx/cluster_data 
```

**Output Description** 

The following files are generated in the `ASCEND_PROFILER_OUTPUT` directory of each rank:

* `api_statistic.csv`: API statistics
* `kernel_details.csv`: kernel details

For details, see [Output File Description](#4-output-file-description).

> [!NOTE]
>
> - If the `api_statistic.csv` or `kernel_details.csv` file already exists, the tool skips generation and displays a message.
> - The exported CSV files can be used for subsequent performance analysis and comparison.

## 4. Output File Description

### 4.1 `api_statistic.csv`

The following table describes fields in the API statistics table.

| Field | Type | Description |
| --- | --- | --- |
| API Name | TEXT | API name |
| Count | INTEGER | Call count |
| Total Time(us) | REAL | Total duration (μs) |
| Avg Time(us) | REAL | Average duration (μs) |
| Min Time(us) | REAL | Minimum duration (μs) |
| Max Time(us) | REAL | Maximum duration (μs) |

### 4.2 `kernel_details.csv`

The following table describes fields in the kernel details table.

| Field | Type | Description |
| --- | --- | --- |
| op_name | TEXT | Operator name |
| op_type | TEXT | Operator type |
| task_type | TEXT | Task type |
| task_duration | REAL | Task duration (μs) |
| input_shapes | TEXT | Input shape |
| output_shapes | TEXT | Output shape |
| block_dim | TEXT | Block dimension |
| input_data_types | TEXT | Input data type |
| output_data_types | TEXT | Output data type |

## 4.3 Output Analysis

* Use `api_statistic.csv` to analyze API call frequency and execution duration distribution to identify high-frequency or time-consuming APIs.
* Use `kernel_details.csv` to analyze operator execution details, including input/output shapes and data types.
* Compare operator information across different ranks to identify inter-rank performance discrepancies.
