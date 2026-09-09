# computational_op_masking

## 1. Overview

Large-scale cluster scenarios involve multiple compute nodes and massive amounts of data. Single-rank profile data statistics and analysis cannot evaluate the overlap degree of overall cluster operator execution.

The operator overlap linearity analysis feature (`computational_op_masking`) analyzes operator overlap durations across different parallelism scenarios during cluster training, covering both computation and communication components, to help users identify performance bottlenecks.

## 2. Preparations

**Environment Setup**

Install `msprof-analyze`. For details, see [msprof-analyze Installation Guide](../install_guide/msprof-analyze_install_guide.md).

**Data Preparation**

`msprof-analyze` requires an input directory containing the collected profile data. For instructions on how to collect such data, see [Preparations](./README.md#2-preparations).

## 3. Function

**Description**

Analyzes the collected cluster data by using the `computational_op_masking` feature of `msprof-analyze`.

**Syntax**

```bash
msprof-analyze -m computational_op_masking [--export_type <export_type>] [--step_id <step_id>] [--parallel_types <parallel_types>] -d <cluster_data> [-o <output_path>]
```

**Command-line Options** 

| Option            | Required (Yes/No)| Description                                                    |
|-------------------|------|--------------------------------------------------------------------------------------|
| -m                | Yes  | Specifies the analysis feature. Set it to `computational_op_masking` to enable fine-grained breakdown of cluster profile data.         |
| --export_type     | No   | Specifies the output file format. Currently, only the `db` format is supported.    |
| --step_id         | No   | Specifies the step ID for which results will be saved. If not specified, results for all steps are output by default.                                                |
| --parallel_types  | No   | Specifies the extent to which communication operators are overlapped by compute operators across different parallelism modes. For example, "edp,dp;dp;edp" represents [('edp','dp'), ('dp',), ('edp',)].|
| -d                | Yes  | Specifies the parent directory of the cluster profile data files.                                               |
| -o                | No   | Specifies the analysis result output directory. If not specified, results are saved to the directory specified by `-d`.              |

For details about more options, see [Command-line Options and Parameters](./README.md#51-command-line-options-and-parameters) of `msprof-analyze`.

**Example**

Perform operator overlap linearity analysis of cluster profile data.

```bash
msprof-analyze -m computational_op_masking --export_type db --step_id 11 --parallel_types "edp,dp;dp;edp" -d ./xxx/cluster_data -o ./xxx/output_path
```

**Output Description** 

The `cluster_analysis_output/cluster_analysis.db` file is generated under the directory specified by `-o`, and the `ComputationalOperatorMaskingLinearity` table is generated in this file. For details about the output files, see [Output File Description](#4-output-file-description).

## 4. Output File Description

The following table describes fields in the `ComputationalOperatorMaskingLinearity` table.

| Field                             | Type   | Description                                                    |
| ------------------------------------- | ------- | -------------------------------------------------------- |
| stepId                                | INTEGER | Iteration ID                                                |
| parallelType                          | TEXT    | Operator parallel mode                                          |
| stepStartTime                         | INTEGER | Step start time                                          |
| stepEndTime                           | INTEGER | Step end time                                          |
| totalCommunicationOperatorTime        | INTEGER | Total communication operator duration within a step                                      |
| timeRatioOfStepCommunicationOperator  | REAL    | Ratio of total communication operator duration to total step duration                    |
| totalTimeWithoutCommunicationBlackout | INTEGER | Total overlap duration of communication operators by compute operators within a step                  |
| ratioOfUnmaskedCommunication          | REAL    | Ratio of total overlap duration of communication operators by compute operators to total step duration|

Time-related fields in the preceding table are in microseconds (μs).

**Output Analysis**

* Analyze computation and communication durations to identify performance bottlenecks.
* Compare duration metrics across ranks within the cluster to locate performance issues. For example, significant fluctuations in computation duration typically indicate inter-rank desynchronization or uneven compute rank performance. Excessive variance in communication duration suggests a need to prioritize troubleshooting for parameter plane network congestion or configuration anomalies.
