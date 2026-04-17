# cluster_time_summary

## Overview

Large-scale cluster scenarios involve multiple compute nodes and massive amounts of data. Single-rank profile data statistics and analysis cannot evaluate the overall operational performance of a cluster.

The original deliverable `cluster_step_trace_time.csv` does not have a dedicated execution command, making it inconvenient to use. Additionally, it does not provide metrics such as memory copies. Therefore, enhancement is required.

Fine-grained cluster profile data breakdown (`cluster_time_summary`) provides a breakdown of iteration duration during cluster training. By analyzing the computation, communication, and memory copy durations, it helps users identify performance bottlenecks.

## Preparations

**Environment Setup**

Install `msprof-analyze`. For details, see [MindStudio Profiler Analyze Installation Guide](../getting_started/install_guide.md).

**Data Preparation**

`msprof-analyze` requires an input directory containing the collected profile data. For instructions on how to collect such data, see [Data Preparation](.//README.md#preparations).

## Fine-grained Cluster Profile Data Breakdown

**Function**

Analyzes the collected cluster data by using the `cluster_time_summary` feature of `msprof-analyze`.

**Syntax**

```bash
msprof-analyze -m cluster_time_summary -d <cluster_data> [-o <output_path>]
```

**Command-line Options** 

| Option| Mandatory (Yes/No)| Description                                                    |
| ---- | --------- | -------------------------------------------------------- |
| -m   | Yes     | Specifies the analysis mode to execute. Set it to `cluster_time_summary` to enable fine-grained breakdown of cluster profile data.|
| -d   | Yes     | Specifies the cluster profile data directory.                                |
| -o   | No     | Specifies the output directory. The default value is the directory specified by the `-d` option.              |

For details about more options, see [Command-line Options and Parameters](./README.md#command-line-options-and-parameters) of `msprof-analyze`.

**Example**

Perform fine-grained breakdown of cluster profile data.

```bash
msprof-analyze -m cluster_time_summary -d ./xxx/cluster_data -o ./xxx/output_path
```

**Output Description** 

* If the export type is set to `db`, `cluster_analysis_output/cluster_analysis.db` is generated in the output directory. If the export type is set to `text`, `cluster_analysis_output/ClusterTimeSummary/cluster_time_summary_{timestamp}.csv` is generated in the output directory.

* Data table name: `ClusterTimeSummary`

  ![Output display](../figures/cluster_time_summary.png)

## Output File Description

The following table describes the fields in the `ClusterTimeSummary` table.

| Field                                | Type   | Description                                          |
| ---------------------------------------- | ------- | ---------------------------------------------- |
| rank                                     | INTEGER | Rank ID                                        |
| step                                     | INTEGER | Iteration number                                    |
| stepTime                                 | REAL    | Total iteration duration                                  |
| computation                              | REAL    | Total computation duration of operators on the NPU                       |
| communicationNotOverlapComputation       | REAL    | Communication duration not overlapped by computation                      |
| communicationOverlapComputation          | REAL    | Overlap duration of computation and communication                        |
| communication                            | REAL    | Total communication duration of operators on the NPU                       |
| free                                     | REAL    | Idle duration (total iteration duration minus computation, communication, and copy durations)|
| communicationWaitStageTime               | REAL    | Total wait duration during communication                          |
| communicationTransmitStageTime           | REAL    | Total transmission duration during communication                          |
| memory                                   | REAL    | Copy duration                                    |
| memoryNotOverlapComputationCommunication | REAL    | Copy duration not overlapped by computation or communication                |

Time-related fields in the preceding table are in microseconds (μs).

Except for the header format, the data in `cluster_time_summary_{timestamp}.csv` is consistent with that in the .db file.

**Output Analysis**

* Identify performance bottlenecks by analyzing the proportions of computation, communication, memory copy, and idle durations.
* Compare duration metrics across ranks within the cluster to locate performance issues. For example, significant fluctuations in computation duration typically indicate inter-rank desynchronization or uneven compute rank performance. Excessive variance in communication duration suggests a need to prioritize troubleshooting for parameter plane network congestion or configuration anomalies.
* The `cluster_time_compare_summary` feature can be used in conjunction to effectively locate the root cause of cluster performance deterioration.
