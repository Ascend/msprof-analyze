# Recipe 分析规则库

本章汇总 `msprof-analyze` 在集群场景下的进阶分析能力，涵盖集群多维信息汇总、拆解对比、通信瓶颈定位和下发问题分析等专题。此外，支持通过 `Recipe` 规则进行自定义分析，具体开发指导请参见[自定义分析能力开发指导](./custom_analysis_guide.md)。

## 使用前准备

支持以下两种集群数据：

* Ascend PyTorch Profiler 采集的 DB 格式集群数据
* msMonitor 采集的集群轻量化 DB 数据

采集指南请参见 [《数据准备》](../getting_started/profiling_data_guide.md)。

使用 Ascend PyTorch Profiler 时，需要采集或离线解析出 `db` 类型结果。示例如下：

```python
experimental_config = torch_npu.profiler._ExperimentalConfig(
    export_type=[torch_npu.profiler.ExportType.Db]
)
```

或者在离线解析时指定导出类型：

```python
from torch_npu.profiler.profiler import analyse

if __name__ == "__main__":
    analyse(profiler_path="./result_data", export_type=["db"])
```

## 使用方式

通过以下命令行形式调用：

```bash
msprof-analyze -m <feature> -d <profiling_path> [options]
```

示例：

```bash
msprof-analyze -m cluster_time_summary -d ./cluster_data -o ./output
msprof-analyze -m free_analysis -d ./cluster_data -o ./output
```

常用参数说明如下：

- `-m`：指定分析能力。
- `-d`：指定 profiling 数据路径。
- `-o`：指定输出路径；未配置时，结果默认保存在输入路径下的 `cluster_analysis_output` 目录。

更多参数说明详见 [《参数说明》](#参数说明)。

## 分析能力

### 拆解对比类

| 分析能力                     | 介绍                                                         | 文档链接                                                     |
| ---------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| cluster_time_summary         | 提供集群训练过程中迭代耗时的拆解，帮助用户找到性能瓶颈。     | [集群性能数据细粒度拆解](./cluster_time_summary_instruct.md) |
| cluster_time_compare_summary | 提供AI运行过程中集群维度的性能数据对比能力，帮助用户找到性能瓶颈。 | [集群性能数据细粒度比对](./cluster_time_compare_summary_instruct.md) |
| module_statistic             | 针对PyTorch模型自动解析模型层级结构的分析能力，帮助用户精准定位性能瓶颈。 | [性能数据模型结构拆解](./module_statistic_instruct.md) |
| calibrate_npu_gpu            | 自动对比NPU和GPU的性能数据，帮助用户进行跨平台的性能校准和瓶颈分析。 | [NPU&GPU性能数据拆解比对](./calibrate_npu_gpu_instruct.md) |

### 计算类特性

| 分析能力                      | 介绍          | 文档链接 |
|---------------------------|-------------|---|
| compute_op_sum            | device侧运行的计算类算子汇总。 | - |
| freq_analysis             | 识别aicore是否存在空闲（频率为800MHz）、异常（频率不为1800MHz或800MHz）的情况并给出分析结果。 | - |
| ep_load_balance           | moe负载信息汇总分析。 | - |
| computational_op_masking  | 提供集群训练过程中不同算子耗时的掩盖计算，帮助用户找到性能瓶颈。 | [集群算子掩盖线性度分析](./computational_op_masking_instruct.md) |

### 通信类特性

| 分析能力                 | 介绍                                                         | 文档链接                                                     |
| ------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| communication_group_map  | 集群场景通信域与并行策略呈现。                               | -                                                            |
| communication_time_sum   | 集群场景通信时间和带宽汇总分析。                             | -                                                            |
| communication_matrix_sum | 集群场景通信矩阵汇总分析。                                   | -                                                            |
| hccl_sum                 | 通信类算子信息汇总。                                         | -                                                            |
| pp_chart                 | pp流水图数据分析，针对pp并行下各个阶段的耗时分析与可视化能力。 | [pp流水图数据分析](./pp_chart_instruct.md)           |
| slow_rank                | 根据当前的快慢卡统计算法，展示各个rank得出的快慢卡影响次数，识别慢卡出现的原因。 | -                                                            |
| communication_bottleneck | 对于长耗时通信算子，识别快慢卡，并推测造成通信等待的Host/Device侧操作。 | [通信瓶颈分析](./communication_bottleneck_instruct.md) |

### Host下发类特性

| 分析能力      | 介绍                                                         | 文档链接                                                |
| ------------- | ------------------------------------------------------------ | ------------------------------------------------------- |
| cann_api_sum  | CANN层API的汇总。                                            | -                                                       |
| mstx_sum      | MSTX自定义打点汇总。                                         | -                                                       |
| free_analysis | 提供对Device侧大块空闲时间的自动分析能力，能够识别空闲时间产生的原因，帮助用户定位性能问题。 | [空闲时间原因分析](./free_analysis_instruct.md) |

### 其他特性

| 分析能力   | 类别 | 介绍                                     | 文档链接 |
|---------|----| ------------------------------------|-----|
| mstx2commop | 数据处理类 | 将通过MSTX内置通信打点的通信信息转换成通信算子表格式。 | -  |
| p2p_pairing | 数据处理类 | P2P算子生成全局关联索引，输出的关联索引会作为一个新的字段`opConnectionId`附在`COMMUNICATION_OP`的表中。 | -  |

## 输出结果文件说明

msprof-analyze分析特性的输出交付件详细内容请参见[recipe结果交付件表](./recipe_output_format_introduct.md)文档。

### 参数说明

#### 全局参数

主要包括输入输出与格式参数、执行参数以及帮助信息等。

| 参数名                | 可选/必选 | 说明                                                                                                                                                                                                     |
| --------------------- | -------- |--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| --profiling_path或-d  | 必选     | 性能数据汇集目录。未配置-o参数时，运行分析脚本之后会在该目录下自动创建cluster_analysis_output文件夹，保存分析数据。                                                                                                                                 |
| --output_path或-o     | 可选     | 自定义输出路径，运行分析脚本之后会在该目录下自动创建cluster_analysis_output文件夹，保存分析数据。                                                                                                                                           |
| --mode或-m            | 可选     | 分析能力选项，取值详见[分析能力](#分析能力)表。                                                                                  |
| --export_type         | 可选     | 设置导出的数据形式。取值为db（.db格式文件）、notebook（Jupyter Notebook文件）、text（泛指json/csv/excel等文本格式文件），默认值为db。                                                                                                                               |
| --force               | 可选     | 强制执行，用户对force行为负责，配置后可强制跳过如下情况：<br/>&#8226; 指定的目录、文件的用户属主不属于当前用户，忽略属主判断直接执行。<br/>&#8226; csv文件大于5G、json文件大于10G、db文件大于8G，忽略文件过大判断直接执行。<br/>&#8226; 指定的目录、文件的读写权限，忽略权限判断直接执行。<br/>配置该参数表示开启强制执行，默认未配置表示关闭。 |
| --parallel_mode       | 可选     | 设置收集多卡、多节点db数据时的并发方式。取值为concurrent（使用concurrent.feature进程池实现并发）。                                                                                                                                       |
| -v，-V<br/>--version | 可选 | 查看版本号。                                                                                                                                                                                                 |
| -h，-H<br>--help     | 可选 | 命令行参数帮助信息。                                                                                                                                                                                             |
| auto-completion     | 可选 | 自动补全，配置后在当前视图下配置msprof-analyze工具所有的子参数时，可以使用Tab将所有子参数自动补全。                                                      | -

#### 分析能力参数

| 参数名                | 可选/必选 | 说明                                                                                                                                                                                                                                                                                             |
| --------------------- | -------- |------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| --rank_list           | 可选     | 对特定Rank上的数据进行统计，默认值为all（表示对所有Rank进行统计），须根据实际卡的Rank ID配置。应配置为大于等于0的整数，若所配置的值大于实际训练所运行的卡的Rank ID，则仅解析合法的RankID的数据，比如当前环境Rank ID为0到7，实际训练运行0到3卡，此时若配置Rank ID为0， 3， 4或不存在的10等其他值，则仅解析0和3。配置示例：--rank_list 0,1,2。<br/>**需要对应分析能力适配才可使用， 当前分析能力设置cann_api_sum、compute_op_sum、hccl_sum、mstx_sum时支持。** |
| --step_id             | 可选 | 性能数据Step ID，配置后对该Step的性能数据进行分析。需配置性能数据中实际存在的Step ID，默认未配置，表示全量分析。配置示例：--step_id=1。<br/>**需要对应分析能力适配才可使用， 当前只有分析能力设置cann_api_sum、compute_op_sum、hccl_sum、mstx_sum时支持。**                                                                                                                         |
| --top_num             | 可选     | 设置TopN耗时的通信算子的数量，默认值为15，配置示例：--top_num 20。<br/>**只有-m配置hccl_sum时可配置此参数。**                                                                                                                                                                                                                      |
| --exclude_op_name    | 可选     | 控制compute_op_name结果是否包含op_name，示例：--exclude_op_name，后面不需要跟参数。<br/>**只有-m配置compute_op_sum时可配置此参数。**                                                                                                                                                                                             |
| --bp                 | 可选     | 要对比的标杆集群数据，示例：--bp {bp_cluster_profiling_path}，表示profiling_path和bp_cluster_profiling_path的数据进行对比。<br/>**只有-m配置cluster_time_compare_summary时可配置此参数。**                                                                                                                                           
