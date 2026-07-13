# 集群算子掩盖线性度分析

## 1. 简介

大集群场景涉及到多个计算节点，数据量大，单卡维度的性能数据统计与分析无法评估整体集群算子运行情况的掩盖程度。

集群算子掩盖线性度分析（computational_op_masking）提供了集群训练过程中不同并行场景下，算子掩盖耗时的分析功能，包括计算、通信各部分，帮助用户找到性能瓶颈。

## 2. 使用前准备

**环境准备**

完成msprof-analyze工具安装，具体请参见《[msprof-analyze工具安装指南](../install_guide/msprof-analyze_install_guide.md)》。

**数据准备**

msprof-analyze需要传入采集的性能数据文件夹，如何采集性能数据请参见[使用前准备](./README.md#2-使用前准备)章节。

## 3. 功能介绍

**功能说明**

使用msprof-analyze工具的集群算子掩盖线性度分析功能，对采集到的集群数据进行分析。

**命令格式**

```bash
msprof-analyze -m computational_op_masking [--export_type <export_type>] [--step_id <step_id>] [--parallel_types <parallel_types>] -d <cluster_data> [-o <output_path>]
```

**参数说明**  

| 参数                | 可选/必选 | 说明                                                                                   |
|-------------------|-------|--------------------------------------------------------------------------------------|
| -m                | 必选    | 设置为computational_op_masking，启动集群性能数据细粒度拆解。                                      |
| --export_type     | 可选    | 输出文件类型，当前场景仅支持配置为 `db`。                           |
| --step_id         | 可选    | 设置step ID取该step结果进行保存，不设置默认输出所有step的结果。                                                 |
| --parallel_types  | 可选    | 设置计算不同并行模式下，通信算子被计算算子掩盖的程度。例如："edp,dp;dp;edp" 实际含义：[('edp','dp'), ('dp',), ('edp',)] |
| -d                | 必选    | 集群性能数据文件父目录路径。                                                                         |
| -o   | 可选      | 分析结果输出路径，默认输出在-d参数指定的目录下。               |

更多参数详细介绍请参见msprof-analyze的[参数说明](./README.md#51-参数说明)。

**使用示例**

执行集群算子掩盖线性度分析。

```bash
msprof-analyze -m computational_op_masking --export_type db --step_id 11 --parallel_types "edp,dp;dp;edp" -d ./xxx/cluster_data -o ./xxx/output_path
```

**输出说明**  

在-o参数指定路径下生成`cluster_analysis_output/cluster_analysis.db`文件，在该文件中生成`ComputationalOperatorMaskingLinearity`表，具体介绍请参见[输出结果文件说明](#4-输出结果文件说明)。

## 4. 输出结果文件说明

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

上表中时间相关字段单位统一使用微秒（us）。

**输出结果分析**

* 通过分析计算、通信找到性能瓶颈。
* 通过比较集群内各卡耗时指标差异，定位性能问题。例如，computing计算耗时波动显著，通常表明存在卡间不同步、计算卡性能不均的情况，而通信传输耗时差异过大时，则需优先排查参数面网络是否存在拥塞或配置异常。
