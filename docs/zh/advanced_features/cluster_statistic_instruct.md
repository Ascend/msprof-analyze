# 超大集群通信统计

## 1. 简介

`cluster_statistic` 适用于超大集群的通信分析。它将通信明细汇总为通信耗时、传输指标和跨 rank 的算子耗时统计，便于比较各 rank 的通信表现和定位慢卡。

## 2. 数据准备

将各 rank 的 PyTorch DB 格式性能数据汇集到同一目录，保留原有目录结构和可识别 rank ID 的文件。需要包含通信分析数据库 `analysis.db`。数据目录结构参见[集群分析使用指南](../user_guide/cluster_analyse_instruct.md)。

## 3. 使用方法

```bash
msprof-analyze cluster -m cluster_statistic -d ./cluster_data -o ./statistic_output
```

默认统计所有可识别的 rank。可添加 `--rank_list 0,2` 指定通信统计的 rank，或添加 `--agent` 获取 JSON 格式的执行结果。迭代耗时和 Host 信息沿用集群分析的范围，读取所有可识别的 rank。

## 4. 输出说明

上述命令将结果写入 `./statistic_output/cluster_analysis_output/cluster_analysis.db`。省略 `-o` 时，`cluster_analysis_output` 位于 `-d` 指定的目录下。根据可用数据生成下列表，重跑时替换本次写入的同名表。

| 表名 | 用途 |
| --- | --- |
| `CommTimeStatistic` | 按 step、rank 和通信域汇总通信总耗时、传输、等待、同步和空闲耗时。 |
| `TransitStatistic` | 按 step、rank、通信域和传输类型汇总传输量、耗时、带宽和包大小分布。 |
| `CommOpStatistic` | 按 step、通信域和完整算子名汇总跨 rank 的总耗时、最小和最大耗时及对应 rank、有效 rank 数。 |
| `CommunicationGroupMapping` | 记录通信域、通信类型、rank 集合和并行组信息。可通过 `group_name` 与统计表关联。 |
| `ClusterBaseInfo` | 在集群配置可用时记录并行策略等基础信息。 |
| `ClusterStepTraceTime` | 记录 rank 或 stage 的迭代耗时拆解。 |
| `HostInfo` | 记录主机标识和主机名。 |
| `RankDeviceMap` | 记录 rank 与设备、主机及采集目录的对应关系。 |

源表缺少 `step` 列时使用字符串 `step` 作为默认值。不可用的统计指标以 `NULL` 表示。

## 5. 统计表字段

### 5.1 `CommTimeStatistic`

| 字段 | 说明 |
| --- | --- |
| `step` | step 标识。 |
| `rank_id` | 全局 rank ID。 |
| `group_name` | 通信域标识。 |
| `comm_total_time` | 通信算子总耗时之和，单位为 ms。 |
| `comm_transit_time` | 通信算子传输耗时之和，单位为 ms。 |
| `comm_wait_time` | 通信算子等待耗时之和，单位为 ms。 |
| `comm_sync_time` | 通信算子同步耗时之和，单位为 ms。 |
| `comm_free_time` | 通信算子内部空闲耗时之和，单位为 ms。 |

### 5.2 `TransitStatistic`

| 字段 | 说明 |
| --- | --- |
| `step` | step 标识。 |
| `rank_id` | 全局 rank ID。 |
| `group_name` | 通信域标识。 |
| `band_type` | 传输类型，例如 `RDMA`。 |
| `transit_size` | 汇总传输数据量，单位为 MB。 |
| `transit_time` | 汇总传输耗时，单位为 ms。 |
| `bandwidth` | 汇总带宽，单位为 GB/s。传输耗时大于 0 时，取 `transit_size / transit_time`。 |
| `package_distribution` | 按包大小升序排列的 JSON 数组。每项包含 `package_size`（包大小，单位为 MB）和 `count`（该包大小对应的传输次数）。 |

### 5.3 `CommOpStatistic`

| 字段 | 说明 |
| --- | --- |
| `step` | step 标识。 |
| `group_name` | 通信域标识。 |
| `op_name` | 完整通信算子名，保留原有后缀。 |
| `total_time` | 该算子在各 rank 上的有效耗时之和，单位为 ms。 |
| `min_time` | 该算子在各 rank 上的最小有效耗时，单位为 ms。 |
| `min_time_rank` | 最小耗时对应的全局 rank ID。 |
| `max_time` | 该算子在各 rank 上的最大有效耗时，单位为 ms。 |
| `max_time_rank` | 最大耗时对应的全局 rank ID。 |
| `rank_count` | 该算子具有有效耗时的 rank 数。 |

最小或最大耗时有多个 rank 并列时，记录其中最小的 rank ID。
