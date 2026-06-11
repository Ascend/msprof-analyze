# 集群分析工具

## 1 简介

`cluster_analyse` 是面向集群场景的分析工具，基础功能涵盖通信域的迭代内耗时分析、通信时间分析和通信矩阵分析，可用于定位慢卡、慢节点及慢链路问题。 生成的交付件推荐在 `MindStudio Insight` 中可视化查看，典型应用场景有：

- **判断是否存在慢卡或负载不均衡**：对比各 rank 或 stage 的计算时间、通信时间、空闲时间。如果同类时间差异超过 5%，可进一步排查慢卡或通信瓶颈。
- **判断是否存在慢链路或带宽异常**：查看 rank 间的链路类型（LOCAL/HCCS/PCIE/RDMA）和传输带宽。同一类链路间的带宽应基本持平，差异明显时可定位到具体慢链路。
- **定位耗时集中的通信算子或通信域**：查看通信算子的耗时分布和通信域内的 rank 范围，快速锁定异常通信操作。

## 2 数据要求

### 2.1 性能数据采集

当前集群分析能力支持以下 4 类 profiling 数据作为输入：

| 采集工具 | 支持的结果类型 | 采集指南                                                                                                                                          |
| --- | --- |-----------------------------------------------------------------------------------------------------------------------------------------------|
| msProf | db | 《[模型调优工具](https://gitcode.com/Ascend/msprof/blob/master/docs/zh/getting_started/quick_start.md)》                                                                                                 |
| Ascend PyTorch Profiler | text、db | 《[Ascend PyTorch调优工具](https://gitcode.com/Ascend/pytorch/blob/v2.7.1/docs/zh/ascend_pytorch_profiler/ascend_pytorch_profiler_user_guide.md)》 |
| MindSpore Profiler | text、db | 《[MindSpore调优工具](https://gitcode.com/Ascend/docs/blob/master/MindStudio/master/mindspore_profiler_user_guide.md)》 |
| msMonitor | db | 《[msMonitor](https://gitcode.com/Ascend/msmonitor)》                                                                              |

下面以 Ascend PyTorch Profiler 为例说明输入数据要求。

### 2.2 采集配置

`profiler_level` 建议设置为 `Level1` 或更高。`Level0` 及以下不会采集通信小算子，因此无法获取通信带宽和通信矩阵信息，仅能汇总集群的`step_trace_time`迭代内耗时信息。

```python
experimental_config = torch_npu.profiler._ExperimentalConfig(
    profiler_level=torch_npu.profiler.ProfilerLevel.Level1
)
```

### 2.3 数据格式

Ascend PyTorch Profiler 支持以下两种结果格式，二者满足其一即可。建议优先使用 db 格式性能数据，处理效率更高。

#### 2.3.1 db 格式性能数据

打开某张卡采集到的 *_ascend_pt 目录，正常可用的 db 类型性能数据通常应包含以下目录和文件：

```text
*_ascend_pt
├── ASCEND_PROFILER_OUTPUT
    ├── analysis.db # 通信细节信息，包含传输量、传输链路、通信矩阵等
    └── ascend_pytorch_profiler_{rank_id}.db
└── profiler_info_*.json
```

> [!NOTE]
>
> 对于超大集群性能数据需要汇总分析的场景，由于数据量较大，转存的代价高，支持单独保存 `analysis.db` 和 `profiler_info_*.json` 文件（须保留原有目录结构）进行 `msprof-analyze cluster` 分析，以此节省文件转储耗时，完成基本的性能分析。

#### 2.3.2 text 格式性能数据

已有 text 类型结果时，也可以直接作为输入。打开某张卡采集到的 *_ascend_pt 目录，可用的 text 类型结果必须包含以下目录和文件：

```text
*_ascend_pt # 单卡性能数据文件
├── ASCEND_PROFILER_OUTPUT
    ├── step_trace_time.csv  # 迭代耗时
    ├── communication.json  # 通信耗时
    └── communication_matrix.json # 通信矩阵信息
└── profiler_info_*.json
```

### 2.4 集群输入目录要求

集群分析时，`-d` 参数应指向集群性能数据根目录，根目录下需包含多张卡、同一次采集得到的 profiling 子目录。为保证分析结果准确，集群路径需满足：

* 只包含同一次采集的全量卡数据，避免混入不同批次或缺失部分 rank；
* 各卡目录层级和命名保持完整，便于工具正确识别 rank 关系。

若混入不同批次数据或缺失部分 rank，通信矩阵的 `src_rank`、`dst_rank` 映射可能不准确，并伴有 warning 输出。

推荐的输入目录示例如下：

```text
profiling_data/
├── dp0_pp0_tp0_dcp0_ep0_rank0_167032_20260527143703527_ascend_pt/
│   ├── ASCEND_PROFILER_OUTPUT
│   └── profiler_info_*.json
├── dp0_pp0_tp1_dcp0_ep1_rank1_167033_20260527143703524_ascend_pt/
│   ├── ASCEND_PROFILER_OUTPUT
│   └── profiler_info_*.json
├── dp0_pp0_tp2_dcp0_ep2_rank2_167034_20260527143703524_ascend_pt/
│   ├── ASCEND_PROFILER_OUTPUT
│   └── profiler_info_*.json
└── dp0_pp0_tp3_dcp0_ep3_rank3_167035_20260527143703524_ascend_pt/
    ├── ASCEND_PROFILER_OUTPUT
    └── profiler_info_*.json
```

## 3 运行集群分析

### 3.1 安装工具

参见《[安装指南](../getting_started/install_guide.md)》完成工具安装。建议安装最新版本。

### 3.2 执行集群分析

将所有卡的数据拷贝并汇集到一个目录下，运行以下命令，生成 `cluster_analysis_output` 文件夹。

```bash
# 命令行运行方式（推荐）
msprof-analyze cluster -d {cluster profiling data path} [-m mode] [-o output_path] [--force]
# 示例
msprof-analyze cluster -m all -d ./cluster_data -o ./output
```

或

```bash
# 脚本运行方式
python3 cluster_analysis.py -d {cluster profiling data path} [-m mode] [-o output_path] [--force]
# 示例
python3 cluster_analysis.py -m all -d ./cluster_data -o ./output
```

### 3.3 参数说明

| 参数名               | 可选/必选 | 说明                                                         |
| -------------------- | --------- | ------------------------------------------------------------ |
| --profiling_path或-d | 必选      | 性能数据汇集目录。未配置-o参数时，运行分析脚本之后会在该目录下自动创建cluster_analysis_output文件夹，保存分析数据。 |
| --output_path或-o    | 可选      | 自定义输出路径，运行分析脚本之后会在该目录下自动创建cluster_analysis_output文件夹，保存分析数据。 |
| --mode或-m           | 可选      | 数据解析模式，取值详见“**--mode参数说明**”表。               |
| --agent              | 可选      | 分析结果以json格式输出至标准输出，配置该参数表示开启，默认未配置表示关闭。 |
| --force              | 可选      | 强制执行 cluster。配置后可强制跳过如下情况：<br>&#8226; 指定的目录、文件的用户属主不属于当前用户，忽略属主判断直接执行。<br>&#8226; csv 文件大于 5G、json 文件大于 10G、db 文件大于 8G，忽略文件过大判断直接执行。<br>&#8226; 指定目录、文件的读写权限不满足校验要求，忽略权限判断直接执行。<br>配置该参数表示开启强制执行，默认未配置表示关闭。 |

--mode 参数说明：

| 参数名               | 可选/必选 | 说明                                                         |
| -------------------- | --------- | ------------------------------------------------------------ |
| communication_matrix | 可选      | 解析通信矩阵数据。                                           |
| communication_time   | 可选      | 解析通信耗时数据。                                           |
| all                  | 可选      | 同时解析通信矩阵communication_matrix和通信耗时数据communication_time，--mode参数默认值为all。 |

### 3.4 可视化查看

推荐使用 MindStudio Insight 工具导入生成的 `cluster_analysis_output` 文件夹进行可视化展示，如下图所示。具体使用方法请参见《[MindStudio Insight用户指南](https://gitcode.com/Ascend/msinsight/blob/master/docs/zh/user_guide/overview.md)》。

![img](../figures/cluster_summary.png)
    <div style="text-align: center;">
    图1 集群计算/通信概览可视化呈现
    </div>

![img](../figures/cluster_communication_matrix.png)
    <div style="text-align: center;">
    图2 集群通信矩阵可视化呈现
    </div>    

## 4 交付件

### 4.1 推荐查看方式

推荐查看路径如下：

1. 分析完成后，强烈建议将整个 `cluster_analysis_output` 文件夹导入 MindStudio Insight。
2. 在集群概览页查看 rank/stage 维度的计算、通信、空闲和 Bubble 耗时，优先判断是否存在慢卡或 stage 间负载不均衡。
3. 在通信矩阵页查看 rank 间链路类型、通信大小、带宽和传输时间，判断是否存在慢链路或异常带宽。
4. 需要进一步定位通信算子或通信域时，在可视化页面中查看通信耗时明细和通信域信息。

### 4.2 交付件介绍

| 交付件 | 输入格式 | 主要用途 / 说明                                        |
| :--- | :--- |:-------------------------------------------------|
| `cluster_analysis.db` | db | 包含导入 MindStudio Insight 进行可视化分析，适合大规模集群数据。       |
| `cluster_step_trace_time.csv` | text | 集群迭代耗时拆解信息，包括 rank/stage 维度耗时，用于辅助判断慢卡、负载不均衡等问题。 |
| `cluster_communication.json` | text | 集群通信算子耗时明细。                                      |
| `cluster_communication_matrix.json` | text | 集群通信矩阵，包括 rank 间链路类型、带宽和传输时间。                    |
| `communication_group.json` | text | 集群集合通信和点对点通信域信息。                                 |

### 4.3 交付件字段说明

#### 4.3.1 cluster_step_trace_time.csv

数据解析模式为 `communication_matrix`、`communication_time` 或 `all` 时均可生成。

|  字段  | 说明 |
|------| --- |
| Step | 采集性能数据时设置的 Step 数。集群性能数据通常采集一个 step 即可；如果采集多个 step，需要先筛选目标 step。 |
| Type | 数据类型，主要包括 `rank` 和 `stage`。`rank` 表示单卡 rank；`stage` 表示 PP 并行场景中的 rank group。 |
| Index | 与 Type 相关的索引，Type 为 `rank` 时表示卡号，Type 为 `stage` 时表示 stage 编号。 |
| Computing | 计算时间。 |
| Communication(Not Overlapped) | 未被计算掩盖的通信耗时。 |
| Overlapped | 计算与通信重叠的耗时。 |
| Communication | 通信时间的全部耗时。 |
| Free | Device 侧既不在通信也不在计算的空闲时间，可能来自 SDMA 拷贝、host bound 或等待。 |
| Stage | PP 并行时有效，表示除 receive 算子时间外的 stage 时间。 |
| Bubble | Receive 时间总和。 |
| Communication(Not Overlapped and Exclude Receive) | 剔除 receive 算子后，未被计算掩盖的通信时间。 |
| Preparing | 迭代开始到首个计算或通信算子运行前的准备时间。 |
| DP Index | 数据按照并行策略切分后所属 DP 组的索引，未采集则不显示。 |
| PP Index | 数据按照并行策略切分后所属 PP 组的索引，未采集则不显示。 |
| TP Index | 数据按照并行策略切分后所属 TP 组的索引，未采集则不显示。 |

排查时可先筛选 Type 为 `stage`，判断 stage 间是否存在明显耗时差异；再筛选 Type 为 `rank`，判断单卡 rank 是否异常。理论上同类时间应基本持平，最大值和最小值差异超过 5% 时，可重点排查慢卡、负载不均衡、host bound 或通信耗时占比过高。

#### 4.3.2 cluster_communication_matrix.json

数据解析模式为 `communication_matrix` 或 `all` 时可生成。该文件记录 rank 间通信矩阵信息，建议优先在 MindStudio Insight 通信矩阵页查看；脚本化处理时可关注如下结构：

```json
{
    "{src_rank}-{dst_rank}": {
        "Transport Type": "LOCAL",
        "Transit Time(ms)": 0.02462,
        "Transit Size(MB)": 16.777216,
        "Bandwidth(GB/s)": 681.4466
    }
}
```

| 字段 | 说明 |
| --- | --- |
| `{src_rank}-{dst_rank}` | 通信链路两端的 rank 编号。 |
| `Transport Type` | 链路类型。`LOCAL` 表示片内拷贝，`HCCS` 或 `PCIE` 表示节点内片间拷贝，`RDMA` 表示节点间拷贝。 |
| `Transit Time(ms)` | 该链路传输耗时。 |
| `Transit Size(MB)` | 该链路传输数据量。 |
| `Bandwidth(GB/s)` | 该链路带宽。 |

同一类链路之间的带宽通常应接近。如果某个 `{src_rank}-{dst_rank}` 的 `Bandwidth(GB/s)` 明显低于同类链路，可结合链路类型、传输数据量和传输耗时判断是否存在慢链路。

#### 4.3.3 cluster_communication.json

数据解析模式为 `communication_time` 或 `all` 时可生成。该文件记录通信耗时明细，可用于脚本化提取通信算子耗时、通信域和 rank 范围。若 `cluster_step_trace_time.csv` 中通信耗时占比较高，可结合该文件进一步定位耗时集中的通信算子或通信域。

#### 4.3.4 communication_group.json

该文件记录通信域信息。`collective` 表示集合通信域，`P2P` 表示点对点通信域。需要确认通信域包含哪些 rank，或需要理解通信算子和通信域的对应关系时，可结合 `cluster_communication.json` 使用。

#### 4.3.5 cluster_analysis.db 

db 格式性能数据解析后生成的集群分析数据库，用于支撑 MindStudio Insight 可视化展示，也可用于后续数据库分析。集群分析生成表如下：

| 表名 | 生成场景 | 用途 |
| --- | --- | --- |
| `ClusterBaseInfo` | db 格式性能数据 | 记录集群基础信息，例如并行策略参数。 |
| `ClusterStepTraceTime` | db 格式性能数据 | 记录 rank/stage 维度的迭代耗时拆解信息，对应 `cluster_step_trace_time.csv`。 |
| `CommunicationGroupMapping` | db 格式性能数据，且存在通信域信息 | 记录通信域、rank 集合和并行组信息。 |
| `ClusterCommunicationTime` | db 格式性能数据，且执行 `communication_time` 或 `all` | 记录集群维度通信算子耗时汇总信息。 |
| `ClusterCommunicationBandwidth` | db 格式性能数据，且执行 `communication_time` 或 `all` | 记录集群维度通信带宽、包大小分布和传输耗时汇总信息。 |
| `ClusterCommunicationMatrix` | db 格式性能数据，且执行 `communication_matrix` 或 `all` | 记录集群维度 rank 间通信矩阵信息。 |

不同采集工具、采集级别、`--mode` 取值和原始 profiling 数据完整度会影响实际生成的表。若某类原始数据缺失，对应表可能不会生成。

#### 4.3.6 `ClusterBaseInfo` 字段说明

| 字段 | 说明 |
| --- | --- |
| `key` | 基础信息名称，例如分布式参数。 |
| `value` | 基础信息内容，通常为序列化后的字符串。 |

#### 4.3.7 `ClusterStepTraceTime` 字段说明

| 字段 | 说明 |
| --- | --- |
| `step` | Step 编号。 |
| `type` | 数据类型，主要包括 `rank` 和 `stage`。 |
| `index` | rank 编号或 stage 编号。 |
| `computing` | 计算时间，单位 ms。 |
| `communication_not_overlapped` | 未被计算掩盖的通信耗时，单位 ms。 |
| `overlapped` | 计算与通信重叠的耗时，单位 ms。 |
| `communication` | 通信总耗时，单位 ms。 |
| `free` | Device 侧空闲时间，单位 ms。 |
| `stage` | PP 并行场景下的 stage 时间，单位 ms。 |
| `bubble` | Receive 时间总和，单位 ms。 |
| `communication_not_overlapped_and_exclude_receive` | 剔除 receive 算子后，未被计算掩盖的通信时间，单位 ms。 |
| `preparing` | 迭代开始到首个计算或通信算子运行前的准备时间，单位 ms。 |
| `dp_index` | 所属 DP 组索引，未采集则为空或默认值。 |
| `pp_index` | 所属 PP 组索引，未采集则为空或默认值。 |
| `tp_index` | 所属 TP 组索引，未采集则为空或默认值。 |

#### 4.3.8 `CommunicationGroupMapping` 字段说明

| 字段 | 说明 |
| --- | --- |
| `type` | 通信域类型，例如集合通信或点对点通信。 |
| `rank_set` | 通信域包含的 rank 集合。 |
| `group_name` | 通信域名称。 |
| `group_id` | 通信域 ID。 |
| `pg_name` | 并行组名称。 |

#### 4.3.9 `ClusterCommunicationTime` 字段说明

| 字段 | 说明 |
| --- | --- |
| `step` | Step 编号。 |
| `type` | 通信算子类型，包含集合通信和点对点通信等类型。 |
| `hccl_op_name` | HCCL 通信算子名称。 |
| `group_name` | 通信域名称。 |
| `start_timestamp` | 通信算子开始时间戳，单位 us。 |
| `elapsed_time` | 通信算子总耗时，单位 ms。 |
| `transit_time` | 数据传输耗时，单位 ms。 |
| `wait_time` | 等待耗时，单位 ms。 |
| `synchronization_time` | 同步耗时，单位 ms。 |
| `idle_time` | 空闲耗时，单位 ms。 |
| `synchronization_time_ratio` | 同步耗时占比，取值为 0 到 1 的小数。 |
| `wait_time_ratio` | 等待耗时占比，取值为 0 到 1 的小数。 |

#### 4.3.10 `ClusterCommunicationBandwidth` 字段说明

| 字段 | 说明 |
| --- | --- |
| `step` | Step 编号。 |
| `type` | 通信算子类型，包含集合通信和点对点通信等类型。 |
| `hccl_op_name` | HCCL 通信算子名称。 |
| `group_name` | 通信域名称。 |
| `band_type` | 通信链路类型。 |
| `transit_size` | 传输数据量，单位 MB。 |
| `transit_time` | 传输耗时，单位 ms。 |
| `bandwidth` | 带宽，单位 GB/s。 |
| `large_packet_ratio` | 大包占比，取值为 0 到 1 的小数。 |
| `package_size` | 包大小，单位 MB。 |
| `count` | 对应包大小的通信次数。 |
| `total_duration` | 对应包大小的总耗时，单位 ms。 |

#### 4.3.11 `ClusterCommunicationMatrix` 字段说明

| 字段 | 说明 |
| --- | --- |
| `step` | Step 编号。 |
| `type` | 通信算子类型，包含集合通信和点对点通信等类型。 |
| `hccl_op_name` | HCCL 通信算子名称。 |
| `group_name` | 通信域名称。 |
| `src_rank` | 源 rank。 |
| `dst_rank` | 目的 rank。 |
| `transit_size` | 传输数据量，单位 MB。 |
| `transit_time` | 传输耗时，单位 ms。 |
| `bandwidth` | 链路带宽，单位 GB/s。 |
| `transport_type` | 链路类型。 |
| `op_name` | 通信算子或链路对应的操作名称。 |
