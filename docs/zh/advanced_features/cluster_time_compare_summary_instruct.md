# 集群性能数据细粒度比对

## 简介

大集群场景涉及多个计算节点，数据量大，原有的单卡性能数据对比不能评估整体集群运行情况。

集群性能数据细粒度比对（cluster_time_compare_summary）提供了AI运行过程中集群维度的性能数据对比能力，包括计算、通信和内存拷贝等各部分的时间消耗，帮助用户找到性能瓶颈。

## 使用前准备

**环境准备**

完成msprof_analyze工具安装，具体请参见《[msprof-analyze工具安装指南](../getting_started/install_guide.md)》。

**数据准备**

msprof-analyze需要传入采集的性能数据文件夹，如何采集性能数据请参见[数据准备](.//README.md#使用前准备)章节。

## 集群性能数据细粒度比对

**功能说明**

使用msprof-analyze工具的集群性能数据细粒度比对功能，对采集到的集群数据进行对比分析。

**命令格式**

```bash
msprof-analyze -m cluster_time_compare_summary -d <cluster_data> --bp <base_cluster_data> [-o <output_path>]
```

**参数说明**

| 参数 | 可选/必选 | 说明                                                         |
| ---- | --------- | ------------------------------------------------------------ |
| -m   | 必选      | 设置为cluster_time_compare_summary，使能集群耗时细粒度比对能力。 |
| -d   | 必选      | 集群性能数据文件夹路径。                                     |
| --bp | 必选      | 基础集群性能数据文件夹路径。                                 |
| -o   | 可选      | 指定输出文件路径，默认为-d参数指定的路径。                   |

更多参数详细介绍请参见msprof-analyze的[参数说明](./README.md#参数说明)。

**使用示例**

1. 执行cluster_time_summary分析能力，以进行集群耗时细粒度拆解。

   cluster_time_summary分析能力详细介绍请参见《[集群性能数据细粒度拆解](./cluster_time_summary_instruct.md)》。

   ```bash
   msprof-analyze -m cluster_time_summary -d ./xxx/cluster_data
   msprof-analyze -m cluster_time_summary -d ./xxx/base_cluster_data
   ```

2. 执行cluster_time_compare_summary，传入两个拆解分析后的文件夹路径。

   ```bash
   msprof-analyze -m cluster_time_compare_summary -d ./xxx/cluster_data --bp ./xxx/base_cluster_data -o ./xxx/output_path
   ```

**输出说明**

* 存储位置：输出路径下的cluster_analysis_output/cluster_analysis.db
* 数据表名：ClusterTimeCompareSummary

## 输出结果文件说明

ClusterTimeCompareSummary表字段如下：

| 字段名称       | 类型     | 说明                               |
|------------|----------|----------------------------------|
| rank       | INTEGER  | 卡号。                              |
| step       | INTEGER  | 迭代编号。                            |
| {metrics}  | REAL     | 当前集群耗时指标，与ClusterTimeSummary字段一致。 |
| {metrics}Base | REAL     | 基准集群的对应耗时。                       |
| {metrics}Diff | REAL     | 耗时偏差值（当前集群-基准集群），正值表示当前集群更慢。     |

上表中时间相关字段，统一使用微秒（us）。

**输出结果分析**

按{metrics}Diff字段排序找出最大差异项，找到劣化环节。
