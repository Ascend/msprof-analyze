# 性能数据模型结构拆解

## 简介

性能数据模型结构拆解（module_statistic）是msprof-analyze提供的针对PyTorch模型自动解析模型层级结构的分析能力，帮助精准定位性能瓶颈，为模型优化提供关键洞察。该分析能力提供：

* 模型结构拆解：自动提取并展示模型的层次化结构，以及模型中的算子调用顺序。
* 算子与Kernel映射：框架层算子下与NPU上执行Kernel的映射关系。
* 算子MFU计算：自动计算MatMul、FlashAttention等核心算子的算力利用率（MFU）。
* 性能分析：精确统计并输出Device侧Kernel的执行耗时。

## 使用前准备

**环境准备**

完成msprof_analyze工具安装，具体请参见《[msprof-analyze工具安装指南](./install_guide.md)》。

**数据准备**

1. 添加模型层级mstx打点

    在模型代码中调用`torch_npu.npu.mstx.range_start/range_end`性能打点接口，需重写PyTorch中的nn.Module调用逻辑。

2. 添加FlashAttention算子mstx打点（可选）

    如需呈现FlashAttention算子的MFU，需要调用`torch_npu.npu.mstx.mark`性能打点接口以记录`torch_npu.npu_fusion_attention`与`torch.nn.functional.scaled_dot_product_attention` 函数的部分入参。

3. 配置并采集 Profiling 数据

   * 使用`torch_npu.profiler`接口采集性能数据。
   * 在`torch_npu.profiler._ExperimentalConfig`设置`mstx=True`，开启打点事件采集（在旧版本中对应的参数为`msprof_tx=True`）。
   * 在`torch_npu.profiler._ExperimentalConfig`设置`export_type`导出类型，需要包含Db。
   * 在`torch_npu.profiler._ExperimentalConfig`设置`profiler_level`采集等级，若需计算MFU请将该等级设置为`level1`及以上。
   * 性能数据落盘在`torch_npu.profiler.tensorboard_trace_handler`接口指定的路径下，将该路径下的数据作为msprof-analyze cluster的输入数据。

完整样例代码，详见[性能数据采集样例代码](#性能数据采集样例代码)。

## 模型结构拆解

**功能说明**  

将采集到的带有模型结构mstx打点的数据，执行msprof-analyze工具分析操作。

**命令格式**  

```bash
msprof-analyze -m module_statistic -d ./result --export_type text
```

**参数说明**

| 参数 | 可选/必选 | 说明                              |
| ---- | --------- |---------------------------------|
| -m   | 必选      | 设置为module_statistic 使能模型结构拆解能力。 |
| -d   | 必选      | 集群性能数据文件夹路径。                    |
| -o   | 可选      | 指定输出文件路径。                       |
| --export_type   | 可选      | 指定输出文件类型，可选db或text。             |

更多参数详细介绍请参见msprof-analyze的[参数说明](./README.md#参数说明)。

**输出说明**  

* 输出结果体现模型层级，算子调用顺序，NPU上执行的Kernel以及统计时间。
* `export_type`设置为`text`时，每张卡生成独立的module_statistic_{rank_id}.xlsx文件，如下图所示：  
![vllm_module_statistic](./figures/vllm_module_statistic.png)

* `export_type`设置为`db`时，结果统一保存到 cluster_analysis.db 的 ModuleStatistic，字段说明如下：  

  | 字段名称                    | 说明                                                                                      |
  |-------------------------|-----------------------------------------------------------------------------------------|
  | parentModule            | 上层Module名称，TEXT类型                                                                       |
  | module                  | 最底层Module名称，TEXT类型                                                                      |
  | opName                  | 框架侧算子名称，同一module下，算子按照调用顺序排列，TEXT类型                                                     |
  | kernelList              | 框架侧算子下发到Device侧执行Kernel的序列，TEXT类型                                                       |
  | totalKernelDuration(ns) | 框架侧算子对应Device侧Kernel运行总时间，单位纳秒（ns），REAL类型                                               |
  | avgKernelDuration(ns)       | 框架侧算子对应Device侧Kernel平均运行时间，单位纳秒（ns），REAL类型                                              |
  | opCount                 | 框架侧算子在采集周期内运行的次数，INTEGER类型                                                              |
  | rankID                  | 集群场景的节点识别ID，集群场景下设备的唯一标识，INTEGER类型                                                      |
  | avgMFU                  | Device侧Kernel的MFU（平均算力利用率），TEXT类型 <br> 当前仅支持对MatMul和FlashAttention两类算子进行计算，若无相关数据则该列不输出 |

## 附录

### 性能数据采集样例代码

对于复杂模型结构，建议采用选择性打点策略以降低性能开销，核心性能打点实现代码如下：

```python
original_call = nn.Module.__call__

module_list = ["Attention", "QKVParallelLinear"]
def custom_call(self, *args, **kwargs):
    module_name = self.__class__.__name__
    if module_name not in module_list:
        return original_call(self, *args, **kwargs)
    mstx_id = torch_npu.npu.mstx.range_start(module_name, domain="Module")
    tmp = original_call(self, *args, **kwargs)
    torch_npu.npu.mstx.range_end(mstx_id, domain="Module")
    return tmp

nn.Module.__call__ = custom_call
```

（可选）对FlashAttention算子的调用接口增加mstx打点功能，以便自动测算该类型算子的MFU，打点代码如下：

```python
import json
import torch
import torch_npu

# torch_npu.npu_fusion_attention接口调用前添加mark打点
original_npu_fusion_attention = torch_npu.npu_fusion_attention
def custom_npu_fusion_attention(*args, **kwargs):
    info = {
        "input_layout": kwargs.get('input_layout'),
        "sparse_mode": kwargs.get('sparse_mode', 0),
        "actual_seq_qlen": kwargs.get('actual_seq_qlen', []),
        "actual_seq_kvlen": kwargs.get('actual_seq_kvlen', []),
    }
    torch_npu.npu.mstx.mark(message=json.dumps(info), domain='flash_attn_args')
    tmp = original_npu_fusion_attention(*args, **kwargs)
    return tmp
torch_npu.npu_fusion_attention = custom_npu_fusion_attention

# torch.nn.functional.scaled_dot_product_attention接口调用前添加mark打点
original_scaled_dot_product_attention = torch.nn.functional.scaled_dot_product_attention
def custom_origin_scaled_dot_product_attention(*args, **kwargs):
    info = {
        "is_causal": kwargs.get('is_causal', False)
    }
    torch_npu.npu.mstx.mark(message=json.dumps(info), domain='flash_attn_args')
    tmp = original_scaled_dot_product_attention(*args, **kwargs)
    return tmp
torch.nn.functional.scaled_dot_product_attention = custom_origin_scaled_dot_product_attention
```

完整样例代码如下：

```python
import random
import torch
import torch_npu
import torch.nn as nn
import torch.optim as optim


original_call = nn.Module.__call__

def custom_call(self, *args, **kwargs):
    """自定义nn.Module调用方法，添加MSTX打点"""
    module_name = self.__class__.__name__
    mstx_id = torch_npu.npu.mstx.range_start(module_name, domain="Module")
    tmp = original_call(self, *args, **kwargs)
    torch_npu.npu.mstx.range_end(mstx_id, domain="Module")
    return tmp
    
# 替换默认调用方法
nn.Module.__call__ = custom_call

class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def _norm(self, x):
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)

    def forward(self, x):
        output = self._norm(x.float()).type_as(x)
        return output * self.weight


class ToyModel(nn.Module):
    def __init__(self, D_in, H, D_out):
        super(ToyModel, self).__init__()
        self.input_linear = torch.nn.Linear(D_in, H)
        self.middle_linear = torch.nn.Linear(H, H)
        self.output_linear = torch.nn.Linear(H, D_out)
        self.rms_norm = RMSNorm(D_out)

    def forward(self, x):
        h_relu = self.input_linear(x).clamp(min=0)
        for i in range(3):
            h_relu = self.middle_linear(h_relu).clamp(min=random.random())
        y_pred = self.output_linear(h_relu)
        y_pred = self.rms_norm(y_pred)
        return y_pred


def train():
    N, D_in, H, D_out = 256, 1024, 4096, 64
    torch.npu.set_device(6)
    input_data = torch.randn(N, D_in).npu()
    labels = torch.randn(N, D_out).npu()
    model = ToyModel(D_in, H, D_out).npu()

    loss_fn = nn.MSELoss()
    optimizer = optim.SGD(model.parameters(), lr=0.001)

    experimental_config = torch_npu.profiler._ExperimentalConfig(
        aic_metrics=torch_npu.profiler.AiCMetrics.PipeUtilization,
        profiler_level=torch_npu.profiler.ProfilerLevel.Level2,
        l2_cache=False,
        mstx=True,  # 打开mstx采集，原参数名为msprof_tx
        data_simplification=False,
        export_type=[
            torch_npu.profiler.ExportType.Text,
            torch_npu.profiler.ExportType.Db
        ],  # 导出类型中必须要包含db
    )

    prof = torch_npu.profiler.profile(
        activities=[torch_npu.profiler.ProfilerActivity.CPU, torch_npu.profiler.ProfilerActivity.NPU],
        schedule=torch_npu.profiler.schedule(wait=1, warmup=1, active=3, repeat=1, skip_first=5),
        on_trace_ready=torch_npu.profiler.tensorboard_trace_handler("./result"),
        record_shapes=True,
        profile_memory=False,
        with_stack=False,
        with_flops=False,
        with_modules=True,
        experimental_config=experimental_config)
    prof.start()

    for i in range(12):
        optimizer.zero_grad()
        outputs = model(input_data)
        loss = loss_fn(outputs, labels)
        loss.backward()
        optimizer.step()
        prof.step()

    prof.stop()


if __name__ == "__main__":
    train()
```
