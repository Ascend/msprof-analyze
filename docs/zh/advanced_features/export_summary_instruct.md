# 集群算子信息导出

## 1. 简介

在集群性能分析场景中，用户需要对各卡的算子信息进行汇总和对比分析。原有的DB格式下集群分析功能未提供单独的算子信息导出能力，用户需要手动解析各卡的数据库文件才能获取算子统计信息。

集群算子信息导出（export_summary）提供了对集群中各卡的API统计信息和Kernel详情信息的表格交付件导出功能，帮助用户快速获取各卡的算子性能数据。

## 2. 使用前准备

**环境准备**

完成msprof-analyze工具安装，具体请参见《[msprof-analyze工具安装指南](../install_guide/msprof-analyze_install_guide.md)》。

**数据准备**

msprof-analyze需要传入采集的性能数据文件夹，如何采集性能数据请参见[使用前准备](./README.md#2-使用前准备)章节。

> [!NOTE]
>
> 该功能需要输入数据包含ascend_pytorch_profiler_{rank_id}.db数据库文件。

## 3. 功能介绍

**功能说明**

使用msprof-analyze工具的集群算子信息导出功能，对采集到的集群数据进行算子信息导出，生成各卡的api_statistic.csv和kernel_details.csv文件。

**命令格式**

```bash
msprof-analyze cluster -m export_summary -d <cluster_data> 
```

**参数说明**  

| 参数 | 可选/必选 | 说明                                         |
| ---- | --------- | -------------------------------------------- |
| -m   | 必选      | 设置为export_summary，启动集群算子信息导出。 |
| -d   | 必选      | 集群性能数据文件父目录路径。                 |

更多参数详细介绍请参见msprof-analyze的[参数说明](./README.md#51-参数说明)。

**使用示例**

执行集群算子信息导出。

```bash
msprof-analyze cluster -m export_summary -d ./xxx/cluster_data 
```

**输出说明**  

在各卡的ASCEND_PROFILER_OUTPUT目录下生成：

* api_statistic.csv：API统计信息
* kernel_details.csv：Kernel详情信息

具体介绍请参见[输出结果文件说明](#4-输出结果文件说明)。

> [!NOTE]
>
> - 如果api_statistic.csv或kernel_details.csv文件已存在，工具将跳过生成并输出提示信息。
> - 导出的CSV文件可用于后续的性能分析和对比。

## 4. 输出结果文件说明

### 4.1 api_statistic.csv

API统计信息表，包含以下字段：

| 字段名称 | 类型 | 说明 |
| --- | --- | --- |
| API Name | TEXT | API名称 |
| Count | INTEGER | 调用次数 |
| Total Time(us) | REAL | 总耗时，单位us |
| Avg Time(us) | REAL | 平均耗时，单位us |
| Min Time(us) | REAL | 最小耗时，单位us |
| Max Time(us) | REAL | 最大耗时，单位us |

### 4.2 kernel_details.csv

Kernel详情信息表，包含不限于以下字段：

| 字段名称 | 类型 | 说明 |
| --- | --- | --- |
| op_name | TEXT | 算子名称 |
| op_type | TEXT | 算子类型 |
| task_type | TEXT | 任务类型 |
| task_duration | REAL | 任务耗时，单位us |
| input_shapes | TEXT | 输入形状 |
| output_shapes | TEXT | 输出形状 |
| block_dim | TEXT | Block维度 |
| input_data_types | TEXT | 输入数据类型 |
| output_data_types | TEXT | 输出数据类型 |

### 4.3 输出结果分析

* 通过api_statistic.csv分析各API的调用频率和耗时分布，识别高频或高耗时的API。
* 通过kernel_details.csv分析各算子的执行细节，包括输入输出形状、数据类型等信息。
* 对比不同卡的算子信息，识别卡间性能差异。
