# 快速入门

本教程旨在帮助你快速上手 `msprof-analyze` 工具，提供一个最小示例，涵盖从采集性能数据、执行 advisor 分析到查看分析结果的完整流程。

## 1. 安装工具

```bash
pip install -U msprof-analyze
```

更多安装方式请参见 《[安装指南](../install_guide/msprof-analyze_install_guide.md)》。

安装完成后，执行如下命令确认工具已可用：

```bash
msprof-analyze --help
```

## 2. 生成样例 profiling 数据

`msprof-analyze` 需要输入 profiling 数据目录作为分析对象。如果您是首次使用，推荐使用附录中的 [train_sample.py](#6-附录) 快速生成 Ascend PyTorch Profiler 样例数据。

### 2.1 环境预检

#### 2.1.1 加载 CANN 环境

若尚未安装 CANN Toolkit 开发套件包和 ops 算子包，请先参考[CANN快速安装](https://www.hiascend.com/cann/download)。  
安装完成后，加载环境变量：  

```bash
# ${install_path} 为 CANN 软件的安装目录，默认为 /usr/local/Ascend/ascend-toolkit。
source ${install_path}/set_env.sh
```

执行完成后，可通过如下命令确认环境变量已生效：

```bash
echo $ASCEND_HOME_PATH
```

#### 2.1.2 确认 NPU 就绪

当前步骤确认以下环境配置：

- `PyTorch` 与 `torch_npu` 是否配套 
- NPU 设备状态

执行以下命令进行预检：

```bash
# 确认 torch、torch_npu 均已安装，版本是否配套
python -c "import torch; print(torch.__version__)"
python -c "import torch_npu; print(torch_npu.__version__)"

# 输出 True 表示当前 Python 环境可以识别 NPU
python -c "import torch; print(torch.npu.is_available())"
```

执行以下命令，返回 NPU 设备列表、健康状态和进程信息，检查 NPU 卡是否空闲，确认当前无其他任务运行。

```bash
npu-smi info
```

### 2.2 采集性能数据

执行以下命令，运行训练脚本并采集性能数据。[train_sample.py](#6-附录) 脚本在 NPU 上训练 ResNet50 模型（共 5 个 epoch），通过 torch_npu.profiler 自动采集性能数据，将 profiling 结果输出到 `./result` 目录。

```bash
python train_sample.py
```

**正常执行时的终端输出示例**  

```text
[INFO] Using device: npu:0
[Epoch 1/5] Average Loss: 2.5849
[Epoch 2/5] Average Loss: 2.5526
[Epoch 3/5] Average Loss: 2.2174
[Epoch 4/5] Average Loss: 2.0562
[2026-03-24 03:44:40] [INFO] [3956593] profiler.py: Start parsing profiling data in sync mode at: /home/result/msprof_3954534_20260324034427358_ascend_pt
[2026-03-24 03:44:49] [INFO] [3956641] profiler.py: CANN profiling data parsed in a total time of 0:00:08.090306
[2026-03-24 03:44:53] [INFO] [3956593] profiler.py: All profiling data parsed in a total time of 0:00:12.392744
[Epoch 5/5] Average Loss: 1.9166
```

**执行结果**  

脚本运行成功后，会生成一个以 `ascend_pt` 结尾的目录，该目录下的`ASCEND_PROFILER_OUTPUT` 文件夹中存放解析后的数据，例如：

```text
   /
├── ASCEND_PROFILER_OUTPUT
│   ├── analysis.db                  // 通信数据db文件
│   ├── ascend_pytorch_profiler_{Rank_ID}.db // 统一db文件，包含所有性能信息，与text（json、csv）信息相同
│   ├── kernel_details.csv           // 记录所有在NPU上执行的kernel性能信息
│   ├── op_statistic.csv             // AI Core/CPU 算子调用及耗时
│   ├── operator_details.csv         // 算子调用次数及耗时等统计信息
│   ├── step_trace_time.csv          // 计算、通信、调度时间统计值
│   ├── trace_view.json              // Chrome trace格式的timeline，记录了Pytorch->CANN->Device的算子耗时时序关系
│   └── ...
├── FRAMEWORK
└── PROF_000001_20260324035119333_03978075KFFEDFAM
```

> [!NOTE]
>
> 这个 `ascend_pt` 目录就是后续执行 `msprof-analyze` 时需要传入的 profiling 数据路径。

**常见问题排查**  
如果执行后没有生成以 ascend_pt 结尾的目录，请检查： 

- 训练脚本是否完整执行完毕（是否出现 All profiling data parsed 日志） 
- 当前目录是否具有写入权限 
- 终端是否提前报错退出（如 NPU 不可用、显存不足等）

如有报错，请根据错误信息优先检查环境预检步骤。

## 3. 运行 advisor 分析

执行一次完整的专家建议分析：

```bash
# 需要将 {..._ascend_pt} 替换为实际生成的 profiling 目录名称。
msprof-analyze advisor all \
  -d ./result/{..._ascend_pt} \
  -o ./advisor_output
```

参数说明如下：

| 参数 | 是否必选 | 说明 | 示例 |
| --- | --- | --- | --- |
| `advisor all` | 是 | 启动专家建议分析，同时分析计算、调度、通信和整体瓶颈。 | `msprof-analyze advisor all` |
| `-d` | 是 | 指定 profiling 数据目录，需要替换为实际生成的 `*_ascend_pt` 目录。 | `-d ./result/msprof_xxx_ascend_pt` |
| `-o` | 否 | 指定分析结果输出目录；未指定时，默认输出到执行命令所在的当前目录。 | `-o ./advisor_output` |

命令执行成功后，会在终端输出简要分析结果，并在输出目录中生成 `mstt_advisor_<timestamp>.html` 和 `log/mstt_advisor_<timestamp>.xlsx` 文件。

## 4. 查看分析结果

分析完成后，`./advisor_output` 目录下会生成以下结果文件：

- `mstt_advisor_<timestamp>.html`
- `log/mstt_advisor_<timestamp>.xlsx`

其中：

- HTML 文件适合快速浏览整体结论和优化建议。
- XLSX 文件适合进一步查看明细数据。

可以直接打开 HTML 报告查看结果。下面是一个报告页面示例：本次样例检测出了 dataloader 数据加载耗时问题，并将其标记为最高优先级，同时给出了相应的优化建议。

![advisor结果示意图](../figures/quick_start_dataloader.png)

查看报告时，建议按以下顺序阅读：

1. 查看报告首页的总体结论，确认是否存在高优先级性能问题。
2. 查看问题列表中的问题类型、优先级和优化建议。
3. 若需要定位明细数据，打开 `log/mstt_advisor_<timestamp>.xlsx`，结合报告中的模块名称和算子/API 信息进一步分析。
4. 根据报告建议修改训练脚本、数据加载方式或通信配置后，重新采集 profiling 数据并再次运行 `advisor` 验证优化效果。

## 5. 下一步阅读

- 《[专家建议](../user_guide/advisor_instruct.md)》
- 《[性能比对](../user_guide/compare_tool_instruct.md)》
- 《[集群分析](../user_guide/cluster_analyse_instruct.md)》
- 《[高级特性导航](../advanced_features/README.md)》

## 6. 附录

train_sample.py:  ResNet50 训练示例，使用 `torch_npu.profiler` 采集性能数据

```python
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.models as models
from torchvision.models import ResNet50_Weights
import torch_npu

class ResNet50:
    def __init__(self, num_classes=1000, device=None):
        # Automatically choose the device: NPU > CUDA > CPU
        if device is None:
            if hasattr(torch, 'npu') and torch.npu.is_available():
                self.device = torch.device("npu:0")
            else:
                self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        print(f"[INFO] Using device: {self.device}")

        # Load ResNet50 (with pretrained weights)
        self.model = models.resnet50(weights=ResNet50_Weights.IMAGENET1K_V1)
        if num_classes != 1000:
            self.model.fc = nn.Linear(self.model.fc.in_features, num_classes)
        self.model = self.model.to(self.device)

    def train(self, data_loader, epochs=5, lr=1e-4, freeze_backbone=False):
        """
        Simple training function.
        :param data_loader: torch.utils.data.DataLoader returning (images, labels)
        :param epochs: Number of epochs to train for
        :param lr: Learning rate
        :param freeze_backbone: Whether to freeze the ResNet backbone, only training the classification head
        """
        # Optionally freeze the backbone (useful for fine-tuning)
        if freeze_backbone:
            for param in self.model.parameters():
                param.requires_grad = False
            for param in self.model.fc.parameters():
                param.requires_grad = True

        # Optimize only parameters that require gradients
        params_to_optimize = [p for p in self.model.parameters() if p.requires_grad]
        optimizer = optim.Adam(params_to_optimize, lr=lr)
        criterion = nn.CrossEntropyLoss().to(self.device)

        self.model.train()

        # torch_npu.profiler experimental configs
        experimental_config = torch_npu.profiler._ExperimentalConfig(
            export_type=[
                torch_npu.profiler.ExportType.Text,
                torch_npu.profiler.ExportType.Db
                ],
            profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
            mstx=False,    
            mstx_domain_include=[],
            mstx_domain_exclude=[],
            aic_metrics=torch_npu.profiler.AiCMetrics.AiCoreNone,
            l2_cache=False,
            op_attr=False,
            data_simplification=True,
            record_op_args=False,
            gc_detect_threshold=None,
            host_sys=[],
            sys_io=False,
            sys_interconnection=False
        )

        with torch_npu.profiler.profile(
            activities=[
                torch_npu.profiler.ProfilerActivity.CPU,
                torch_npu.profiler.ProfilerActivity.NPU
                ],
            schedule=torch_npu.profiler.schedule(wait=0, warmup=1, active=3, repeat=1, skip_first=0),
            on_trace_ready=torch_npu.profiler.tensorboard_trace_handler("./result"),
            record_shapes=False,
            profile_memory=False,
            with_stack=False,
            with_modules=False,
            with_flops=False,
            experimental_config=experimental_config) as prof:
                for epoch in range(epochs):
                    total_loss = 0.0
                    for inputs, labels in data_loader:
                        inputs, labels = inputs.to(self.device), labels.to(self.device)

                        optimizer.zero_grad()
                        outputs = self.model(inputs)
                        loss = criterion(outputs, labels)
                        loss.backward()
                        optimizer.step()

                        total_loss += loss.item()

                    avg_loss = total_loss / len(data_loader)
                    print(f"[Epoch {epoch + 1}/{epochs}] Average Loss: {avg_loss:.4f}")
                    prof.step()

def train():
    trainer = ResNet50(num_classes=10)
    fake_images = torch.randn(80, 3, 224, 224)
    fake_labels = torch.randint(0, 10, (80,))
    dataset = torch.utils.data.TensorDataset(fake_images, fake_labels)
    loader = torch.utils.data.DataLoader(dataset, batch_size=8, shuffle=True)
    trainer.train(loader, epochs=5, lr=1e-3, freeze_backbone=True)

if __name__ == "__main__":
    train()

```
