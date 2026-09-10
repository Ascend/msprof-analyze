# cluster_time_compare_summary

## 1. Overview

Large-scale cluster scenarios involve multiple compute nodes and massive amounts of data. Existing single-rank profile data comparison capabilities cannot evaluate the overall operational performance of a cluster.

Fine-grained cluster profile data comparison (`cluster_time_compare_summary`) provides the feature to compare profile data at the cluster level during AI task execution. By analyzing the computation, communication, and memory copy durations, it helps users identify performance bottlenecks.

## 2. Preparations

**Environment Setup**

Install `msprof-analyze`. For details, see [msprof-analyze Installation Guide](../install_guide/msprof-analyze_install_guide.md).

**Data Preparation**

`msprof-analyze` requires an input directory containing the collected profile data. For instructions on how to collect such data, see [Preparations](./README.md#2-preparations).

## 3. Function

**Description**

Compares and analyzes the collected cluster profile data by using the `cluster_time_compare_summary` feature of `msprof-analyze`.

**Syntax**

```bash
msprof-analyze -m cluster_time_compare_summary -d <cluster_data> --bp <base_cluster_data> [-o <output_path>]
```

**Command-line Options**

| Option| Required (Yes/No)| Description                                                        |
| ---- | --------- | ------------------------------------------------------------ |
| -m   | Yes     | Specifies the analysis feature. Set it to `cluster_time_compare_summary` to enable fine-grained cluster duration comparison.|
| -d   | Yes     | Specifies the parent directory of the cluster profile data files.                                    |
| --bp | Yes     | Specifies the parent directory of the basic cluster profile data files.                                |
| -o   | No     | Specifies the analysis result output directory. The default value is the directory specified by `-d`.                  |

For details about more options, see [Command-line Options and Parameters](./README.md#51-command-line-options-and-parameters) of `msprof-analyze`.

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

The `cluster_analysis_output/cluster_analysis.db` file is generated in the directory specified by `-o`. The `ClusterTimeCompareSummary` table is generated in this file. For details, see [Output File Description](#4-output-file-description).

## 4. Output File Description

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
