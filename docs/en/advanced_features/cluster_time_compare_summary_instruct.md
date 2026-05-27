# cluster_time_compare_summary

## Overview

Large-scale cluster scenarios involve multiple compute nodes and massive amounts of data. Existing single-rank profile data comparison capabilities cannot evaluate the overall operational performance of a cluster.

Fine-grained cluster profile data comparison (`cluster_time_compare_summary`) provides the capability to compare profile data at the cluster level during AI task execution. By analyzing the computation, communication, and memory copy durations, it helps users identify performance bottlenecks.

## Preparations

**Environment Setup**

Install `msprof-analyze`. For details, see [MindStudio Profiler Analyze Installation Guide](../getting_started/install_guide.md).

**Data Preparation**

`msprof-analyze` requires an input directory containing the collected profile data. For instructions on how to collect such data, see [Data Preparation](.//README.md#preparations).

## Fine-grained Cluster Profile Data Comparison

**Function**

Compares and analyzes the collected cluster profile data by using the `cluster_time_compare_summary` feature of `msprof-analyze`.

**Syntax**

```bash
msprof-analyze -m cluster_time_compare_summary -d <cluster_data> --bp <base_cluster_data> [-o <output_path>]
```

**Command-line Options**

| Option| Mandatory (Yes/No)| Description                                                        |
| ---- | --------- | ------------------------------------------------------------ |
| -m   | Yes     | Specifies the analysis mode to execute. Set it to `cluster_time_compare_summary` to enable fine-grained comparison of cluster durations.|
| -d   | Yes     | Specifies the cluster profile data directory.                                    |
| --bp | Yes     | Specifies the basic cluster profile data directory.                                |
| -o   | No     | Specifies the output directory. The default value is the directory specified by the `-d` option.                  |

For details about more options, see [Command-line Options and Parameters](./README.md#command-line-options-and-parameters) of `msprof-analyze`.

**Example**

1. Execute `cluster_time_summary` analysis to perform fine-grained cluster duration breakdown.

   For details about `cluster_time_summary` analysis, see [cluster_time_summary](./cluster_time_summary_instruct.md).

   ```bash
   msprof-analyze -m cluster_time_summary -d ./xxx/cluster_data
   msprof-analyze -m cluster_time_summary -d ./xxx/base_cluster_data
   ```

2. Run the `cluster_time_compare_summary` command by passing the two directories containing data that has undergone breakdown and analysis.

   ```bash
   msprof-analyze -m cluster_time_compare_summary -d ./xxx/cluster_data --bp ./xxx/base_cluster_data -o ./xxx/output_path
   ```

**Output Description**

* Storage location: `cluster_analysis_output/cluster_analysis.db` in the output directory.
* Data table name: `ClusterTimeCompareSummary`

## Output File Description

The following table describes the fields in the `ClusterTimeCompareSummary` table.

| Field      | Type    | Description                              |
|------------|----------|----------------------------------|
| rank       | INTEGER  | Rank ID                             |
| step       | INTEGER  | Iteration number                           |
| {metrics}  | REAL     | Current cluster duration metrics (consistent with fields in the `ClusterTimeSummary` table)|
| {metrics}Base | REAL     | Corresponding duration of the benchmark cluster                      |
| {metrics}Diff | REAL     | Duration difference (current cluster duration – benchmark cluster duration), where positive values indicate a slower current cluster    |

Time-related fields in the preceding table are in microseconds (μs).

**Output Analysis**

Sort by the `{metrics}Diff` field to identify the item with the largest difference and locate the performance bottleneck.
