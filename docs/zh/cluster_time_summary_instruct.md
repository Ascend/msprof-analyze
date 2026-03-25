# 集群性能数据细粒度拆解

## 简介

大集群场景涉及多个计算节点，数据量大，单卡维度的性能数据统计与分析无法评估整体集群运行情况。

原有的cluster_step_trace_time.csv交付件没有单独的执行命令，导致用户使用不便，且不能涵盖内存拷贝等指标项，需要增强。

集群性能数据细粒度拆解（cluster_time_summary）提供了集群训练过程中迭代耗时的拆解，包括计算、通信和内存拷贝等各部分的时间消耗，帮助用户找到性能瓶颈。

## 使用前准备

**环境准备**

完成msprof_analyze工具安装，具体请参见《[msprof-analyze工具安装指南](./install_guide.md)》。

**数据准备**

msprof-analyze需要传入采集的性能数据文件夹，如何采集性能数据请参见[数据准备](./README.md#使用前准备)章节。

## 集群性能数据细粒度拆解

**功能说明**

使用msprof-analyze工具的集群性能数据细粒度拆解功能，对采集到的集群数据进行分析。

**命令格式**

```bash
msprof-analyze -m cluster_time_summary -d <cluster_data> [-o <output_path>]
```

**参数说明**  

| 参数 | 可选/必选 | 说明                                                     |
| ---- | --------- | -------------------------------------------------------- |
| -m   | 必选      | 设置为cluster_time_summary，集群性能数据细粒度拆解能力。 |
| -d   | 必选      | 集群性能数据文件夹路径。                                 |
| -o   | 可选      | 指定输出文件路径，默认为-d参数指定的路径。               |

更多参数详细介绍请参见msprof-analyze的[参数说明](./README.md#参数说明)。

**使用示例**

执行集群性能数据细粒度拆解。

```bash
msprof-analyze -m cluster_time_summary -d ./xxx/cluster_data -o ./xxx/output_path
```

**输出说明**  

* 存储位置：导出类型设置为db时，在输出路径下生成cluster_analysis_output/cluster_analysis.db；导出类型设置为text时，在输出路径下生成cluster_analysis_output/ClusterTimeSummary/cluster_time_summary_{timestamp}.csv。

* 数据表名：ClusterTimeSummary

  ![输出结果展示](./figures/cluster_time_summary.png)

## 输出结果文件说明

ClusterTimeSummary表字段如下：

| 字段名称                                 | 类型    | 说明                                           |
| ---------------------------------------- | ------- | ---------------------------------------------- |
| rank                                     | INTEGER | 卡号。                                         |
| step                                     | INTEGER | 迭代编号。                                     |
| stepTime                                 | REAL    | 迭代总耗时。                                   |
| computation                              | REAL    | NPU上算子的计算总时间。                        |
| communicationNotOverlapComputation       | REAL    | 未被计算掩盖的通信耗时。                       |
| communicationOverlapComputation          | REAL    | 计算和通信重叠的时间。                         |
| communication                            | REAL    | NPU上算子的通信总时间。                        |
| free                                     | REAL    | 空闲时间，迭代总时间减去计算、通信、拷贝时间。 |
| communicationWaitStageTime               | REAL    | 通信中的总等待耗时。                           |
| communicationTransmitStageTime           | REAL    | 通信中的总传输耗时。                           |
| memory                                   | REAL    | 拷贝耗时。                                     |
| memoryNotOverlapComputationCommunication | REAL    | 未被计算、通信掩盖的拷贝耗时。                 |

上表中时间相关字段，统一使用微秒（us）。

cluster_time_summary_{timestamp}.csv除了表头格式有所调整，数据和db保持一致。

**输出结果分析：**

* 通过分析计算、通信、内存拷贝、空闲时间占比，找到性能瓶颈。
* 通过比较集群内各卡耗时指标差异，定位性能问题。例如，computing计算耗时波动显著，通常表明存在卡间不同步、计算卡性能不均的情况，而通信传输耗时差异过大时，则需优先排查参数面网络是否存在拥塞或配置异常。
* 配合使用cluster_time_compare_summary功能，可有效定位集群性能劣化根因。
