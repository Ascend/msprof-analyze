# communication_bottleneck

## Overview

In distributed training scenarios, communication operations are a key factor affecting overall performance. When a slow communication rank exists in a cluster, other ranks are forced to wait, which reduces the overall efficiency of the training process.

The communication bottleneck analysis (`communication_bottleneck`) feature automatically identifies slow ranks during communication operations. By comparing the task execution of fast and slow ranks, this feature locates the root cause of communication bottlenecks. It determines whether the bottleneck occurs on the host or device side and further identifies specific operations and latencies.

## Preparations

**Environment Setup**

Install `msprof-analyze`. For details, see [MindStudio Profiler Analyze Installation Guide](../getting_started/install_guide.md).

**Data Preparation**

`msprof-analyze` requires an input directory containing the collected profile data. For instructions on how to collect such data, see [Data Preparation](./README.md#preparations).

## Communication Bottleneck Analysis

**Function**

Analyzes the collected cluster data by using the `communication_bottleneck` feature of `msprof-analyze`. This feature will:

1. Analyze communication operations of a specified rank to identify the top N communication operations with the longest durations.
2. Compare the execution durations of all ranks for each communication operation to identify fast and slow ranks.
3. Perform an in-depth analysis of the causes of slow ranks when the execution duration difference between fast and slow ranks exceeds the threshold:
   - Determine whether the bottleneck is Host Bound or Device Bound.
   - Locate the specific operations and latency durations causing the delay.

**Syntax**

```bash
msprof-analyze -m communication_bottleneck -d <cluster_data> [-o <output_path>] [--rank_id <rank_id>] [--top_num <top_num>] [--export_type <export_type>]
```

**Command-line Options**

| Option| Mandatory (Yes/No)| Description|
| ---- | --------- | -------------------------------------------------------- |
| -m   | Yes     | Specifies the analysis mode to execute. Set it to `communication_bottleneck` to enable communication bottleneck analysis.|
| -d   | Yes     | Specifies the cluster profile data directory.|
| -o   | No     | Specifies the output directory. The default value is the directory specified by the `-d` option.|
| --rank_id | No| Specifies the ID of the target rank to be analyzed. The default value is `0`. Analyze the communication operations of the rank and compare the execution status of all ranks.|
| --top_num | No| Specifies the number of top N communication operations to be analyzed. The default value is `10`. This option restricts the analysis to only the N communication operations with the longest execution durations.|
| --export_type | No| Specifies the output file type. The value can be `db` (default) or `text`.             |

For details about more options, see [Command-line Options and Parameters](./README.md#command-line-options-and-parameters) of `msprof-analyze`.

**Examples**

1. (Optional) Modify the configuration file.
You can modify the analysis thresholds in the configuration file based on the actual situation. For details about the configuration file, see [Configuration Description](#configuration-description).

2. Perform communication bottleneck analysis to analyze the 10 communication operations with the longest execution durations in rank 0.

```bash
msprof-analyze -m communication_bottleneck -d ./xxx/cluster_data -o ./xxx/output_path --rank_id 0 --top_num 10
```

**Output Description**

 * If `export_type` is set to `db`, the results are saved to the `CommunicationBottleneck` table in `cluster_analysis.db`.
 * If `export_type` is set to `text`, the results are saved as a .csv file: `communication_bottleneck.csv`.

## Configuration Description

The `communication_bottleneck` feature supports custom analysis thresholds by using a configuration file. The configuration file is as follows:

```bash
msprof_analyze/cluster_analyse/recipes/communication_bottleneck/config.json
```

The format of the configuration file is as follows:

```json
{
    "threshold": {
        "slow_npu_happen": 0.05,
        "diff_waiting_time": 100000,
        "start_ns_shifted": 1000000,
        "device_bound_proportion": 0.5
    }
}
```

Parameters

| Parameter| Mandatory (Yes/No)| Description|
| ---- | --------- | ---- |
| slow_npu_happen | No| Ratio threshold for fast/slow rank detection. If the time difference ratio between fast and slow ranks is less than this value, no slow rank issue is identified. The value is of the `float` type and the default value is `0.05` (0.05%).|
| diff_waiting_time | No| Wait duration difference threshold. If the device-side wait duration exceeds the host-side wait duration by more than this value (approximately 100 μs), a device-bound issue is identified. The value is of the `int` type and the default value is `100000` (ns).|
| start_ns_shifted | No| Start time shift threshold. If the actual shift is less than this value (approximately 1 ms), the start time is considered aligned. The value is of the `int` type and the default value is `1000000` (ns).|
| device_bound_proportion | No| Proportion threshold for device-bound issues. If the proportion of device-bound issues exceeds this value, it is identified as a device-side bottleneck. The value is of the `float` type and the default value is `0.5` (0.5%).|

## Output File Description

**CommunicationBottleneck Table**

Table field description

| Field      | Description                              |
| -------------- |----------------------------------|
| startTime(us)  | Start timestamp (`TEXT` type) of the communication operator on the target rank (μs)|
| endTime(us)    | End timestamp (`TEXT` type) of the communication operator on the target rank (μs) |
| duration(us)   | Duration (`REAL` type) of the communication operator on the target rank (μs) |
| communicationOp| Name (`TEXT` type) of the communication operator                 |
| slowRankId     | Slow rank ID (`INTEGER` type) (valid when fast and slow ranks exist)       |
| fastRankId     | Fast rank ID (`INTEGER` type) (valid when fast and slow ranks exist)       |
| reason         | Analysis result (`TEXT` type)                    |

**communication_bottleneck.csv**

CSV field description

| Field        | Description                             |
|------------------|---------------------------------|
| Start Time(us)   | Start timestamp (`TEXT` type) of the communication operator on the target rank (μs)|
| End Time(us)     | End timestamp (`TEXT` type) of the communication operator on the target rank (μs)|
| Duration(us)     | Duration (`REAL` type) of the communication operator on the target rank (μs)|
| Communication Op | Name (`TEXT` type) of the communication operator                |
| Slow Rank ID     | Slow rank ID (`INTEGER` type) (valid when fast and slow ranks exist)                 |
| Fast Rank ID     | Fast rank ID (`INTEGER` type) (valid when fast and slow ranks exist)                 |
| Reason           | Analysis result (`TEXT` type)            |
