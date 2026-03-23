# 集群算子掩盖线性度分析

## 简介

大集群场景设计到多个计算节点，数据量大，单卡维度的性能数据统计与分析无法评估整体集群算子运行情况的掩盖程度。
集群不同并行场景下算子掩盖细粒度拆解（computational_op_masking）提供了集群训练过程中不同算子耗时的掩盖计算，
包括计算、通信各部分，帮助用户找到性能瓶颈。

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
msprof-analyze -m computational_op_masking [--export_type <export_type>] [--step_id <step_id>] [--parallel_types <parallel_types>] -d <cluster_data> [-o <output_path>]
```

**参数说明**  

| 参数                | 可选/必选 | 说明                                                                                   |
|-------------------|-------|--------------------------------------------------------------------------------------|
| -m                | 必选    | 设置为computational_op_masking，集群性能数据细粒度拆解能力。                                               |
| --export_type     | 可选    | 设置为导出文件格式为db，默认格式是db，仅支持db格式数据保存。                                                    |
| --step_id         | 可选    | 设置step取该step结果进行保存，不设置默认输出所有step的结果。                                                 |
| --parallel_types  | 可选    | 设置计算不同并行模式下，通信算子被计算算子掩盖的程度。例如："edp,dp;dp;edp" 实际含义：[('edp','dp'), ('dp',), ('edp',)] |
| -d                | 必选    | 集群性能数据文件夹路径。                                                                         |
| -o   | 可选      | 指定输出文件路径，默认为-d参数指定的路径。               |

更多参数详细介绍请参见msprof-analyze的[参数说明](./README.md#参数说明)。

**使用示例**

执行集群性能数据细粒度拆解。

```bash
msprof-analyze -m computational_op_masking --export_type db --step_id 11 --parallel_types "edp,dp;dp;edp" -d ./xxx/cluster_data -o ./xxx/output_path
```

**输出说明**  

* 存储位置：输出路径下的cluster_analysis_output/cluster_analysis.db  

* 数据表名：ComputationalOperatorMaskingLinearity

## 输出结果文件说明

ComputationalOperatorMaskingLinearity表字段如下：

| 字段名称                              | 类型    | 说明                                                     |
| ------------------------------------- | ------- | -------------------------------------------------------- |
| stepId                                | INTEGER | 迭代ID。                                                 |
| parallelType                          | TEXT    | 算子并行方式。                                           |
| stepStartTime                         | INTEGER | step开始时间。                                           |
| stepEndTime                           | INTEGER | step结束时间。                                           |
| totalCommunicationOperatorTime        | INTEGER | step内通信总耗时。                                       |
| timeRatioOfStepCommunicationOperator  | REAL    | step内通信总耗时与step总耗时的比值。                     |
| totalTimeWithoutCommunicationBlackout | INTEGER | step内通信算子被计算算子掩盖的总时间。                   |
| ratioOfUnmaskedCommunication          | REAL    | step内通信算子被计算算子掩盖的总时间与step总耗时的比值。 |

上表中时间相关字段，统一使用微秒（us）

**输出结果分析**

* 通过分析计算、通信找到性能瓶颈。
* 通过比较集群内各卡耗时指标差异，定位性能问题。例如，computing计算耗时波动显著，通常表明存在卡间不同步、计算卡性能不均的情况，而通信传输耗时差异过大时，则需优先排查参数面网络是否存在拥塞或配置异常。
