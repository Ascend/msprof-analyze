# Profiling Data Collection and Analysis for Large-Scale Clusters

## 1. Background

Full profile data for a large-scale cluster can reach the TB level. Collecting large amounts of detailed data for an extended period increases performance overhead and storage pressure. Cross-node transfer, data export, and visualization loading also take longer, reducing the efficiency of the initial investigation.

This document describes how to use the streamlined Level0 configuration to collect profile data in a large-cluster scenario, aggregate the data, use msprof-analyze to generate cluster results, and then use MindStudio Insight to view duration distribution and communication timelines. During the initial investigation, identify ranks and communication domains with imbalanced durations, and then collect detailed data only for the candidate scope.

## 2. Solution

| Phase | Action | Description |
| --- | --- | --- |
| Data collection | Use `torch_npu.profiler` to collect data statically or dynamically and export DB files. | Collect the same training iteration range on each target rank, for example, two consecutive steps. Use Level0 and a streamlined configuration to control collection overhead. Exporting only DB files reduces the burden of generating, storing, and subsequently processing additional text files. |
| Data aggregation | Collect artifacts from each node and preserve the directory hierarchy. | When collected profile data is stored in local paths on different cluster nodes, copy each node's data to the same directory so that `msprof-analyze` can perform unified analysis on all data. |
| Data analysis | Run `msprof-analyze cluster -m all`. | Aggregate iteration durations, communication domains, and communication durations, and write the results to `cluster_analysis_output`. |
| Problem localization | Load the cluster results in MindStudio Insight. | Import the cluster results to view the duration distribution across ranks and the communication operator duration thumbnail within each communication domain. Identify slow-rank candidates and determine the scope for detailed investigation. |

## 3. Procedure

### 3.1 Selecting a Collection Level

| Analysis Objective | Recommended Level | Available Data and Boundaries |
| --- | --- | --- |
| Cluster overview, inter-rank balance, and communication timeline comparison within the same communication domain | Level0 | Use iteration duration, start time of major communication operators, and total duration. In the sample used by this document, detailed durations such as transfer, wait, synchronization, and idle time are unavailable and are displayed as `-1`. |
| Detailed analysis of links, matrices, communication breakdowns, or specific compute operators | Level1 or a higher level selected for the objective | Re-collect data for a small number of candidate ranks and abnormal windows, and enable the shapes, stacks, or performance metrics required for the objective. Use the corresponding capability matrix and actual exported fields as the authority. |

### 3.2 Recommended Level0 Configuration

| Parameter or Capability | Recommended Setting | Purpose |
|------------------|-------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| Collection level | `Level0` | Collect a cluster duration overview and available total communication durations in the first round. |
| Data simplification | `data_simplification=True` | Simplify collected files during export. The items retained depend on the current version's artifacts. |
| Data export format | `export_type=[torch_npu.profiler.ExportType.Db]` | DB files occupy less storage space and improve data parsing and analysis efficiency. |
| Collected activities | `activities=[npu_profiler.ProfilerActivity.CPU, npu_profiler.ProfilerActivity.NPU]` | Collect framework-side and device-side events. |
| AI Core performance metrics (PM) | `aic_metrics=AiCMetrics.AiCoreNone`, `l2_cache=False` | Disable performance counters and L2 Cache metric collection. |
| Other settings | `with_stack=False`, `profile_memory=False`, `record_shapes=False` | Disable stack, memory, and framework-level shape collection to reduce performance overhead and file size. |

The preceding parameters belong to the `torch_npu.profiler` API series. For details, see [Ascend PyTorch Tuning Tools](https://gitcode.com/Ascend/pytorch/blob/master/docs/en/developer_notes/ascend_pytorch_profiler_user_guide.md).

Collection parameters depend on the software version. For version compatibility, see [Release Notes](https://gitcode.com/Ascend/release-management/blob/master/MindStudio/master/release_notes_en.md).

### 3.3 Selecting a Collection Method

Select the collection method based on the task's running state.

- **Static collection** is suitable for reproducible tasks whose collection range can be determined in advance. Configure the start step and collection length in the training script, and then start the task to collect data as scheduled.
- **Dynamic collection** is suitable for continuously running tasks. Integrate the dynamic collection entry point into the training script in advance, and trigger collection by changing the configuration while the task is running.

#### 3.3.1 Static Collection

Integrate the following code into a script that has completed distributed initialization, and replace `train_one_step(batch)` with an existing complete training iteration. The example skips five steps, performs one warmup step, and collects two steps. Each target rank must collect the same training iteration range, and the loop must run at least until the selected collection range ends. The output directory for each batch must be unique. Use the global rank in `worker_name` to distinguish artifacts.

```python
import os

import torch.distributed as dist
import torch_npu
import torch_npu.profiler as npu_profiler

rank = dist.get_rank()
output_dir = os.environ["PROFILE_OUTPUT_DIR"]

config = npu_profiler._ExperimentalConfig(
    profiler_level=npu_profiler.ProfilerLevel.Level0,
    data_simplification=True,
    export_type=[npu_profiler.ExportType.Db],
    aic_metrics=npu_profiler.AiCMetrics.AiCoreNone,
    l2_cache=False,
)

with npu_profiler.profile(
    activities=[npu_profiler.ProfilerActivity.CPU, npu_profiler.ProfilerActivity.NPU],
    schedule=npu_profiler.schedule(skip_first=5, wait=0, warmup=1, active=2, repeat=1),
    on_trace_ready=npu_profiler.tensorboard_trace_handler(output_dir, worker_name=f"rank_{rank}"),
    record_shapes=False,
    profile_memory=False,
    with_stack=False,
    experimental_config=config,
) as prof:
    for batch in train_dataloader:
        train_one_step(batch)
        prof.step()
```

#### 3.3.2 Dynamic Collection

Integrate the dynamic collection entry point before starting training. For versions that support the following API, initialize it in each target process and call `step()` at iteration boundaries.

```python
from torch_npu.profiler import dynamic_profile as dp

dp.init("/data/profile_config")
for batch in train_dataloader:
    train_one_step(batch)
    dp.step()
```

Configure the following parameters in the `profiler_config.json` file generated by the current version. In the example, the default value of `start_step` is `0`, which means collection is waiting to be triggered. To start collection, set it to the same step that none of the target processes has reached, and update the configuration on all nodes. Each target rank starts collection at the specified step, and `active` controls the number of iterations to collect.

```json
{
  "activities": ["CPU", "NPU"],
  "prof_dir": "/data/profiles/run_001",
  "analyse": true,
  "record_shapes": false,
  "profile_memory": false,
  "with_stack": false,
  "warmup": 1,
  "active": 2,
  "start_step": 0,
  "is_rank": false,
  "rank_list": [],
  "experimental_config": {
    "profiler_level": "Level0",
    "data_simplification": true,
    "export_type": ["db"],
    "aic_metrics": "AiCoreNone",
    "l2_cache": false
  }
}
```

### 3.4 Data Aggregation

If the shared storage has sufficient write capability, configure a shared output root directory for the same batch. If exporting from a large number of ranks at the same time disturbs training, first write data to each node's local disk and copy the exported data to a central location afterward. Keep the directory for each rank separate to prevent files with the same name from overwriting each other or mixing data from other collection batches.

#### 3.4.1 Full Aggregation

Copy the complete `*_ascend_pt` directory exported from each node to the same batch directory.

```text
/path/to/cluster_data
├── rank_0_<timestamp>_ascend_pt/
│   ├── profiler_info_0.json
│   ├── profiler_metadata.json
│   └── ASCEND_PROFILER_OUTPUT/
│       ├── analysis.db
│       └── ascend_pytorch_profiler_0.db
└── rank_1_<timestamp>_ascend_pt/
    ├── profiler_info_1.json
    ├── profiler_metadata.json
    └── ASCEND_PROFILER_OUTPUT/
        ├── analysis.db
        └── ascend_pytorch_profiler_1.db
```

#### 3.4.2 Minimal Aggregation

When transfer capacity is limited, copy only `profiler_info*.json` and `ASCEND_PROFILER_OUTPUT/analysis.db` from each rank's original location, and preserve the original hierarchy.

```text
/path/to/cluster_data
├── rank_0_<timestamp>_ascend_pt/
│   ├── profiler_info_0.json
│   └── ASCEND_PROFILER_OUTPUT/
│       └── analysis.db
└── rank_1_<timestamp>_ascend_pt/
    ├── profiler_info_1.json
    └── ASCEND_PROFILER_OUTPUT/
        └── analysis.db
```

### 3.5 Data Analysis

```bash
msprof-analyze cluster -m all \
  -d /path/to/cluster_data \
  -o /path/to/output
```

Use a new output directory for each analysis batch. After the command runs, first check the number of ranks and the input format in the log, and then verify the actual tables and row counts in the result database.

The following is an excerpt from the key log of the Level0 sample, with timestamps and paths omitted:

```text
Finish allocate profiling data: 2 ranks, data type: db, profiling type: pytorch
Exporting data to database: .../cluster_analysis.db, table: CommunicationGroupMapping
Exporting data to database: .../cluster_analysis.db, table: ClusterCommunicationTime
Communication matrix data is None.
StepTraceTimeAnalysis completed
```

The output directory is `/path/to/output/cluster_analysis_output`. The core results for the sample are as follows.

| Table in `cluster_analysis.db` | Purpose |
| --- | --- |
| `ClusterStepTraceTime` | Records a duration overview for each rank at different steps and supports analysis on the summary page. |
| `CommunicationGroupMapping` | Maps communication domains to rank sets. |
| `ClusterCommunicationTime` | Contains all communication operator invocation records and supports communication duration comparison. |

### 3.6 Visualization Analysis

Use MindStudio Insight to visualize and analyze profile data. For detailed analysis methods, see [In-Depth Model Tuning Analysis](https://www.hiascend.com/document/detail/en/mindstudio/latest/practicalcases/GeneralPerformanceIssue/docs/en/best_practices/general_performance_issue_troubleshooting_guide/performance_tool_usage.md#in-depth-model-tuning-analysis-mindstudio-insight).

The analysis approach for large clusters is as follows:

1. **Import the cluster results.** Select the complete `cluster_analysis_output` folder. On the Summary page, enter the actual parallel strategy as required by the interface, and then generate the duration distribution. Importing only the aggregated results is suitable for scenarios in which you first need a cluster overview.
2. **View the duration distribution.** Break down each rank's iteration duration into computation, communication not hidden by computation, and idle (Free) time. First examine the proportion of each part, and then compare ranks with the same step and parallel roles. Overlap between computation and communication is already included in the duration breakdown, so use the communication not hidden by computation column for comparisons. Record ranks, steps, and main duration components that deviate significantly, and use them as filters on the Communication tab.
3. **View communication domains.** Switch to the communication duration analysis on the Communication tab, select the relevant communication domain and step, and compare the ranks, start time, and total duration in the same invocation round in the communication duration overview.
4. **Identify slow-rank candidates.** Compare collective communication operations in the same round within the same communication domain, and check each rank's entry and completion times by using the start time and total duration. If completion times are similar but one rank enters significantly later, prioritize investigation of that rank's preceding computation, dispatch, or waiting. Ranks that enter earlier may instead have a longer total communication duration because they wait. After confirming that timestamps are comparable across ranks, verify the pattern over multiple communication rounds, and then collect Level1 data for candidate ranks and the corresponding iteration ranges.
