# GE自动融合性能对比

## 简介

GE自动融合性能对比，是指通过开启自动融合开关，导出TensorFlow模型的datadump数据与Build图，调用图执行接口，采集自动融合开关前后的性能数据，完成性能对比。

## 使用前准备

**约束**

- 仅支持TensorFlow框架

**环境准备**

- 硬件环境请参见《[昇腾产品形态说明](https://www.hiascend.com/document/detail/zh/AscendFAQ/ProduTech/productform/hardwaredesc_0001.html)》。

- 软件环境请参见《[CANN 软件安装指南](https://www.hiascend.com/document/detail/zh/canncommercial/83RC1/softwareinst/instg/instg_quick.html?Mode=PmIns&InstallType=local&OS=openEuler&Software=cannToolKit)》安装配套版本的CANN Toolkit开发套件包和ops算子包并配置CANN环境变量。

- 依赖torch_npu>=7.1.RC1，使用前请确认已安装。

- 执行构建脚本：

    ```shell
    git clone https://gitcode.com/Ascend/msprof-analyze
    cd msprof-analyze
    git checkout pre-research
    # 安装依赖
    pip install -r requirements.txt
    # 构建图执行的so
    cd misc/autofuse_performance_comparison
    bash build.sh
    ```
  脚本执行成功后，autofuse_performance_comparison/lib64路径下生成ExecuteGraph_C.so。

**数据准备**
1. 开启自动融合开关。
    ```shell
    export AUTOFUSE_FLAGS="--enable_autofuse=true"
    ```
    自动融合开关的更多介绍，请参见《[AutoFuse使能方式](https://www.hiascend.com/document/detail/zh/canncommercial/83RC1/graph/autofuse/autofuse_1_0004.html)》。


2. TensorFlow模型运行时开启datadump和自动融合，获取datadump数据和Build图。

- 开启datadump，请参见《[准备NPU侧dump数据和计算图文件](https://www.hiascend.com/document/detail/zh/canncommercial/83RC1/devaids/ModelAccuracyAnalyzer/atlasaccuracy_16_0007.html)》。

- 开启graphdump，可设置以下几个环境变量：

    ```shell
    export PRINT_MODEL=1
    export DUMP_GE_GRAPH=1
    export DUMP_GRAPH_LEVEL=1
    export DUMP_GRAPH_PATH=<dump_path>
    ```
    关于这些环境变量的具体含义，请参见《[dump图文件环境变量](https://www.hiascend.com/document/detail/zh/canncommercial/83RC1/maintenref/envvar/envref_07_0001.html)》。

3. 数据处理。

- dump数据文件转换成npy文件，可以得到对应融合算子的输入和输出，请参见《[dump数据文件Format转换](https://www.hiascend.com/document/detail/zh/canncommercial/83RC1/devaids/ModelAccuracyAnalyzer/atlasaccuracy_16_0054.html)》。

    例如AscBackend.autofuse_pointwise_0_Abs_Add.1.59.1767681027598365转换为npy文件可以得到AscBackend.autofuse_pointwise_0_Abs_Add.1.59.1767681027598365.input.0.npy、AscBackend.autofuse_pointwise_0_Abs_Add.1.59.1767681027598365.input.1.npy和AscBackend.autofuse_pointwise_0_Abs_Add.1.59.1767681027598365.output.0.npy。


- 整图txt文件（例如ge_proto_00000094_graph_1_Build.txt）转换为json格式。
    ```shell
    # 需要source CANN的环境变量
    atc --mode=5 --om=<graph_txt_file_path> --json=<graph_json_file_path>
    ```

## GE自动融合性能对比

**功能说明**

无需执行整个模型，直接调用图执行接口，并采集自动融合开关前后的性能数据，完成性能对比。

**注意事项**

无

**命令格式**


```bash
cd misc/autofuse_performance_comparison/autofuse_core
python3 autofuse_performance_comparison.py -f <whole_graph> -d <subgraph_dir> -m <dump_path> [-o <output>]
```


**参数说明**


| 参数 | 可选/必选 | 说明 |
| ----- | ----- | ----- |
| -f<br>--whole_graph  | 必选 | json格式的整图文件，例如`ge_proto_00000094_graph_1_Build.json`。 |
| -d<br>--subgraph_dir | 必选 | 存放所有txt格式子图文件（例如：autofuse_pointwise_0_Abs_Add.txt）的目录。 |
| -m <br>--dump_path   | 可选 | 存放所有融合算子npy格式的dump数据的目录。 |
| -o <br>--output      | 可选 | 该目录下生成两个子目录autofuse_enabled和autofuse_disabled，分别保存自动融合开关开启和关闭时采集的性能数据，默认为当前路径。用户一般无需关注这个性能数据，只需要查看终端的输出结果即可。 |

**使用示例**

```python
python3 autofuse_performance_comparison.py -f /data/graph_path/ge_proto_00000094_graph_1_Build.json -d /data/graph_path -m /data/dump_path
```

**输出说明**

生成autofuse_performance_comparison_result_{timestamp}.xlsx，详见[输出结果文件说明](#输出结果文件说明)。

## 输出结果文件说明

GE自动融合性能对比的输出结果文件autofuse_performance_comparison_result_{timestamp}.xlsx中呈现。内容如图所示：
![GE自动融合性能对比结果](../../docs/zh/figures/autofuse_performance_comparison.png)

