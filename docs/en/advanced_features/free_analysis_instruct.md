# free_analysis

## Overview

Idle time cause analysis (`free_analysis`) provides automated analysis of significant idle blocks on the device to identify their root causes and help users troubleshoot performance issues. This feature can identify the following scenarios:

* Tasks are still being executed on the device but fall outside the scope of compute or communication statistics.
* The PyTorch layer has not dispatched tasks for an extended period (host- or framework-side idle period).
* The CANN layer exhibits abnormal dispatch or launch intervals or excessive node@launch durations.

## Preparations

**Environment Setup**

Install `msprof-analyze`. For details, see [MindStudio Profiler Analyze Installation Guide](../getting_started/install_guide.md).

**Data Preparation**

`msprof-analyze` requires an input directory containing the collected profile data. For instructions on how to collect such data, see [Data Preparation](./README.md#Preparations).

## Idle Time Cause Analysis

**Function**

Analyzes the collected cluster data by using the `free_analysis` feature of the `msprof-analyze` tool to identify the longest idle period and its root cause in each rank.

**Syntax**

```bash
msprof-analyze -m free_analysis -d <cluster_data> [-o <output_path>] [--export_type <export_type>] [--top_num <top_num>]
```

**Command-line Options**

| Option| Mandatory (Yes/No)| Description                                    |
| ---- | --------- |----------------------------------------|
| -m   | Yes     | Specifies the analysis mode to execute. Set it to `free_analysis` to enable idle time cause analysis.        |
| -d   | Yes     | Specifies the cluster profile data directory.                          |
| -o   | No     | Specifies the output directory. The default value is the directory specified by the `-d` option.                |
| --export_type | No| Specifies the output file type. The value can be `db` (default) or `text`.             |
| --top_num | No| Specifies the number of top idle periods to output for each rank (sorted by duration). The default value is `10`.|

For details about more options, see [Command-line Options and Parameters](./README.md#command-line-options-and-parameters) of `msprof-analyze`.

**Examples**

Analyze the cause of the idle period.

```bash
msprof-analyze -m free_analysis -d ./xxx/cluster_data -o ./xxx/output_path --top_num 10 --export_type text
```

**Output Description**

* When `--export_type` is set to `db`, a `cluster_analysis.db` file is generated in the output path specified by the `-o` option. The analysis results are stored in the `FreeAnalysis` table within this database.
* When `--export_type` is set to `text`, the `cluster_analysis_output/FreeAnalysis/free_analysis.csv` file is generated in the output directory specified by the `-o` option.
For details, see [Output File Description](#output-file-description).

## Output File Description

The following figure shows the analysis results of this tool.
![Output results](../figures/free_analysis.png)

**FreeAnalysis Table** 

Table field description

| Field| Description                                        |
| ---- |--------------------------------------------|
| rankId | Rank ID (`INTEGER` type)                       |
| startTime(us) | Start timestamp (`TEXT` type) of the idle period (μs)                 |
| endTime(us) | End timestamp (`TEXT` type) of the idle period (μs)                  |
| duration(us) | Duration (`REAL` type) of the idle period (μs)                  |
| pytorchIdleTime(us) | Idle time (`REAL` type) at the PyTorch layer (μs) (may be `0` or `NULL` when no data exists)|
| cannIdleTime(us) | Idle time (`REAL` type) at the CANN layer (μs) (may be `0` or `NULL` when no data exists) |
| reason | Analysis result (`TEXT` type)                      |

**free_analysis.csv**  

CSV field description

| Field| Description|
| ---- | ---- |
| Rank ID | Rank ID (`TEXT` type)|
| Start Time(us) | Start timestamp (`TEXT` type) of the idle period (μs)|
| End Time(us) | End timestamp (`TEXT` type) of the idle period (μs)|
| Duration(us) | Duration (`REAL` type) of the idle period (μs)|
| Pytorch Idle Time(us) | Idle time (`REAL` type) at the PyTorch layer (μs)|
| Cann Idle Time(us) | Idle time (`REAL` type) at the CANN layer (μs)|
| Reason | Analysis result (`TEXT` type)|
