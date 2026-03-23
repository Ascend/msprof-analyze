# 性能分析工具

## 简介

本文介绍msprof-analyze工具的完整命令参数并提供子功能、特性的指导文档链接。

## 使用前准备

**环境准备**

完成msprof-analyze工具安装，具体请参见《[msprof-analyze工具安装指南](./install_guide.md)》。

**数据准备**

msprof-analyze工具将Profiling性能数据作为输入，进行性能数据分析，支持分析如下场景的性能数据：

  * msProf场景性能数据采集，具体操作请参见《[模型调优工具](https://gitcode.com/Ascend/msprof/blob/master/docs/zh/quick_start.md)》。
  * PyTorch场景性能数据采集，具体操作请参见《[Ascend PyTorch调优工具](https://gitcode.com/Ascend/pytorch/blob/v2.7.1/docs/zh/ascend_pytorch_profiler/ascend_pytorch_profiler_user_guide.md)》。
  * MindSpore场景性能数据采集，具体操作请参见《[MindSpore调优工具](https://www.hiascend.com/document/detail/zh/mindstudio/830/T&ITools/Profiling/atlasprofiling_16_0118.html)》。
  * msMonitor场景性能数据采集，具体操作请参见《[msMonitor](https://gitcode.com/Ascend/msmonitor/blob/master/docs/zh/quick_start.md)》。

## 工具使用

### 功能说明

msprof-analyze为性能分析工具的主命令，可直接配置：

- [全局参数](#全局参数)实现对Profiling性能数据的分析操作。
- [分析能力参数](#分析能力参数)配置数据分析时的执行动作。
- [子功能命令参数](#子功能命令参数)执行除数据分析之外的性能比对和专家建议功能。

其中[分析特性介绍](#分析特性介绍)为性能分析的各种分析特性，通过全局参数的-m参数配置。

### 命令格式

msprof-analyze（version ≥ 8.2.0a1）性能分析工具通过命令行方式启动性能分析。命令格式如下：

```bash
msprof-analyze -m [feature_option] -d <profiling_path> [global_option] [analyze_option]
```

* `-m`：指定分析能力，`[feature_option]`可指定对应特性，具体请参见[分析特性介绍](#分析特性介绍)章节，必选。  
* `-d <profiling_path>`：Profiling性能数据文件夹，必选。  
* `[global_option]`：全局参数，具体请参见[全局参数](#全局参数)章节，可选。  
* `[analyze_option]`：分析能力参数，具体请参见[分析能力参数](#分析能力参数)章节，可选。  

详细使用样例请参见[使用样例](#使用样例)章节。

对于msprof-analyze version < 8.2.0a1的版本，需在命令中添加`cluster子`命令，格式如下：

```bash
msprof-analyze cluster -m [feature_option] -d <profiling_path> [global_option] [analyze_option]
```

### 参数说明

#### 全局参数

主要包括输入输出与格式参数、执行参数以及帮助信息等。

| 参数名                | 可选/必选 | 说明                                                                                                                                                                                                     |
| --------------------- | -------- |--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| --profiling_path或-d  | 必选     | 性能数据汇集目录。未配置-o参数时，运行分析脚本之后会在该目录下自动创建cluster_analysis_output文件夹，保存分析数据。                                                                                                                                 |
| --output_path或-o     | 可选     | 自定义输出路径，运行分析脚本之后会在该目录下自动创建cluster_analysis_output文件夹，保存分析数据。                                                                                                                                           |
| --mode或-m            | 可选     | 分析能力选项，取值详见[分析能力特性说明](#分析特性介绍)表。  默认参数为all，all会执行step_trace_time、communication_matrix通信矩阵和communication_time通信耗时分析能力。                                                                                  |
| --export_type         | 可选     | 设置导出的数据形式。取值为db（.db格式文件）、notebook（Jupyter Notebook文件）、text（泛指json/csv/excel等文本格式文件），默认值为db。                                                                                                                               |
| --force               | 可选     | 强制执行，用户对force行为负责，配置后可强制跳过如下情况：<br/>&#8226; 指定的目录、文件的用户属主不属于当前用户，忽略属主判断直接执行。<br/>&#8226; csv文件大于5G、json文件大于10G、db文件大于8G，忽略文件过大判断直接执行。<br/>&#8226; 指定的目录、文件的读写权限，忽略权限判断直接执行。<br/>配置该参数表示开启强制执行，默认未配置表示关闭。 |
| --parallel_mode       | 可选     | 设置收集多卡、多节点db数据时的并发方式。取值为concurrent（使用concurrent.feature进程池实现并发）。                                                                                                                                       |
| -v，-V<br/>--version | 可选 | 查看版本号。                                                                                                                                                                                                 |
| -h，-H<br>--help     | 可选 | 命令行参数帮助信息。                                                                                                                                                                                             |

#### 分析能力参数

| 参数名                | 可选/必选 | 说明                                                                                                                                                                                                                                                                                             |
| --------------------- | -------- |------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| --rank_list           | 可选     | 对特定Rank上的数据进行统计，默认值为all（表示对所有Rank进行统计），须根据实际卡的Rank ID配置。应配置为大于等于0的整数，若所配置的值大于实际训练所运行的卡的Rank ID，则仅解析合法的RankID的数据，比如当前环境Rank ID为0到7，实际训练运行0到3卡，此时若配置Rank ID为0， 3， 4或不存在的10等其他值，则仅解析0和3。配置示例：--rank_list 0,1,2。<br/>**需要对应分析能力适配才可使用， 当前分析能力设置cann_api_sum、compute_op_sum、hccl_sum、mstx_sum时支持。** |
| --step_id             | 可选 | 性能数据Step ID，配置后对该Step的性能数据进行分析。需配置性能数据中实际存在的Step ID，默认未配置，表示全量分析。配置示例：--step_id=1。<br/>**需要对应分析能力适配才可使用， 当前只有分析能力设置cann_api_sum、compute_op_sum、hccl_sum、mstx_sum时支持。**                                                                                                                         |
| --top_num             | 可选     | 设置TopN耗时的通信算子的数量，默认值为15，配置示例：--top_num 20。<br/>**只有-m配置hccl_sum时可配置此参数。**                                                                                                                                                                                                                      |
| --exclude_op_name    | 可选     | 控制compute_op_name结果是否包含op_name，示例：--exclude_op_name，后面不需要跟参数。<br/>**只有-m配置compute_op_sum时可配置此参数。**                                                                                                                                                                                             |
| --bp                 | 可选     | 要对比的标杆集群数据，示例：--bp {bp_cluster_profiling_path}，表示profiling_path和bp_cluster_profiling_path的数据进行对比。<br/>**只有-m配置cluster_time_compare_summary时可配置此参数。**                                                                                                                                           |

#### 子功能命令参数

| 参数            | 说明                                                         | 文档链接                                  |
| --------------- | ------------------------------------------------------------ | ----------------------------------------- |
| compare         | 性能比对功能，提供NPU与GPU性能拆解功能以及算子、通信、内存性能的比对功能。 | [性能比对](./compare_tool_instruct.md)    |
| advisor         | 专家建议功能，基于性能数据进行分析，并输出性能调优建议。     | [专家建议](./advisor_instruct.md)         |
| cluster         | 集群分析功能，提供集群分析能力。8.2.0a1版本后，该参数可不配置，对应分析功能在msprof-analyze命令下直接执行。 | [集群分析](./cluster_analyse_instruct.md) |
| auto-completion | 自动补全，配置后在当前视图下配置msprof-analyze工具所有的子参数时，可以使用Tab将所有子参数自动补全。 | -                                         |

### 分析特性介绍

#### 拆解对比类

| 分析能力                     | 介绍                                                         | 文档链接                                                     |
| ---------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| cluster_time_summary         | 提供集群训练过程中迭代耗时的拆解，帮助用户找到性能瓶颈。     | [集群性能数据细粒度拆解](./cluster_time_summary_instruct.md) |
| cluster_time_compare_summary | 提供AI运行过程中集群维度的性能数据对比能力，帮助用户找到性能瓶颈。 | [集群性能数据细粒度比对](./cluster_time_compare_summary_instruct.md) |
| module_statistic             | 针对PyTorch模型自动解析模型层级结构的分析能力，帮助用户精准定位性能瓶颈。 | [性能数据模型结构拆解](./module_statistic_instruct.md)       |
| calibrate_npu_gpu            | 自动对比NPU和GPU的性能数据，帮助用户进行跨平台的性能校准和瓶颈分析。 | [NPU&GPU性能数据拆解比对](./calibrate_npu_gpu_instruct.md)   |

#### 计算类特性

| 分析能力                 | 介绍                                                         | 文档链接                                                     |
| ------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| compute_op_sum           | device侧运行的计算类算子汇总。                               | -                                                            |
| freq_analysis            | 识别aicore是否存在空闲（频率为800MHz）、异常（频率不为1800MHz或800MHz）的情况并给出分析结果。 | -                                                            |
| ep_load_balance          | moe负载信息汇总分析。                                        | -                                                            |
| computational_op_masking | 提供集群训练过程中不同算子耗时的掩盖计算，帮助用户找到性能瓶颈。 | [集群算子掩盖线性度分析](./computational_op_masking_instruct.md) |

#### 通信类特性

| 分析能力                 | 介绍                                                         | 文档链接                                               |
| ------------------------ | ------------------------------------------------------------ | ------------------------------------------------------ |
| communication_matrix     | 通信矩阵分析。                                               | -                                                      |
| communication_time       | 通信耗时分析。                                               | -                                                      |
| all                      | 默认值，会执行communication_matrix通信矩阵和communication_time通信耗时分析能力，并导出cluster_step_trace_time交付件。 | -                                                      |
| communication_group_map  | 集群场景通信域与并行策略呈现。                               | -                                                      |
| communication_time_sum   | 集群场景通信时间和带宽汇总分析。                             | -                                                      |
| communication_matrix_sum | 集群场景通信矩阵汇总分析。                                   | -                                                      |
| hccl_sum                 | 通信类算子信息汇总。                                         | -                                                      |
| pp_chart                 | pp流水图数据分析，针对pp并行下各个阶段的耗时分析与可视化能力。 | [pp流水图数据分析](./pp_chart_instruct.md)             |
| slow_rank                | 根据当前的快慢卡统计算法，展示各个rank得出的快慢卡影响次数，识别慢卡出现的原因。 | -                                                      |
| communication_bottleneck | 对于长耗时通信算子，识别快慢卡，并推测造成通信等待的Host/Device侧操作。 | [通信瓶颈分析](./communication_bottleneck_instruct.md) |

#### Host下发类特性

| 分析能力      | 介绍                                                         | 文档链接                                        |
| ------------- | ------------------------------------------------------------ | ----------------------------------------------- |
| cann_api_sum  | CANN层API的汇总。                                            | -                                               |
| mstx_sum      | MSTX自定义打点汇总。                                         | -                                               |
| free_analysis | 提供对Device侧大块空闲时间的自动分析能力，能够识别空闲时间产生的原因，帮助用户定位性能问题。 | [空闲时间原因分析](./free_analysis_instruct.md) |

#### 其他特性

| 分析能力   | 类别 | 介绍                                     | 文档链接 |
|---------|----| ------------------------------------|-----|
| mstx2commop | 数据处理类 | 将通过MSTX内置通信打点的通信信息转换成通信算子表格式。 | -  |
| p2p_pairing | 数据处理类 | P2P算子生成全局关联索引，输出的关联索引会作为一个新的字段`opConnectionId`附在`COMMUNICATION_OP`的表中。 | -  |

### 使用样例

#### 最简使用

```bash
# 只传入cluster_data性能数据文件夹，输入cluster_time_summary分析能力，在cluster_data输入文件夹下生成cluster_analysis_output文件夹，保存分析结果信息
msprof-analyze -m cluster_time_summary -d ./cluster_data
```

#### 分析能力为all设置下使用

```bash
# 可以输入-m参数为all，当前输出step_trace_time、通信矩阵、通信耗时交付件
msprof-analyze -m all -d ./cluster_data
```

#### 指定输出路径

```bash
# 设置-o参数，指定自定义输出路径
msprof-analyze -m cluster_time_summary -d ./cluster_data -o ./cluster_output
```

#### 设置输出格式

```bash
# 设置--export_type参数，设置输出格式
msprof-analyze -m cluster_time_summary -d ./cluster_data --export_type db
```

#### 性能对比（compare）子功能

支持GPU与NPU之间、NPU与NPU之间两组性能数据的深度对比，通过多维度量化指标直观呈现性能差异。

```bash
# 基础用法：对比昇腾NPU与GPU性能数据
msprof-analyze compare -d ./ascend_pt  # 昇腾NPU性能数据目录
                       -bp ./gpu_trace.json  # GPU性能数据文件
                       -o ./compare_output  # 对比结果输出目录
```

对比报告`performance_comparison_result_{timestamp}.xlsx`包含：

* 宏观性能拆分：按计算、通信、空闲三大维度统计耗时占比差异，快速识别性能损耗主要场景。
* 细粒度对比：按算子（如 Conv、MatMul）、框架接口等粒度展示耗时差异，定位具体性能差距点。

> 对比规则维度、参数说明及报告解读，请参见[msprof-analyze compare](./compare_tool_instruct.md)子功能介绍文档。

#### 专家建议（advisor）子功能

自动分析性能数据，识别算子执行效率、下发调度、集群通信等潜在瓶颈，并生成分级优化建议，助力快速定位问题。

```bash
# 基础用法
msprof-analyze advisor all -d ./prof_data -o ./advisor_output
```

分析完成后，在执行终端打印关键问题与优化建议，并生成

* `mstt_advisor_{timestamp}.html`按重要程度标记的优化建议
* `mstt_advisor_{timestamp}.xlsx`问题综述与详细的分析信息

> 详细分析规则、参数配置及结果解读，请参见[msprof-analyze advisor](advisor_instruct.md)子功能介绍文档。

#### 集群分析（cluster）子功能

提供集群分析能力，例如对基于通信域的迭代内耗时分析、通信时间分析以及通信矩阵分析为主，从而定位慢卡、慢节点以及慢链路问题。

```bash
# 基础用法
## 命令行方式
msprof-analyze cluster -m all # 分析能力 
                       -d ./cluster_data  # 昇腾NPU集群性能数据目录
                       -o ./compare_output  # 集群分析结果输出目录
## 脚本方式
python3 cluster_analysis.py -m all  # 分析能力 
                            -d ./cluster_data  # 昇腾NPU集群性能数据目录
                            -o ./compare_output  # 集群分析结果输出目录
```

> 集群分析子功能已整合至msprof-analyze下，详细分析规则、参数配置，请参见[工具使用](#工具使用)。

### 输出结果文件说明

msprof-analyze分析特性的输出交付件详细内容请参见[recipe结果交付件表](./recipe_output_format_introduct.md)文档。

## 扩展功能

### 自定义开发指导

用户可自定义一套性能数据的分析规则，需要详细了解性能分析的开发人员，具体开发指导请参见[自定义分析能力开发指导](./custom_analysis_guide.md)。

### 集群算子耗时分析

集群场景下，基于多卡性能数据的op_summary信息，统计并展示各卡中执行最快、最慢、均值和方差的TopN算子。具体请参见[集群算子耗时分析](./cluster_kernels_analysis_instruct.md)。
