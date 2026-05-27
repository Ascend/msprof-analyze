# Table Structures of Recipe Results and `cluster_analysis.db` Deliverables

> [!NOTE]NOTE
>
> - When `msprof-analyze` is configured with the `--mode` option, the profile data is analyzed and the `cluster_analysis.db` deliverables are generated. This topic describes the table structures and fields of these deliverables.
>
> - Some analysis features do not generate the `cluster_analysis.db` file.

## `cluster_step_trace_time.csv`

Generated when the data parsing mode is `communication_matrix`, `communication_time`, or `all`.

Column A: **Steps**. This column is set during profile data collection. Generally, profile data for a single step is sufficient for cluster performance analysis. If multiple steps are collected, filter them first.

Column B: **Type**. Valid values are `rank` and `stage`, which are closely related to the index. `rank` represents a single rank, while `stage` represents a rank group (PP parallel stage). If the type is `stage`, the information in columns D through K represents the maximum values within the rank group.

Column C: **Index**. This column is related to the type and indicates the device ID.

Column D: **Computing**. This column displays the computation duration.

Column E: **Communication (Not Overlapped)**. This column displays the communication duration not overlapped by computation.

Column F: **Overlapped**. This column displays the duration where computation and communication overlap.

Column G: **Communication**. This column displays the total communication duration.

Column H: **Free**. This column displays the idle duration, which indicates the duration where the device is neither communicating nor computing. This may include the SDMA copy and idle wait durations.

Column I: **Stage**. This column and the following two columns are valid only for PP parallelism. Stage duration represents the total time excluding the duration of `receive` operators.

Column J: **Bubble**. This column displays the bubble time, which is the sum of the duration of all `receive` operators.

Column K: **Communication (Not Overlapped and Exclude Receive)**. This column indicates the communication duration that is not overlapped and excludes the duration of `receive` operators.

Column L: **Preparing**. This column displays the duration from the start of an iteration to the execution of the first computation or communication operator.

Column M: **DP Index**. This column displays the index of the DP group to which the cluster data belongs after being partitioned based on the parallel strategy. If the data is not collected, this column is not displayed.

Column N: **PP Index**. This column displays the index of the PP group to which the cluster data belongs after being partitioned based on the parallel strategy. If not collected, this column is not displayed.

Column O: **TP Index**. This column displays the index of the TP group to which the cluster data belongs after being partitioned based on the parallel strategy. If not collected, this column is not displayed.

**Tips**: Filter Column B by the `stage` type to check for issues between stages. Then, filter Column B by the `rank` type to check for issues between ranks. Perform the following troubleshooting checks:

* Check for slow ranks or load imbalance based on the computation duration difference.

* Check for host-bound issues or uneven distribution based on the idle duration statistics.

* Check for excessive communication duration based on the duration displayed in the **Communication (Not Overlapped and Exclude Receive)** column.

* Check whether the bubble configuration is appropriate and whether imbalance exists between stages based on the proportion of bubble time and the theoretical calculation formula.

Theoretically, the values for these durations should remain relatively consistent. If the difference between the maximum and minimum values exceeds 5%, a slow rank may exist.

## `cluster_communication_matrix.json`

Generated when the data parsing mode is `communication_matrix` or `all`.

Open the JSON file using VS Code or a JSON viewer and search for `Total`. There will be multiple results. Generally, the structure of the link bandwidth information is as follows:

```bash
{src_rank}-{dst_rank}: {
    "Transport Type": "LOCAL",
    "Transit Time(ms)": 0.02462,
    "Transit Size(MB)": 16.777216,
    "Bandwidth(GB/s)": 681.4466
}
```

**Tips**: You can identify slow link issues based on the rank interconnection bandwidth and the link type.

- `LOCAL`: represents on-chip copy, which provides the highest speed.
- `HCCS` or `PCIE`: represents intra-node inter-chip copy, which provides medium speed.
- `RDMA`: represents inter-node copy, which provides the lowest speed.

## `cluster_communication.json`

Generated when the data parsing mode is set to `communication_time` or `all`.
It mainly provides the communication duration data.

## `compute_op_sum`

When `-m compute_op_sum` is set, the following tables are generated.

### `ComputeOpAllRankStats`

Description:

Provides statistical analysis of computation duration for all ranks, grouped by `OpType` and `TaskType`. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| OpType   | TEXT    | Computation operator type                          |
| TaskType | TEXT    | Accelerator type for operator execution                   |
| Count    | INTEGER | Number of operators grouped by `OpType` and `TaskType`|
| MeanNs   | REAL    | Average duration                          |
| StdNs    | REAL    | Standard deviation of the duration                          |
| MinNs    | REAL    | Minimum duration                          |
| Q1Ns     | REAL    | 25th percentile of duration                       |
| MedianNs | REAL    | 50th percentile of duration                       |
| Q3Ns     | REAL    | 75th percentile of duration                       |
| MaxNs    | REAL    | Maximum duration                          |
| SumNs    | REAL    | Total duration                            |

### `ComputeOpPerRankStatsByOpType`

Description:

Provides statistical analysis of computation duration for each rank, grouped by `OpType` and `TaskType`. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| OpType   | TEXT    | Computation operator type                          |
| TaskType | TEXT    | Accelerator type for operator execution                   |
| Count    | INTEGER | Number of operators grouped by `OpType` and `TaskType`|
| MeanNs   | REAL    | Average duration                          |
| StdNs    | REAL    | Standard deviation of the duration                          |
| MinNs    | REAL    | Minimum duration                          |
| Q1Ns     | REAL    | 25th percentile of duration                       |
| MedianNs | REAL    | 50th percentile of duration                       |
| Q3Ns     | REAL    | 75th percentile of duration                       |
| MaxNs    | REAL    | Maximum duration                          |
| SumNs    | REAL    | Total duration                            |
| Rank     | INTEGER | Rank ID                              |

### `ComputeOpPerRankStatsByOpName`

Description:

Not generated when the `--exclude_op_name` option is specified.
It provides a statistical analysis of computation duration for each rank, grouped by `OpName`, `OpType`, `TaskType`, and `InputShapes`. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| OpName      | TEXT    | Computation operator name                          |
| OpType      | TEXT    | Computation operator type                          |
| TaskType    | TEXT    | Accelerator type for operator execution                   |
| InputShapes | TEXT    | Input shape of the operator                        |
| Count       | INTEGER | Number of operators in this group                    |
| MeanNs      | REAL    | Average duration                          |
| StdNs       | REAL    | Standard deviation of the duration                          |
| MinNs       | REAL    | Minimum duration                          |
| Q1Ns        | REAL    | 25th percentile of duration                       |
| MedianNs    | REAL    | 50th percentile of duration                       |
| Q3Ns        | REAL    | 75th percentile of duration                       |
| MaxNs       | REAL    | Maximum duration                          |
| SumNs       | REAL    | Total duration                            |
| Rank        | INTEGER | Rank ID                              |

## `cann_api_sum`

When `-m cann_api_sum` is set, the following tables are generated:

### `CannApiSum`

Description:

Provides statistical analysis of the duration of each unique API across all ranks. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| name           | TEXT    | API name                          |
| timeRatio      | REAL    | Percentage of the duration of the API relative to the total duration of all APIs|
| totalTimeNs    | INTEGER | Total duration of the API                   |
| totalCount     | INTEGER | Number of APIs                     |
| averageNs      | REAL    | Average duration                      |
| Q1Ns           | REAL    | 25th percentile of duration                   |
| medNs          | REAL    | 50th percentile of duration                   |
| Q3Ns           | REAL    | 75th percentile of duration                   |
| minNs          | REAL    | Minimum duration                      |
| maxNs          | REAL    | Maximum duration                      | 
| stdev          | REAL    | Standard deviation of the duration                      |
| minRank        | TEXT    | A set of ranks corresponding to `minNs`             |
| maxRank        | TEXT    | A set of ranks corresponding to `maxNs`             |

### `CannApiSumRank`

Description:

Provides statistical analysis of the duration of each unique API on each rank. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| name          | TEXT    | API name           |
| durationRatio | REAL    | Percentage of the duration of the API relative to the total duration of all APIs on the rank|
| totalTimeNs   | INTEGER | Total duration of the API       |
| totalCount    | INTEGER | Number of APIs         |
| averageNs     | REAL    | Average duration      |
| minNs         | REAL    | Minimum duration      |
| Q1Ns          | REAL    | 25th percentile of duration   |
| medNs         | REAL    | 50th percentile of duration   |
| Q3Ns          | REAL    | 75th percentile of duration   |
| maxNs         | REAL    | Maximum duration      |
| stdev         | REAL    | Standard deviation of the duration      |
| rank          | INTEGER | Rank ID          |

## `hccl_sum`

When `-m hccl_sum` is set, the following tables are generated:

### `HcclAllRankStats`

Description:

Provides statistical analysis of the duration of each communication operator type (such as `hcom_broadcast_`) across all ranks. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| OpType   | TEXT    | Communication operator type   |
| Count    | INTEGER | Count          |
| MeanNs   | REAL    | Average duration   |
| StdNs    | REAL    | Standard deviation of the duration   |
| MinNs    | REAL    | Minimum duration   |
| Q1Ns     | REAL    | 25th percentile of duration|
| MedianNs | REAL    | 50th percentile of duration|
| Q3Ns     | REAL    | 75th percentile of duration|
| MaxNs    | REAL    | Maximum duration   | 
| SumNs    | REAL    | Total duration     |

### `HcclPerRankStats`

Description:

Provides statistical analysis of the duration of each communication operator type (such as `hcom_broadcast_`) on each rank. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| OpType   | TEXT    | Communication operator type   |
| Count    | INTEGER | Count          |
| MeanNs   | REAL    | Average duration   |
| StdNs    | REAL    | Standard deviation of the duration   |
| MinNs    | REAL    | Minimum duration   |
| Q1Ns     | REAL    | 25th percentile of duration|
| MedianNs | REAL    | 50th percentile of duration|
| Q3Ns     | REAL    | 75th percentile of duration|
| MaxNs    | REAL    | Maximum duration   | 
| SumNs    | REAL    | Total duration     |
| Rank     | INTEGER | Rank ID       |

### `HcclGroupNameMap`

Description:

Provides a mapping of ranks contained within each communication group.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| GroupName | TEXT | Communication group, such as `{ip_address}%enp67s0f5_60000_0_1708156014257149`|
| GroupId   | TEXT | Last three digits of the hash value of the communication group|
| Ranks     | TEXT | All ranks within the communication group|

### `HcclTopOpStats`

Description:

Provides an analysis of the computation duration for all communication operators across all ranks. It displays data for the top N (default value: `15`) communication operators with the largest average durations. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| OpName   | TEXT    | Communication operator name, such as `hcom_allReduce__606_0_1`|
| Count    | INTEGER | Count          |
| MeanNs   | REAL    | Average duration   |
| StdNs    | REAL    | Standard deviation of the duration   |
| MinNs    | REAL    | Minimum duration   |
| Q1Ns     | REAL    | 25th percentile of duration|
| MedianNs | REAL    | 50th percentile of duration|
| Q3Ns     | REAL    | 75th percentile of duration|
| MaxNs    | REAL    | Maximum duration   | 
| SumNs    | REAL    | Total duration     |
| MinRank  | INTEGER | Rank with the minimum duration for the communication operator|
| MaxRank  | INTEGER | Rank with the maximum duration for the communication operator|

## `mstx_sum`

When `-m mstx_sum` is set, the following tables are generated:

### `MSTXAllFrameworkStats`

Description:

Provides statistical analysis of the framework-side duration of MSTX instrumentation. This analysis is based on cluster profile data in `db` format and does not distinguish between ranks.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| Name     | TEXT    | Information carried by the MSTX instrumentation data|
| Count    | INTEGER | Number of instrumentation events grouped by `Name` within the iteration|
| MeanNs   | REAL    | Average duration|
| StdNs    | REAL    | Standard deviation of the duration|
| MinNs    | REAL    | Minimum duration|
| Q1Ns     | REAL    | 25th percentile of duration|
| MedianNs | REAL    | 50th percentile of duration|
| Q3Ns     | REAL    | 75th percentile of duration|
| MaxNs    | REAL    | Maximum duration|
| SumNs    | REAL    | Total duration|
| StepId   | INTEGER | Iteration ID|

### `MSTXAllCannStats`

Description:

Provides statistical analysis of the CANN-layer duration of MSTX instrumentation. This analysis is based on cluster profile data in `db` format and does not distinguish between ranks.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| Name     | TEXT    | Information carried by the MSTX instrumentation data|
| Count    | INTEGER | Number of instrumentation events grouped by `Name` within the iteration|
| MeanNs   | REAL    | Average duration|
| StdNs    | REAL    | Standard deviation of the duration|
| MinNs    | REAL    | Minimum duration|
| Q1Ns     | REAL    | 25th percentile of duration|
| MedianNs | REAL    | 50th percentile of duration|
| Q3Ns     | REAL    | 75th percentile of duration|
| MaxNs    | REAL    | Maximum duration|
| SumNs    | REAL    | Total duration|
| StepId   | INTEGER | Iteration ID|

### `MSTXAllDeviceStats`

Description:

Provides statistical analysis of the device-side duration of MSTX instrumentation. This analysis is based on cluster profile data in `db` format and does not distinguish between ranks.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| Name     | TEXT    | Information carried by the MSTX instrumentation data|
| Count    | INTEGER | Number of instrumentation events grouped by `Name` within the iteration|
| MeanNs   | REAL    | Average duration|
| StdNs    | REAL    | Standard deviation of the duration|
| MinNs    | REAL    | Minimum duration|
| Q1Ns     | REAL    | 25th percentile of duration|
| MedianNs | REAL    | 50th percentile of duration|
| Q3Ns     | REAL    | 75th percentile of duration|
| MaxNs    | REAL    | Maximum duration|
| SumNs    | REAL    | Total duration|
| StepId   | INTEGER | Iteration ID|

### `MSTXMarkStats`

Description:

Provides statistical analysis of the duration of MSTX instrumentation for each rank, grouped by `Rank` and `StepId`. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| Name                | TEXT    | Information carried by the MSTX instrumentation data|
| FrameworkDurationNs | REAL    | Framework-side duration|
| CannDurationNs      | REAL    | CANN layer duration|
| DeviceDurationNs    | REAL    | Device-side duration|
| Rank                | INTEGER | global rank |
| StepId              | INTEGER | Iteration ID|

## `communication_group_map`

When `-m communication_group_map` is set, the following tables are generated:

### `CommunicationGroupMapping`

Description:

Provides the mapping between communication groups and parallel strategies based on the cluster profile data in `db` format.

Table fields

| Field| Type| Description                                                               |
| ------ | ---- |-------------------------------------------------------------------|
| type       | TEXT | Operator type (`collective` or `p2p`). Operators with names containing `send`, `recv`, or `receive` are classified as `p2p`.  |
| rank_set   | TEXT | A set of ranks (global ranks) within the communication group.                                         |
| group_name | TEXT | Hash value of the communication group, which maps to `group_id`.                                           |
| group_id   | TEXT | Communication group name defined within HCCL, such as `{ip_address}%enp67s0f5_60000_0_1708156014257149`|
| pg_name    | TEXT | Service-defined communication group name (such as `dp`, `dp_cp`, and `mp`).                                |

## `cluster_time_summary`

When `-m cluster_time_summary` is set, the following tables are generated:

Note: This table is similar to `cluster_step_trace_time.csv`, which will be replaced later.

### `ClusterTimeSummary`

Description:

Provides statistical analysis of cluster duration for all ranks to facilitate performance issue identification. This analysis is based on cluster profile data in `db` format.

Table fields (time unit: μs)

| Field| Type| Description|
| ------ | ---- | ---- |
| rank           | INTEGER | global rank |
| step           | INTEGER | Iteration ID|
| stepTime       | REAL    | Total iteration duration|
| computation    | REAL    | Total computation duration|
| communicationNotOverlapComputation       | REAL | Communication duration not overlapped by computation|
| communicationOverlapComputation          | REAL | Duration of the overlap between computation and communication|
| communication  | REAL    | Total communication duration|
| free           | REAL    | Idle time (total duration when the device is neither communicating nor computing, excluding asynchronous memory copy)|
| communicationWaitStageTime               | REAL | Total communication wait duration|
| communicationTransmitStageTime           | REAL | Total communication transmission duration|
| memory         | REAL    | Total asynchronous memory copy duration|
| memoryNotOverlapComputationCommunication | REAL | Total duration of asynchronous memory copy not overlapped by computation or communication| 
| taskLaunchDelayAvgTime                   | REAL | Delivery duration (average duration from the start of the host-side API to the start of the device-side task)|

## `cluster_time_compare_summary`

When `-m cluster_time_compare_summary` is set, the following tables are generated.

Note: This analysis feature requires the `cluster_time_summary` results. Both cluster data and benchmark cluster data must contain a `cluster_analysis.db` file including the `ClusterTimeSummary` table.

### `ClusterTimeCompareSummary`

Description: Provides a comparison between the current cluster and the benchmark cluster. For example, `computationDiff` indicates the difference in computation time between the current cluster and the benchmark cluster. A positive `computationDiff` value indicates the current cluster computation time exceeds that of the benchmark cluster, while a negative value indicates the opposite.

Table fields (time unit: μs)

| Field         | Type| Description|
|--------------| ---- | ---- |
| rank         | INTEGER | global rank |
| step         | INTEGER | Iteration ID|
| stepTime     | REAL    | Iteration duration for current cluster data|
| stepTimeBase | REAL    | Computation time for benchmark cluster data|
| stepTimeDiff | REAL    | Difference in iteration duration|
|......|-|Some fields omitted (for the `ClusterTimeSummary` table, current cluster data, benchmark cluster data, and the difference between the two are displayed)|
| taskLaunchDelayAvgTime     | REAL | Delivery duration for current cluster data|
| taskLaunchDelayAvgTimeBase   | REAL | Delivery duration for benchmark cluster data|
| taskLaunchDelayAvgTimeDiff | REAL | Difference in delivery duration|

## `freq_analysis`

Description:

Provides AI Core frequency analysis to enable one-click NPU frequency reduction detection. This analysis is based on cluster profile data in `db` format. There are three frequency scenarios:

* Normal: The frequency remains stable at 1800 MHz.
* Idle state: When the NPU is idle for an extended period, the device automatically reduces the frequency to 800 MHz.
* Abnormal reduction: When NPU frequency reduction occurs due to other factors, abnormal frequencies apart from 1800 MHz and 800 MHz are detected.

When `-m freq_analysis` is set, the following tables are generated if frequency reduction occurs.

### `FreeFrequencyRanks`

Description:

Idle state: When the NPU is idle for an extended period, the device automatically reduces the frequency to 800 MHz.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| rankId          | INTEGER | global rank |
| aicoreFrequency | TEXT    | [800, 1800] |

### `AbnormalFrequencyRanks`

Description:

Abnormal reduction: When NPU frequency reduction occurs due to other factors, abnormal frequencies apart from 1800 MHz and 800 MHz are detected.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| rankId          | INTEGER | global rank |
| aicoreFrequency | TEXT    | List of frequencies in abnormal reduction scenarios, such as [800, 1150, 1450, 1800]|

## `ep_load_balance`

Description:

In cluster training scenarios, MoE load imbalance refers to the uneven distribution of tasks across different expert models in a distributed environment, causing some expert models to overload while others remain idle. This imbalance reduces overall system efficiency and creates potential performance bottlenecks.

When `-m ep_load_balance` is set, the following tables are generated.

### `EPTokensSummary`

Description:

Provides `GroupedMatmul` operator shape analysis. This analysis is based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| rank               | INTEGER | global rank |
| epRanks            | TEXT    | A set of ranks within the same Expert Parallelism (EP) group, such as [rank0,rank1]|
| inputShapesSummary | INTEGER | Sum of the first dimension of all `input_shapes` for the `GroupedMatmul` operator on this rank|

### `TopEPTokensInfo`

Description:

Provides information about EP groups with load imbalance.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| epRanks    | TEXT    | A set of ranks within the EP group with load imbalance, such as [rank0, rank1]|
| tokensDiff | INTEGER | Difference between the maximum and minimum values within the same EP group|

## `mstx2commop`

When `-m mstx2commop` is set, `cluster_analysis.db` is not generated, and the built-in communication instrumentation data is converted into communication operators.

**Note: This setting generates a new `COMMUNICATION_OP` table. You are advised to use it in combination with `Level_none`. Otherwise, the original table structure will be damaged.**

Output:

When `Level_none` is set, the unified database does not contain a `COMMUNICATION_OP` table. This analysis feature converts built-in communication instrumentation data into communication operators for display in MindStudio Insight.

## `slow_rank`

When `-m slow_rank` is set, the following tables are generated.

### `SlowRank`

Description:

Provides slow rank analysis based on cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| rankId          | INTEGER | Slow rank   |
| slowAffectCount | INTEGER | Number of communications affected by this rank|

### `SlowOpStats`

Description:

Provides communication operator statistics corresponding to slow rank bottleneck locations. This analysis is based on cluster profile data in `db` format.

Table fields

| Field      | Type| Description            |
|-----------| ---- |----------------|
| SlowRank  | TEXT    | Slow rank ID      |
| OpName    | TEXT    | Communication operator name         |
| GroupName | TEXT    | Communication group name         |
| Timestamp | TEXT    | Communication operator timestamp       |
| Count     | INTEGER | Count            |
| MeanNs    | REAL    | Average duration        |
| StdNs     | REAL    | Standard deviation of the duration        |
| MinNs     | REAL    | Minimum duration        |
| Q1Ns      | REAL    | 25th percentile of duration     |
| MedianNs  | REAL    | 50th percentile of duration     |
| Q3Ns      | REAL    | 75th percentile of duration     |
| MaxNs     | REAL    | Maximum duration        | 
| SumNs     | REAL    | Total duration         |
| MinRank   | INTEGER | Rank with the minimum duration for the communication operator|
| MaxRank   | INTEGER | Rank with the maximum duration for the communication operator|

## `p2p_pairing`

When `-m p2p_pairing` is set, `cluster_analysis.db` is not generated.

This analysis feature displays P2P operator connection lines, allowing users to identify the source rank (`src_rank`) and destination rank (`dst_rank`) for send and receive operations. **Currently, MindStudio Insight does not support this feature.**

Output:

An `opConnectionId` column is added to the `COMMUNICATION_OP` table in the `ascend_pytorch_profiler_{rank_id}.db` file of the cluster data. P2P operators across different ranks can be linked based on this operator connection ID (`opConnectionId`).

## `pp_chart`

Note: This capability requires lightweight instrumentation before and after forward and backward passes. Use `msprof-analyze` for processing and MindStudio Insight for result visualization.

### Instrumentation

Taking `DualpipeV2` as an example, locate the forward and backward pass code and add the following code to `dualpipev_schedules.py` (for reference only; ensure the code is added at the correct location):

```python
import torch_npu
def step_wrapper(func, msg: str):
    def wrapper(*args, **kwargs):
        new_msg = {"name": msg}
        if msg == "forward_step_with_model_graph" and kwargs.get("extra_block_kwargs") is not None:
            new_msg["name"] = "forward_backward_overlaping"
        if "current_microbatch" in kwargs:
            new_msg["current_microbatch"] = kwargs["current_microbatch"]
        if msg == "WeightGradStore_pop" and len(WeightGradStore.cache) == 0:
            mstx_state_step_range_id = None
        else:
            mstx_state_step_range_id = torch_npu.npu.mstx.range_start(str(new_msg), torch_npu.npu.current_stream())
        out = func(*args, **kwargs)
        if mstx_state_step_range_id is not None:
            torch_npu.npu.mstx.range_end(mstx_state_step_range_id)
            mstx_state_step_range_id = None
        return out
    return wrapper

forward_step_with_model_graph = step_wrapper(forward_step_with_model_graph, "forward_step_with_model_graph")
forward_step_no_model_graph = step_wrapper(forward_step_no_model_graph, "forward_step_no_model_graph")
backward_step_with_model_graph = step_wrapper(backward_step_with_model_graph, "backward_step_with_model_graph")
backward_step = step_wrapper(backward_step, "backward_step")
WeightGradStore.pop = step_wrapper(WeightGradStore.pop, "WeightGradStore.pop")
```

Add metadata when collecting profile data:

```python
prof.add_metadata('pp_info', json.dumps(
    {
        'pp_type': 'dualpipev',
        'microbatch_num': 10,
    }
))
# Replace microbatch_num with the actual value.
```

### `StepTaskInfo`

Description:

Provides a table for visualized display. This table is generated by processing the `db` format cluster profile data instrumented in the previous section.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| name    | TEXT    | Forward and backward propagation information|
| startNs | INTEGER | Start time on the device|
| endNs   | INTEGER | End time on the device|
| type    | INTEGER | Type (different types are displayed in different colors)|

### Communication

When `profiler_level` is set to `Level_none`, the `COMMUNICATION_OP` table is not generated. Use the `mstx2commop` analysis feature to convert built-in communication instrumentation data into communication operators to generate this table. The PP chart can also display `send` and `recv` operators.

With the `COMMUNICATION_OP` table, use the `p2p_pairing` analysis feature to display `send` and `recv` connection lines in the PP chart. This allows the PP pipeline to also display the `send` and `recv` lines. However, this feature requires `level 1` or higher.

### `communication_group.json`

Records communication group information. It is generated by parsing `analysis.db`. `collective` indicates a collective communication group, and `P2P` indicates point-to-point communication. Ignore this file.

### `stats.ipynb`

- Generated when the analysis feature is set to `cann_api_sum` and stored in the `cluster_analysis_output/CannApiSum` directory.

  Open this file using Jupyter Notebook or MindStudio Insight to view cluster API duration information.

- Generated when the analysis feature is set to `compute_op_sum` and stored in the `cluster_analysis_output/ComputeOpSum` directory.

  Open this file using Jupyter Notebook or MindStudio Insight to view cluster computation operator duration analysis results (summarizing all cluster computation operators in charts) and cluster rank computation operator duration analysis results (summarizing computation operators for each rank).
  
- Generated when the analysis feature is set to `hccl_sum` and stored in the `cluster_analysis_output/HcclSum` directory.

  Open this file using Jupyter Notebook or MindStudio Insight to view cluster communication operator duration analysis results (summarizing all cluster communication operators in charts), cluster rank communication operator duration analysis results (summarizing communication operators for each rank), and top communication operator information.
  
- Generated when the analysis feature is set to `mstx_sum` and stored in the `cluster_analysis_output/MstxSum` directory.

  Open this file using Jupyter Notebook or MindStudio Insight to view MSTX instrumentation information for cluster scenarios across framework, CANN, and device sides.

- Generated when the analysis feature is set to `slow_link` and stored in the `cluster_analysis_output/SlowLink` directory.

  Open this file using Jupyter Notebook or MindStudio Insight to view abnormal slow link data analysis results for cluster scenarios (summarizing all cluster links in charts) and cluster slow link total duration analysis results (displaying data for detected potential slow links).

## `export_summary`

When `-m export_summary` is set, the following files are generated in the `ASCEND_PROFILER_OUTPUT` directory of each rank.

### `api_statistic.csv`

Description:

Provides the API statistics of each rank based on the cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| API Name | TEXT | API name|
| Count | INTEGER | Call count|
| Total Time(us) | REAL | Total duration (μs)|
| Avg Time(us) | REAL | Average duration (μs)|
| Min Time(us) | REAL | Minimum duration (μs)|
| Max Time(us) | REAL | Maximum duration (μs)|

### `kernel_details.csv`

Description:

Provides the kernel details of each rank based on the cluster profile data in `db` format.

Table fields

| Field| Type| Description|
| ------ | ---- | ---- |
| op_name | TEXT | Operator name|
| op_type | TEXT | Operator type|
| task_type | TEXT | Task type|
| task_duration | REAL | Task duration (μs)|
| input_shapes | TEXT | Input shape|
| output_shapes | TEXT | Output shape|
| block_dim | TEXT | Block dimension|
| input_data_types | TEXT | Input data type|
| output_data_types | TEXT | Output data type|
