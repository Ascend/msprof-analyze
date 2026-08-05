# inductor+triton融合算子性能对比

## 简介

inductor+triton融合算子性能对比，是指对inductor+triton框架自动生成的融合算子融合前后的性能进行对比。

## 使用前准备

**约束**

仅支持PyTorch框架。

**环境准备**

- 硬件环境请参见《[昇腾产品形态说明](https://www.hiascend.com/document/detail/zh/AscendFAQ/ProduTech/productform/hardwaredesc_0001.html)》。

- 软件环境请参见[CANN快速安装](https://www.hiascend.com/cann/download)安装配套版本的CANN Toolkit开发套件包和ops算子包并配置CANN环境变量。

- TorchNPU版本大于等于7.2.0，PyTorch仅支持v2.6.0、v2.7.1，具体安装方式请参见《[TorchNPU软件安装](https://gitcode.com/Ascend/pytorch/blob/v2.7.1-26.1.0/docs/zh/installation_guide/installation_description.md)》的“安装PyTorch > [方式一：离线安装（Whl）](https://gitcode.com/Ascend/pytorch/blob/v2.7.1-26.1.0/docs/zh/installation_guide/installation_via_binary_package.md)”章节。

- clone代码仓。

    ```shell
    git clone https://gitcode.com/Ascend/msprof-analyze -b 26.1.0
    ```

- 安装依赖

    ```bash
    cd msprof-analyze
    pip install -r requirements.txt
    ```

**数据准备**

1. 准备包含inductor场景的脚本或者模型。

    ```python
   import torch
   
    def add(a, b):
        return a + b
    inductor_add = torch.compile(add)
    ```

   上面示例代码定义了一个名为add的函数，然后使用torch.compile进行编译，后端默认是inductor。

2. 通过配置环境变量dump fx图，作为inductor+triton融合算子性能对比的输入。

    ```shell
    export TORCHINDUCTOR_FX_GRAPH_CACHE=0  # 关闭fx graph cache。
    export INDUCTOR_ASCEND_DUMP_FX_GRAPH=1  # 开启dump fx图。
    export INDUCTOR_ASCEND_FX_GRAPH_CACHE=<dump_path>  # 配置fx图dump的路径。
    ```

3. 运行用户程序。

    程序运行结束后，fx图保存在INDUCTOR_ASCEND_FX_GRAPH_CACHE设置的路径下。

## 功能介绍

**功能说明**

对inductor+triton框架自动生成的融合算子融合前后的性能进行对比。该功能通过inductor_triton_performance_comparison.py脚本实现，该脚本存放路径为：`msprof-analyze/misc/inductor_triton_performance_comparison`。

**注意事项**

无

**命令格式**

```shell
python3 inductor_triton_performance_comparison.py -d <fx_graph_path> [-o <output_path>]
```

**参数说明**

| 参数 | 可选/必选 | 说明 |
| ----- | ----- | ----- |
| -d<br>--fx_graph_path | 必选 | fx图dump的路径。 |
| -o<br>--output_path  | 可选 | 该目录下生成一个子目录inductor_triton，保存采集到的性能数据，默认为当前路径。用户一般无需关注这个性能数据，只需要查看[输出结果](#输出结果文件说明)即可。 |

**使用示例**

完成使用前准备后，执行如下命令。

```shell
cd misc/inductor_triton_performance_comparison
python3 inductor_triton_performance_comparison.py -d /data/fx_dump
```

**输出说明**

inductor_triton_performance_comparison.py脚本执行完成后，在-o参数指定的路径下生成inductor_triton_performance_comparison_result_{timestamp}.xlsx文件，文件详细介绍请参见[输出结果文件说明](#输出结果文件说明)。

## 输出结果文件说明

性能对比的输出结果在inductor_triton_performance_comparison_result_{timestamp}.xlsx中呈现。内容如图所示：

![性能对比结果](../../docs/zh/figures/inductor_triton_performance_comparison.png)

**表头字段说明**

| 字段        | 说明                            |
| --------- |-------------------------------|
| Triton Op | inductor+triton框架自动生成的融合算子名称。 |
| Triton Op Duration(us) | 执行耗时，单位us。                    |
| Original Op Duration(us) | 融合前算子及其耗时，按照耗时从高到低排序。         |
| Original Op Total Duration(us)    | 融合前算子总耗时，单位us。                |
| Duration Diff Ratio | 融合后算子耗时占融合前算子总耗时的百分比。         |

**输出结果分析**

- 展示融合前后算子及其耗时。
- 融合算子耗时占融合前算子总耗时的百分比小于100%，则认为融合算子性能提升，反之则认为融合算子性能下降。
