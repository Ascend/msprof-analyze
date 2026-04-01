# 通信瓶颈分析

## 简介

在分布式训练场景中，通信操作是影响整体性能的关键因素之一。当集群中存在通信慢卡时，会导致其他卡等待，从而影响整体训练效率。

通信瓶颈分析（communication_bottleneck）功能能够自动识别通信操作中的慢卡问题，并通过对比快卡和慢卡的任务执行情况，定位通信瓶颈的根本原因。该功能可以判断瓶颈是出现在Host侧还是Device侧，并进一步定位具体的操作和延迟。

## 使用前准备

**环境准备**

完成msprof_analyze工具安装，具体请参见《[msprof-analyze工具安装指南](../getting_started/install_guide.md)》。

**数据准备**

msprof-analyze需要传入采集的性能数据文件夹，如何采集性能数据请参见[数据准备](./README.md#使用前准备)章节。

## 通信瓶颈分析

**功能说明**

使用msprof-analyze工具的通信瓶颈分析功能，对采集到的集群数据进行分析。该功能会：

1. 分析指定rank的通信操作，找出耗时最长的TopN个通信操作
2. 对于每个通信操作，对比所有rank的执行时间，识别快卡和慢卡
3. 当快慢卡时间差异超过阈值时，深入分析慢卡的原因：
   - 判断是Host Bound还是Device Bound瓶颈
   - 定位导致延迟的具体操作和延迟时间

**命令格式**

```bash
msprof-analyze -m communication_bottleneck -d <cluster_data> [-o <output_path>] [--rank_id <rank_id>] [--top_num <top_num>] [--export_type <export_type>]
```

**参数说明**

| 参数 | 可选/必选 | 说明 |
| ---- | --------- | -------------------------------------------------------- |
| -m   | 必选      | 设置为communication_bottleneck，通信瓶颈分析能力。 |
| -d   | 必选      | 集群性能数据文件夹路径。 |
| -o   | 可选      | 指定输出文件路径，默认为-d参数指定的路径。 |
| --rank_id | 可选 | 指定要分析的目标rank ID，默认为0。分析该rank的通信操作，并对比所有rank的执行情况。 |
| --top_num | 可选 | 指定要分析的TopN个通信操作，默认为10。只分析耗时最长的N个通信操作。 |
| --export_type | 可选 | 指定输出文件类型，可选db或text，默认为db。              |

更多参数详细介绍请参见msprof-analyze的[参数说明](./README.md#参数说明)。

**使用示例**

1. （可选）修改配置文件。
用户可根据实际情况自行修改配置文件中的分析阈值，配置文件详细介绍请参见[配置说明](#配置说明)。

2. 执行通信瓶颈分析，分析rank 0中耗时最长的10个通信操作。

```bash
msprof-analyze -m communication_bottleneck -d ./xxx/cluster_data -o ./xxx/output_path --rank_id 0 --top_num 10
```

**输出说明**

 * 当`export_type`设置为`db`时，结果统一保存到cluster_analysis.db的CommunicationBottleneck表。
 * 当`export_type`设置为`text`时，结果保存为CSV文件：communication_bottleneck.csv。

## 配置说明

通信瓶颈分析功能支持通过配置文件自定义分析阈值。配置文件位于：

```bash
msprof_analyze/cluster_analyse/recipes/communication_bottleneck/config.json
```

配置文件格式如下：

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

配置参数说明：

| 参数 | 可选/必选 | 说明 |
| ---- | --------- | ---- |
| slow_npu_happen | 可选 | 设置快慢卡识别阈值，当快慢卡时间差异比例小于此值时，认为无慢卡问题。float类型，默认值0.05，此值为百分比。 |
| diff_waiting_time | 可选 | 等待时间差异阈值，Device侧等待时间比Host侧多于此值时，认为是Device Bound问题，约为100us。int类型，默认值100000，单位ns。 |
| start_ns_shifted | 可选 | 起始时间偏移阈值，偏移小于此值时认为对齐，约为1ms。int类型，默认值1000000，单位ns。 |
| device_bound_proportion | 可选 | 设置Device侧瓶颈阈值，当Device Bound问题占比超过此比例时，判定为Device侧瓶颈。float类型，默认值0.5，此值为百分比。 |

## 输出结果文件说明

**CommunicationBottleneck表**

表字段如下：

| 字段名称       | 说明                               |
| -------------- |----------------------------------|
| startTime(us)  | 目标卡上通信算子的开始时间戳，TEXT类型，单位为us。 |
| endTime(us)    | 目标卡上通信算子的结束时间戳，TEXT类型，单位为us。  |
| duration(us)   | 目标卡上通信算子的持续时间，REAL类型，单位为us。  |
| communicationOp| 通信算子的名称，TEXT类型。                  |
| slowRankId     | 慢卡卡号，INTEGER类型，当存在快慢卡时有效。        |
| fastRankId     | 快卡卡号，INTEGER类型，当存在快慢卡时有效。        |
| reason         | 分析结果，TEXT类型。                     |

**communication_bottleneck.csv**

CSV文件列名如下：

| 字段名称         | 说明                              |
|------------------|---------------------------------|
| Start Time(us)   | 目标卡上通信算子的开始时间戳，TEXT类型，单位为us。 |
| End Time(us)     | 目标卡上通信算子的结束时间戳，TEXT类型，单位为us。 |
| Duration(us)     | 目标卡上通信算子的持续时间，REAL类型，单位为us。 |
| Communication Op | 通信算子的名称，TEXT类型。                 |
| Slow Rank ID     | 慢卡卡号，INTEGER类型，当存在慢卡时有效。                  |
| Fast Rank ID     | 快卡卡号，INTEGER类型，当存在慢卡时有效。                  |
| Reason           | 分析结果，TEXT类型，文本描述形式。             |
