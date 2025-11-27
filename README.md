# MindStudio-Profiler-Analyze（msprof-analyze）

## 📌 简介
MindStudio-Profiler-Analyze（简称msprof-analyze）是MindStudio全流程工具链推出的性能分析工具，基于采集的性能数据进行分析，识别AI作业中的性能瓶颈。

## 🔧 安装

msprof-analyze的安装方式包括：**pip安装**、**下载whl包安装**和**源代码编译安装**。

### 下载whl包安装

1. whl包获取。
   请通过[发布程序包下载链接](#发布程序包下载链接)下载whl包。

2. whl包校验。

   1. 根据以上下载链接下载whl包到Linux安装环境。

   2. 进入whl包所在目录，执行如下命令。

      ```
      sha256sum {name}.whl
      ```

      {name}为whl包名称。

      若回显呈现对应版本whl包一致的**校验码**，则表示下载了正确的性能工具whl安装包。示例如下：

      ```bash
      sha256sum msprof_analyze-1.0-py3-none-any.whl
      xx *msprof_analyze-1.0-py3-none-any.whl
      ```

3. whl包安装。

   执行如下命令进行安装。

   ```bash
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

   提示如下信息则表示安装成功。

   ```bash
   Successfully installed msprof_analyze-{version}
   ```

###  pip安装

```shell
pip install msprof-analyze
```

使用`pip install msprof-analyze==版本号`可安装指定版本的包，使用采集性能数据对应的CANN版本号即可。  
如不清楚版本号可不指定，使用最新程序包。

pip命令会自动安装最新的包及其配套依赖。

提示如下信息则表示安装成功。

```bash
Successfully installed msprof-analyze-{version}
```

### 源代码编译安装

1. 安装依赖。

   编译前需要安装wheel。

   ```bash
   pip3 install wheel
   ```

2. 下载源码。

   ```bash
   git clone https://gitcode.com/Ascend/msprof-analyze
   ```

3. 编译whl包。

**在安装如下依赖时，请注意使用满足条件的较新版本软件包，关注并修补存在的漏洞，尤其是已公开的CVSS打分大于7分的高危漏洞。**
   ```bash
   pip3 install -r requirements.txt && python3 setup.py bdist_wheel
   ```

   以上命令执行完成后在dist目录下生成性能工具whl安装包`msprof_analyze-{version}-py3-none-any.whl`。

4. 安装。

   执行如下命令进行性能工具安装。

   ```bash
   cd dist
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

### 卸载和更新

若需要更新工具，请先卸载旧版本后再重新安装新版本，操作如下：
```bash
# 卸载旧版本
pip3 uninstall msprof-analyze
# 安装新版本
pip3 install ./msprof_analyze-{version}-py3-none-any.whl
```

## 🧰 使用方法
### 数据准备
msprof-analyze需要传入采集的性能数据文件夹，如何采集性能数据请参见[采集profiling性能数据指导](#采集profiling性能数据指导)章节。

### 命令格式
msprof-analyze（version ≥ 8.2.0a1）性能分析工具通过命令行方式启动性能分析。命令格式如下：

```
msprof-analyze -m [feature_option] -d <profiling_path> [global_option] [analyze_option]
```
* `-m`指定分析能力，`[feature_option]`可指定对应特性，详见[分析特性介绍](#分析特性介绍)章节，必选。  
* `<profiling_path>`为profiling性能数据文件夹，必选。  
* `[global_option]`为全局参数，详见[全局参数说明](#全局参数)章节，可选。  
* `[analyze_option]`为分析能力参数，详见[分析能力参数说明](#分析能力参数)章节，可选。  

详细使用样例请参考[使用样例](#使用样例)章节。

对于 version < 8.2.0a1 的版本，需在命令中添加 cluster 子命令，格式如下：
```
msprof-analyze cluster -m [feature_option] -d <profiling_path> [global_option] [analyze_option]
```

### 参数说明
#### 全局参数
主要包括输入输出与格式参数、执行参数以及帮助信息等。

   | 参数名                | 说明                                                                                                                                                                                                       | 是否必选 |
   | --------------------- |----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------| -------- |
   | --profiling_path或-d  | 性能数据汇集目录。未配置-o参数时，运行分析脚本之后会在该目录下自动创建cluster_analysis_output文件夹，保存分析数据。                                                                                                                                   | 是       |
   | --output_path或-o     | 自定义输出路径，运行分析脚本之后会在该目录下自动创建cluster_analysis_output文件夹，保存分析数据。                                                                                                                                             | 否       |
   | --mode或-m            | 分析能力选项，取值详见[分析能力特性说明](#分析特性介绍)表。  默认参数为all，all会执行step_trace_time和communication_matrix通信矩阵和communication_time通信耗时分析能力。                                                                                    | 否       |
   | --export_type         | 设置导出的数据形式。取值为db（.db格式文件）和notebook（Jupyter Notebook文件），默认值为db。                                                                                                                                            | 否       |
   | --force               | 强制执行，用户对force行为负责，配置后可强制跳过如下情况：<br/>        指定的目录、文件的用户属主不属于当前用户，忽略属主判断直接执行。<br/>        csv文件大于5G、json文件大于10G、db文件大于8G，忽略文件过大判断直接执行。<br/>        指定的目录、文件的读写权限，忽略权限判断直接执行。<br/>配置该参数表示开启强制执行，默认未配置表示关闭。 | 否       |
   | --parallel_mode       | 设置收集多卡、多节点db数据时的并发方式。取值为concurrent（使用concurrent.feature进程池实现并发）。                                                                                                                                         | 否       |
   | -v，-V<br/>--version | 查看版本号。                                                                                                                                                                                                   | 否 |
   | -h，-H<br>--help     | 命令行参数帮助信息。                                                                                                                                                                                               | 否 |

#### 分析能力参数

   | 参数名                | 说明                                                                                                                                                                                                                                                                                             | 是否必选 |
   | --------------------- |------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------| -------- |
   | --rank_list           | 对特定Rank上的数据进行统计，默认值为all（表示对所有Rank进行统计），须根据实际卡的Rank ID配置。应配置为大于等于0的整数，若所配置的值大于实际训练所运行的卡的Rank ID，则仅解析合法的RankID的数据，比如当前环境Rank ID为0到7，实际训练运行0到3卡，此时若配置Rank ID为0， 3， 4或不存在的10等其他值，则仅解析0和3。配置示例：--rank_list 0,1,2。<br/>**需要对应分析能力适配才可使用， 当前分析能力设置cann_api_sum、compute_op_sum、hccl_sum、mstx_sum时支持。** | 否       |
   | --step_id             | 性能数据Step ID，配置后对该Step的性能数据进行分析。需配置性能数据中实际存在的Step ID，默认未配置，表示全量分析。配置示例：--step_id=1。<br/>**需要对应分析能力适配才可使用， 当前只有分析能力设置cann_api_sum、compute_op_sum、hccl_sum、mstx_sum时支持。**                                                                                                                         | 否 |
   | --top_num             | 设置TopN耗时的通信算子的数量，默认值为15，配置示例：--top_num 20。<br/>**只有-m配置hccl_sum时可配置此参数。**                                                                                                                                                                                                                      | 否       |
   | --exclude_op_name    | 控制compute_op_name结果是否包含op_name，示例：--exclude_op_name，后面不需要跟参数。<br/>**只有-m配置compute_op_sum时可配置此参数。**                                                                                                                                                                                             | 否       |
   | --bp                 | 要对比的标杆集群数据，示例：--bp {bp_cluster_profiling_path}，表示profiling_path和bp_cluster_profiling_path的数据进行对比。<br/>**只有-m配置cluster_time_compare_summary时可配置此参数。**                                                                                                                                           | 否       |

#### 子功能命令参数
| 参数   | 说明                                                                                                               |
|---------------------|------------------------------------------------------------------------------------------------------------------|
| compare             | [compare（性能比对子功能）](./docs/zh/compare_tool_instruct.md)。提供NPU与GPU性能拆解功能以及算子、通信、内存性能的比对功能。  |
| advisor             | [advisor（专家建议子功能）](./docs/zh/advisor_instruct.md)。基于性能数据进行分析，并输出性能调优建议。 |
| cluster              | [cluster_analyse（集群分析工具）](./docs/zh/cluster_analyse_introduct.md)。提供集群分析能力。8.2.0a1版本后，该参数可不配置，对应分析功能在msprof-analyze命令下直接执行。 |
| auto-completion     | 自动补全。配置后在当前视图下配置msprof-analyze工具所有的子参数时，可以使用Tab将所有子参数自动补全。                                                       |


### 分析特性介绍

#### 拆解对比类

| 分析能力    | 介绍                                     | 介绍链接 |
|---------|----------------------------------------|-----|
| cluster_time_summary | 性能数据细粒度拆解，替换step_trace_time.csv内容。 | [link](./docs/zh/cluster_time_summary_instruct.md) |
| cluster_time_compare_summary | 性能数据细粒度对比。 | [link](./docs/zh/cluster_time_compare_summary_instruct.md) |

#### 计算类特性

| 分析能力    | 介绍                                                          | 介绍链接 |
|---------|-------------------------------------------------------------|-----|
| compute_op_sum | device侧运行的计算类算子汇总。                                          | -  |
| freq_analysis | 识别aicore是否存在空闲（频率为800MHz）、异常（频率不为1800MHz或800MHz）的情况并给出分析结果。 | -  |
| ep_load_balance | moe负载信息汇总分析。                                                | - |

#### 通信类特性

| 分析能力    | 介绍                                                                                        | 介绍链接 |
|---------|-------------------------------------------------------------------------------------------|-----|
| communication_matrix | 通信矩阵分析。                                                                                   | -  |
| communication_time| 通信耗时分析。                                                                                   | -   |
| all | 默认值，会执行communication_matrix通信矩阵和communication_time通信耗时分析能力，并导出cluster_step_trace_time交付件。 | -  |
| communication_group_map | 集群场景通信域与并行策略呈现。                                                                           | -   |
| communication_time_sum | 集群场景通信时间和带宽汇总分析。                                                                          | -   |
| communication_matrix_sum | 集群场景通信矩阵汇总分析。                                                                             | -   |
| hccl_sum | 通信类算子信息汇总。                                                                                | -   |
| pp_chart | pp流水图，针对pp并行下各个阶段的耗时分析与可视化能力。                                                             | [link](./docs/zh/pp_chart_instruct.md) |
| slow_rank | 根据当前的快慢卡统计算法，展示各个rank得出的快慢卡影响次数，识别慢卡出现的原因。                                                | -  |

#### Host下发类特性

| 分析能力    | 介绍                                     | 介绍链接 |
|---------|----------------------------------------|-----|
| cann_api_sum | CANN层API的汇总。 | -  |
| mstx_sum | MSTX自定义打点汇总。 | -  |

#### 其他特性
| 分析能力   | 类别 | 介绍                                     | 介绍链接 |
|---------|----| ------------------------------------|-----|
| mstx2commop | 数据处理类 | 将通过MSTX内置通信打点的通信信息转换成通信算子表格式。 | -  |
| p2p_pairing | 数据处理类 | P2P算子生成全局关联索引，输出的关联索引会作为一个新的字段`opConnectionId`附在`COMMUNICATION_OP`的表中。 | -  |

交付件详细内容请参见[recipe结果交付件表](./docs/zh/recipe_output_format_introduct.md)文档。

### 使用样例
#### 最简使用
```bash
# 只传入cluster_data性能数据文件夹，输入cluster_time_summary分析能力，在cluster_data输入文件夹下生成cluster_analysis_output文件夹，保存分析结果信息
msprof-analyze -m cluster_time_summary -d ./cluster_data
```

#### 分析能力为all设置下使用
```bash
# 可以输入-m参数为all，当前输出step_trace_time/通信矩阵/通信耗时交付件
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

> 对比规则维度、参数说明及报告解读，请参考 [msprof-analyze compare](./docs/zh/compare_tool_instruct.md)子功能介绍文档。

#### 专家建议（advisor）子功能
自动分析性能数据，识别算子执行效率、下发调度、集群通信等潜在瓶颈，并生成分级优化建议，助力快速定位问题。

```bash
# 基础用法
msprof-analyze advisor all -d ./prof_data -o ./advisor_output
```

分析完成后，在执行终端打印关键问题与优化建议，并生成
* `mstt_advisor_{timestamp}.html`按重要程度标记的优化建议
* `mstt_advisor_{timestamp}.xlsx`问题综述与详细的分析信息

> 详细分析规则、参数配置及结果解读，请参考 [msprof-analyze advisor](./docs/zh/advisor_instruct.md)子功能介绍文档。

## 扩展功能
### 自定义开发指导
用户可自定义一套性能数据的分析规则，需要详细了解性能分析的开发人员，具体开发指导请参见[自定义分析能力开发指导](./docs/zh/custom_analysis_guide.md)。


## 附录
### 采集profiling性能数据指导
  * msprof 场景：参见“性能数据采集 > [msprof采集通用命令](https://www.hiascend.com/document/detail/zh/mindstudio/81RC1/T&ITools/Profiling/atlasprofiling_16_0008.html)”。
  * PyTorch 场景：参见“性能数据采集 > [PyTorch](https://www.hiascend.com/document/detail/zh/mindstudio/81RC1/msquickstart/atlasquick_train_0018.html)”。
  * MindSpore 场景：参见“性能数据采集 > [MindSpore](https://www.hiascend.com/document/detail/zh/mindstudio/81RC1/msquickstart/atlasquick_train_0017.html)”。
  * msMonitor 场景：参见“msmonitor > [msmonitor](https://gitcode.com/Ascend/msmonitor)”。

### 发布程序包下载链接
| profiler版本 | 发布日期       | 下载链接                                                                                                                                                       | 校验码                                                       |
|------------|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------| ------------------------------------------------------------ |
| 8.2.0a2    | 2025-10-13 | [msprof_analyze-8.2.0a2-py3-none-any.whl](https://ptdbg.obs.cn-north-4.myhuaweicloud.com/profiler/package/8.2.0a2/msprof_analyze-8.2.0a2-py3-none-any.whl) | f16e08fc4b342a2d2229d173166fe49d70d9185fe30d9159d5e27f88f3853bf8 |
| 8.2.0a1    | 2025-08-26 | [msprof_analyze-8.2.0a1-py3-none-any.whl](https://ptdbg.obs.cn-north-4.myhuaweicloud.com/profiler/package/8.2.0a1/msprof_analyze-8.2.0a1-py3-none-any.whl) | ee3e9944d205300af925d8f482da2c2cf00536196445d0652b17621303d76586 |
| 8.1.0      | 2025-07-30 | [msprof_analyze-8.1.0-py3-none-any.whl](https://ptdbg.obs.cn-north-4.myhuaweicloud.com/profiler/package/8.1.0/msprof_analyze-8.1.0-py3-none-any.whl)       | 064f68ff22c88d91d8ec8c47045567d030d1f9774169811c618c06451ef697e4 |
| 2.0.2      | 2025-03-31 | [msprof_analyze-2.0.2-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/2.0.2/msprof_analyze-2.0.2-py3-none-any.whl)                  | 4227ff628187297b2f3bc14b9dd3a8765833ed25d527f750bc266a8d29f86935 |
| 2.0.1      | 2025-02-28 | [msprof_analyze-2.0.1-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/2.0.1/msprof_analyze-2.0.1-py3-none-any.whl)                  | 82dfe2c779dbab9015f61d36ea0c32d832b6d182454b3f7db68e6c0ed49c0423 |
| 2.0.0      | 2025-02-08 | [msprof_analyze-2.0.0-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/2.0.0/msprof_analyze-2.0.0-py3-none-any.whl)                  | 8e44e5f3e7681c377bb2657a600ad9841d3bed11061ddd7844c30e8a97242101 |
| 1.3.4      | 2025-01-20 | [msprof_analyze-1.3.4-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.3.4/msprof_analyze-1.3.4-py3-none-any.whl)                  | 8de92188d1a97105fb14cadcb0875ccd5f66629ee3bb25f37178da1906f4cce2 |
| 1.3.3      | 2024-12-26 | [msprof_analyze-1.3.3-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.3.3/msprof_analyze-1.3.3-py3-none-any.whl)                  | 27676f2eee636bd0c65243f81e292c7f9d30d7f985c772ac9cbaf10b54d3584e |
| 1.3.2      | 2024-12-20 | [msprof_analyze-1.3.2-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.3.2/msprof_analyze-1.3.2-py3-none-any.whl)                  | ceb227e751ec3a204135be13801f1deee6a66c347f1bb3cdaef596872874df06 |
| 1.3.1      | 2024-12-04 | [msprof_analyze-1.3.1-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.3.1/msprof_analyze-1.3.1-py3-none-any.whl)                  | eae5548804314110a649caae537f2c63320fc70ec41ce1167f67c1d674d8798e |
| 1.3.0      | 2024-10-12 | [msprof_analyze-1.3.0-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.3.0/msprof_analyze-1.3.0-py3-none-any.whl)                  | 8b09758c6b5181bb656a95857c32852f898c370e7f1041e5a08e4f10d5004d48 |
| 1.2.5      | 2024-09-25 | [msprof_analyze-1.2.5-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.2.5/msprof_analyze-1.2.5-py3-none-any.whl)                  | aea8ae8deac07b5b4980bd2240da27d0eec93b9ace9ea9eb2e3a05ae9072018b |
| 1.2.4      | 2024-09-19 | [msprof_analyze-1.2.4-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.2.4/msprof_analyze-1.2.4-py3-none-any.whl)                  | 7c392e72c3347c4034fd3fdfcccb1f7936c24d9c3eb217e2cc05bae1347e5ab7 |
| 1.2.3      | 2024-08-29 | [msprof_analyze-1.2.3-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.2.3/msprof_analyze-1.2.3-py3-none-any.whl)                  | 354a55747f64ba1ec6ee6fe0f05a53e84e1b403ee0341ec40cc216dd25fda14c |
| 1.2.2      | 2024-08-23 | [msprof_analyze-1.2.2-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.2.2/msprof_analyze-1.2.2-py3-none-any.whl)                  | ed92a8e4eaf5ada8a2b4079072ec0cc42501b1b1f2eb00c8fdcb077fecb4ae02 |
| 1.2.1      | 2024-08-14 | [msprof_analyze-1.2.1-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.2.1/msprof_analyze-1.2.1-py3-none-any.whl)                  | 7acd477417bfb3ea29029dadf175d019ad3212403b7e11dc1f87e84c2412c078 |
| 1.2.0      | 2024-07-25 | [msprof_analyze-1.2.0-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.2.0/msprof_analyze-1.2.0-py3-none-any.whl)                  | 6a4366e3beca40b4a8305080e6e441d6ecafb5c05489e5905ac0265787555f37 |
| 1.1.2      | 2024-07-12 | [msprof_analyze-1.1.2-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.1.2/msprof_analyze-1.1.2-py3-none-any.whl)                  | af62125b1f9348bf491364e03af712fc6d0282ccee3fb07458bc9bbef82dacc6 |
| 1.1.1      | 2024-06-20 | [msprof_analyze-1.1.1-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.1.1/msprof_analyze-1.1.1-py3-none-any.whl)                  | 76aad967a3823151421153d368d4d2f8e5cfbcb356033575e0b8ec5acea8e5e4 |
| 1.1.0      | 2024-05-28 | [msprof_analyze-1.1.0-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.1.0/msprof_analyze-1.1.0-py3-none-any.whl)                  | b339f70e7d1e45e81f289332ca64990a744d0e7ce6fdd84a8d82e814fa400698 |
| 1.0        | 2024-05-10 | [msprof_analyze-1.0-py3-none-any.whl](https://ptdbg.obs.myhuaweicloud.com/profiler/package/1.0/msprof_analyze-1.0-py3-none-any.whl)                        | 95b2f41c8c8e8afe4887b738c8cababcb4f412e1874483b6adae4a025fcbb7d4 |


## FAQ
暂无

## License

MindStudio-Profiler-Analyze工具使用许可证，详见[LICENSE](./LICENSE)文件。

## ❗免责声明

本工具为开发调测工具，不应在生产环境使用。

## 建议与交流

欢迎大家为社区做贡献。如果有任何疑问或建议，请提交issues，我们会尽快回复。感谢您的支持。

## 致谢

🔎 msprof-analyze 由华为公司的下列部门联合贡献 ：

华为公司：

- 昇腾计算MindStudio开发部
- 华为云昇腾云服务
- 昇腾计算生态使能部
- 2012网络实验室

感谢来自社区的每一个PR，欢迎贡献 msprof-analyze！