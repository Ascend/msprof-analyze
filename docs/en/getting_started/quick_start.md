# Quick Start

This tutorial is designed to help you quickly get started with MindStudio Profiler Analyze (`msprof-analyze`). It provides a minimal example covering the end-to-end workflow: collecting profile data, performing `advisor` analysis, and viewing the results.

## Step 1: Installing the Tool

```bash
pip install -U msprof-analyze
```

For more installation methods, see [MindStudio Profiler Analyze Installation Guide](./install_guide.md).

## Step 2: Generating Sample Profile Data

`msprof-analyze` requires an input directory containing the collected profile data. For your first use of the tool, you are advised to use the [train_sample.py](#appendix) script provided in the appendix to generate sample Ascend PyTorch Profiler data. This script uses `torch_npu.profiler` to collect profile data from a ResNet-50 training task and outputs the results to the `./result` directory.

```bash
python train_sample.py
```

After the script is executed, the terminal displays information similar to the following:

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

After the execution is complete, a directory ending in `ascend_pt` is generated. This is the profile data directory required for subsequent `advisor` analysis. The example directory structure is as follows:

```text
msprof_3978075_20260324035119296_ascend_pt/
├── ASCEND_PROFILER_OUTPUT
├── FRAMEWORK
├── logs
└── PROF_000001_20260324035119333_03978075KFFEDFAM
```

## Step 3: Performing `advisor` Analysis

Perform a complete `advisor` analysis:

```bash
# Replace {..._ascend_pt} with the name of the actual profile data directory.
msprof-analyze advisor all \
  -d ./result/{..._ascend_pt} \
  -o ./advisor_output
```

Specifically:

- `-d`: specifies the profile data directory.
- `-o` specifies the analysis results output directory.
- `advisor all` analyzes computation, scheduling, communication, and overall bottlenecks simultaneously.

## Step 4: Viewing the Analysis Results

After the analysis is complete, the following result files are generated in the `./advisor_output` directory:

- `mstt_advisor_<timestamp>.html`
- `log/mstt_advisor_<timestamp>.xlsx`

Specifically:

- The HTML file is ideal for a quick overview of conclusions and optimization suggestions.
- The XLSX file is ideal for viewing detailed data.

You can open the HTML report to view the analysis results. The following figure shows an example of the report page. In this example, the tool identifies high data loading latency in the DataLoader as the top priority and provides the corresponding optimization suggestions.

![advisor result example](../figures/quick_start_dataloader.png)

## Related Links

- [advisor](../user_guide/advisor_instruct.md)
- [compare](../user_guide/compare_tool_instruct.md)
- [cluster_analyse](../user_guide/cluster_analyse_instruct.md)
- [Advanced Features](../advanced_features/README.md)

## Appendix

`train_sample.py`: a ResNet-50 training sample that uses `torch_npu.profiler` to collect profile data.

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
