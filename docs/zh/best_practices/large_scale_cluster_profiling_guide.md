# 超大规模集群性能数据采集与分析

## 1. 问题背景

超大规模集群的全量性能数据可能达到 TB 级。长时间采集大量详细数据会增加性能开销和存储压力，跨节点传输、数据导出和可视化加载也需要更长时间，影响首次排查效率。

本文介绍在超大集群场景下，采用 Level0 精简配置采集性能数据，集中汇总后使用 msprof-analyze 生成集群结果，再通过 MindStudio Insight 查看耗时分布与通信时序。首次排查时，先定位耗时不均衡的 rank 和通信域，再对候选范围采集详细数据。

## 2. 解决方案

| 阶段 | 操作 | 说明                                                                                        |
| --- | --- |-------------------------------------------------------------------------------------------|
| 数据采集 | 使用 `torch_npu.profiler` 静态或动态采集并导出 DB | 各目标 rank 采集相同的训练迭代区间，例如连续两个 Step。采用 Level0 和精简配置控制采集开销，仅导出 DB 可减少额外 text 文件的生成、存储及后续处理负担。 |
| 数据汇总 | 收集各节点产物并保留目录层级 | 采集完成的性能数据分别保存在集群各节点本地路径上时，需要将每个节点的数据拷贝到同一目录下，方便 `maprof-analyze` 工具统一执行分析。                |
| 数据分析 | 执行 `msprof-analyze cluster -m all` | 汇总迭代耗时、通信域和通信耗时，输出到 `cluster_analysis_output`。                                            |
| 问题定位 | 使用 MindStudio Insight 加载集群结果 | 导入集群结果，查看不同卡上的耗时分布，及同一通信域内的通信算子耗时缩略图，找到慢卡的候选，确定后续深挖范围。                                    |

## 3. 操作流程

### 3.1 采集级别选择

| 分析目标 | 推荐级别 | 可用数据与边界 |
| --- | --- | --- |
| 集群概览、卡间均衡性、同一通信域的通信时序对比 | Level0 | 使用迭代耗时与通信大算子开始时间、整体耗时。本文样本的传输、等待、同步、空闲等细分耗时不可用，以 `-1` 表示。 |
| 链路、矩阵、细分通信耗时或具体计算算子深挖 | Level1 或按目标选择更高等级 | 对少量候选 rank 和异常窗口重新采集，并按目标启用所需的 shape、栈或性能指标。以对应能力矩阵及实际导出字段为准。 |

### 3.2 Level0 采集推荐配置

| 参数或能力            | 推荐设置                                                                                | 用途                                                                         |
|------------------|-------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| 采集等级             | `Level0`                                                                            | 首轮采集集群耗时概览及可用的通信整体耗时                                                       |
| 数据精简开关           | `data_simplification=True`                                                          | 导出后精简采集文件，实际保留项以当前版本产物为准                                                   |
| 数据导出格式           | `export_type=[torch_npu.profiler.ExportType.Db]`                                    | DB 格式文件占用更小的存储空间，数据解析、分析效率更高                                               |
| 采集事件             | `activities=[npu_profiler.ProfilerActivity.CPU, npu_profiler.ProfilerActivity.NPU]` | 采集框架和设备侧事件                                                                 |
| AI Core 性能指标（PM） | `aic_metrics=AiCMetrics.AiCoreNone`，`l2_cache=False`                                | 关闭性能计数器和 L2 Cache 指标采集                                                     |
| 其他配置             | `with_stack=False`，`profile_memory=False`，`record_shapes=False`                     | 关闭调用栈、内存、框架层的Shape采集，减小性能膨胀和文件大小                                           |

以上参数为`torch_npu.profiler`系列接口参数，详细介绍请参见[Ascend PyTorch调优工具](https://gitcode.com/Ascend/pytorch/blob/master/docs/zh/developer_notes/ascend_pytorch_profiler_user_guide.md)。

采集参数与版本相关，版本配套关系请参见[版本说明](https://gitcode.com/Ascend/release-management/blob/master/MindStudio/master/release_notes.md)。

### 3.3 采集方式选择

采集方式根据任务的运行状态选择。

- **静态采集**适合可提前确定采集区间的复现任务。在训练脚本中配置起始 Step 和采集长度，启动任务后按计划执行。
- **动态采集**适合持续运行的任务。在训练脚本中预先集成动态采集入口，运行期间通过修改配置触发采集。

#### 3.3.1 静态采集

将以下代码接入已完成分布式初始化的脚本，用现有的一次完整训练迭代替换 `train_one_step(batch)`。示例跳过 5 个 Step，预热 1 个 Step，采集 2 个 Step。各目标 rank 应采集相同的训练迭代区间，循环至少执行到所选采集区间结束。每个批次的输出目录应唯一，`worker_name` 使用全局 rank 区分产物。

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

#### 3.3.2 动态采集

在训练启动前集成动态采集入口。对使用以下 API 的版本，在每个目标进程初始化并在迭代边界调用 `step()`。

```python
from torch_npu.profiler import dynamic_profile as dp

dp.init("/data/profile_config")
for batch in train_dataloader:
    train_one_step(batch)
    dp.step()
```

在当前版本生成的 `profiler_config.json` 中配置下列参数。示例中 `start_step` 的默认值 `0`，此时处于待触发状态。需要开始采集时，将其修改为所有目标进程都尚未执行到的同一个 Step，并在所有节点更新配置。各目标 rank 将从指定的 Step 开始采集，`active` 控制采集的迭代数量。

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

### 3.4 数据汇总

共享存储具备足够写入能力时，可以为同一批次设置统一输出根目录。若大量 rank 同时导出会扰动训练，先写各节点本地盘，导出完成后再集中拷贝。保持各 rank 目录独立，避免同名文件覆盖或混入其他采集批次。

#### 3.4.1 全量汇总

将各节点导出完成的 `*_ascend_pt` 目录完整拷贝到同一个批次目录。

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

#### 3.4.2 最小汇总

传输受限时，每个 rank 只拷贝原位置的 `profiler_info*.json` 和 `ASCEND_PROFILER_OUTPUT/analysis.db`，保留原有层级。

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

### 3.5 数据分析

```bash
msprof-analyze cluster -m all \
  -d /path/to/cluster_data \
  -o /path/to/output
```

建议每个分析批次使用新的输出目录。运行后先确认日志中的 rank 数和输入格式，再核对结果库中的实际表与行数。

以下是 Level0 样本的关键日志节选，省略时间戳和路径：

```text
Finish allocate profiling data: 2 ranks, data type: db, profiling type: pytorch
Exporting data to database: .../cluster_analysis.db, table: CommunicationGroupMapping
Exporting data to database: .../cluster_analysis.db, table: ClusterCommunicationTime
Communication matrix data is None.
StepTraceTimeAnalysis completed
```

输出目录为 `/path/to/output/cluster_analysis_output`。该样本的核心结果如下：

| `cluster_analysis.db` 中的表 | 用途 |
| --- | --- |
| `ClusterStepTraceTime` | 记录各 rank 在不同 Step 的耗时概览，供概览页面分析 |
| `CommunicationGroupMapping` | 通信域与 rank 集合的映射 |
| `ClusterCommunicationTime` | 所有的通信算子调用记录，供通信耗时对比 |

### 3.6 可视化分析

使用 MindStudio Insight 工具进行性能数据可视化分析，详细分析方法请参见[模型调优深入分析](https://www.hiascend.com/document/detail/zh/mindstudio/latest/practicalcases/GeneralPerformanceIssue/docs/zh/best_practices/general_performance_issue_troubleshooting_guide/performance_tool_usage.md#%E6%A8%A1%E5%9E%8B%E8%B0%83%E4%BC%98%E6%B7%B1%E5%85%A5%E5%88%86%E6%9E%90mindstudio-insight)。

针对超大集群场景的分析思路如下：

1. **导入集群结果。** 选择完整的 `cluster_analysis_output` 文件夹。在概览（Summary）页按界面要求填写实际并行策略，再生成耗时分布。单独导入汇总结果适用于先查看集群概况的场景。
2. **看耗时分布。** 将每个 rank 的迭代耗时拆为计算、未被计算掩盖的通信和空闲（Free）时间。先看各部分占比，再比较相同 Step、相同并行职责的 rank。计算与通信重叠的部分已纳入耗时拆解，比较时使用未掩盖通信列。记录偏离明显的 rank、Step 和主要耗时项，作为通信页签的筛选条件。
3. **看通信域。** 切换到通信（Communication）页签的通信耗时分析，选择相关通信域和 Step，在通信耗时缩略图里对照同一轮调用的 rank、开始时间和整体耗时。
4. **找慢卡候选。** 在同一通信域中比较同一轮集合通信，使用开始时间和整体耗时核对各 rank 的进入及结束时间。如果结束时间接近而某个 rank 明显晚进入，可优先排查该 rank 的前序计算、调度或等待。早进入的 rank 反而可能因等待而具有更长的通信整体耗时。确认各 rank 的时间戳可比后，用多轮通信验证这一模式，再针对候选 rank 和相应迭代区间补采 Level1 数据。
