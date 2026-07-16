# msprof-analyze 快速入门

<br>

## 1. 概述

msprof-analyze 是面向昇腾 AI 处理器性能数据的自动分析工具。本文以一次完整的性能诊断为例，介绍环境准备、性能数据采集、Advisor 分析和报告查看的基本流程。

**体验地图（核心操作约需 10 分钟）**

| 步骤 | 环节 | 核心工具 | 参考操作耗时 | 建议原理学习耗时 |
| :---: | :--- | :--- |:------:| :---: |
| **1** | **环境准备** | CANN 容器环境 | 5 分钟 | 5 分钟 |
| **2** | **性能数据采集** | Ascend PyTorch Profiler | 2 分钟 | 10 分钟 |
| **3** | **自动分析与报告查看** | msprof-analyze Advisor | 3 分钟 | 10 分钟 |

## 2. 操作步骤

### 2.1 环境准备（必做）

🛑 **本节为强制前置步骤！跳过本节可能导致后续多项操作失败。**

本教程**仅支持**在标准化 CANN 容器中执行，不支持直接在裸机、虚拟机或其他非标准容器环境中执行。

#### 2.1.1 前置条件

开始前，请确认服务器满足以下要求：

| 项目 | 要求 | 验证方法 |
| --- | --- | --- |
| **硬件算力** | Linux 服务器配备至少 1 张 NPU 卡，驱动与固件已安装 | 执行 `npu-smi info`，确认 NPU 卡状态正常 |
| **容器运行** | 已安装并运行 Docker（建议版本 ≥ 18.0） | 执行 `docker ps`，无报错即表示服务正常启动 |
| **脚本执行** | 宿主机已安装 Python 3 | 在宿主机执行 `python3 -V`，有版本信息输出即表示已安装 |
| **网络通信** | 已安装 curl（任意版本） | 执行 `curl -V`，有版本信息输出即表示已安装 |

> 👉 确认前置条件满足后，若环境具备公网访问能力，本章后续命令可全程直接 **Copy/Paste** 执行，无需手动输入或拼接，以避免因输入错误导致命令执行失败。

#### 2.1.2 宿主机：自动识别并配置镜像环境变量

在宿主机执行以下命令（本命令做了三件事：① 读取 NPU PCI ID → ② 匹配镜像版本 → ③ 写入环境变量供后续流程使用）：

```bash
source /dev/stdin <<< "$(dev_id=$(lspci -n -D | grep -o '19e5:d[0-9a-f]\{3\}' | head -n1 | cut -d: -f2); case "$dev_id" in 'd500' ) echo "export MY_STUDY_VAR_CANN_IMAGE=swr.cn-south-1.myhuaweicloud.com/ascendhub/cann:9.0.0-310p-openeuler24.03-py3.11-devel; export MY_CHIP_NAME=310P";; 'd802' ) echo "export MY_STUDY_VAR_CANN_IMAGE=swr.cn-south-1.myhuaweicloud.com/ascendhub/cann:9.0.0-910b-openeuler24.03-py3.11-devel; export MY_CHIP_NAME=910B";; 'd803' ) echo "export MY_STUDY_VAR_CANN_IMAGE=swr.cn-south-1.myhuaweicloud.com/ascendhub/cann:9.0.0-a3-openeuler24.03-py3.11-devel; export MY_CHIP_NAME=A3";; 'd806' ) echo "export MY_STUDY_VAR_CANN_IMAGE=swr.cn-south-1.myhuaweicloud.com/ascendhub/cann:9.0.0-950-openeuler24.03-py3.11-devel; export MY_CHIP_NAME=950";; * ) echo "unset MY_STUDY_VAR_CANN_IMAGE MY_CHIP_NAME; echo >&2; echo -e '\033[31m[FAIL] Get device ID: $dev_id. Learning is not supported in the current environment.\033[0m' >&2";; esac)"
[ -n "$MY_STUDY_VAR_CANN_IMAGE" ] && echo -e "\e[32m[PASS] Successfully identified chip [$MY_CHIP_NAME] and auto-selected image:\n    $MY_STUDY_VAR_CANN_IMAGE\e[0m"
```

> [!NOTE]说明
>
> **命令原理**  
> 通过 `lspci` 获取 NPU 的 PCI ID，自动匹配 CANN 官方镜像，并将镜像地址赋给环境变量 `MY_STUDY_VAR_CANN_IMAGE`，供后续使用。  
> 所有镜像均来自华为云 AscendHub 上发布的 CANN 官方镜像。如需了解镜像详情，请参阅 [CANN 官方镜像仓库](https://www.hiascend.com/developer/ascendhub/detail/17da20d1c2b6493cb38765adeba85884)。

若命令执行后输出 `[PASS]`，则表示执行成功；若输出 `[FAIL]`，可能原因如下：

1. 硬件不在本教程支持范围内：本学习环境仅支持昇腾 310P、A2、A3 及 950 系列产品，请切换至兼容的硬件环境后重试；
2. 底层环境异常：未安装 `lspci`，或当前用户无法通过 `lspci -n -D` 查询 NPU PCI ID，请联系环境管理员确认底层环境。

#### 2.1.3 宿主机：拉取镜像

在宿主机执行：

```bash
docker pull ${MY_STUDY_VAR_CANN_IMAGE}
```

若因处于企业内网导致拉取失败，请参考 [第 3.1 节](#31-docker-镜像在隔离内网的获取方法) 的解决方案。

#### 2.1.4 宿主机：下载容器启动脚本

在宿主机执行：

```bash
cd ~ && curl -fLO --retry 3 https://inst.obs.cn-north-4.myhuaweicloud.com/env/ctr_in.py && chmod +x ctr_in.py
```

若因网络限制无法下载，请参考 [第 3.2 节](#32-传输容器启动脚本) 的解决方案。

#### 2.1.5 宿主机：启动容器

在宿主机执行以下命令，并根据终端提示确认容器创建信息：

```bash
~/ctr_in.py ${MY_STUDY_VAR_CANN_IMAGE}
```

**预期结果**：终端进入类似以下 root Shell 提示符，表示容器已成功启动：

```text
[root@xxxxxx ~]#
```

若提示错误或出现容器选择界面，请返回 [第 2.1.2 节](#212-宿主机自动识别并配置镜像环境变量)，确认命令输出 `[PASS]`，再重新启动容器。

#### 2.1.6 容器内：安装 Python 依赖和 msprof-analyze

在容器内执行以下命令：

```bash
pip3 install networkx==3.6.1 pillow==12.2.0
pip3 install https://inst.obs.cn-north-4.myhuaweicloud.com/env/mirror/$(arch)/download.pytorch.org/whl/cpu/torch-2.7.1%2Bcpu-cp311-cp311-manylinux_2_28_$(arch).whl
pip3 install torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cpu
pip3 install https://gitcode.com/Ascend/pytorch/releases/download/v26.0.0-pytorch2.7.1/torch_npu-2.7.1.post4-cp311-cp311-manylinux_2_28_$(arch).whl
pip3 install -U msprof-analyze
```

若因处于企业内网导致安装失败，请参考 [第 3.3 节](#33-离线安装-python-依赖和-msprof-analyze) 的解决方案。

#### 2.1.7 容器内：验证环境是否安装正确

安装完成后执行环境检查命令：

```bash
python3 -c 'import torch, torch_npu, torchvision; assert torch.npu.is_available(), "NPU is unavailable"; print("PyTorch:", torch.__version__)' && msprof-analyze --help >/dev/null && echo -e "\e[32m[PASS] NPU environment and msprof-analyze check passed.\e[0m"
```

若显示 `[PASS]`，表示 NPU 环境、Python 依赖和 msprof-analyze 均已正常配置，可以继续进行下一步操作。

### 2.2 采集性能数据

#### 2.2.1 准备模型训练代码

在容器内执行以下命令，将示例训练代码写入 `~/train_sample.py`。该示例使用随机数据训练 ResNet50 模型 5 个 epoch，并通过 Ascend PyTorch Profiler 采集性能数据：

```bash
cat > ~/train_sample.py << 'EOF'
import os, re, subprocess, sys, torch, torch_npu; import torch.nn as nn, torch.optim as optim, torchvision.models as models # 为精简篇幅，导入语句合并为单行（非规范写法）

def find_idle_npu():
    result = subprocess.run(["npu-smi", "info"], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"ERROR: npu-smi info failed: {result.stderr.strip()}")
    idle = [int(x) for x in re.findall(r"No running processes found in NPU\s+(\d+)", result.stdout)]
    print(f"[INFO] Available (idle) NPU IDs: {idle}")
    if not idle:
        sys.exit("[WARNING] No idle NPU, please free resources or retry later.")
    return idle[0]

def train():
    device = f"npu:{find_idle_npu()}"
    torch.npu.set_device(device)
    print(f"[INFO] Using device: {device}")

    model = models.resnet50(weights=None, num_classes=10).to(device)
    for parameter in model.parameters():
        parameter.requires_grad = False
    for parameter in model.fc.parameters():
        parameter.requires_grad = True

    optimizer = optim.Adam(model.fc.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss().to(device)
    dataset = torch.utils.data.TensorDataset(
        torch.randn(80, 3, 224, 224),
        torch.randint(0, 10, (80,)),
    )
    data_loader = torch.utils.data.DataLoader(dataset, batch_size=8, shuffle=True)

    experimental_config = torch_npu.profiler._ExperimentalConfig(
        export_type=[
            torch_npu.profiler.ExportType.Text,
            torch_npu.profiler.ExportType.Db,
        ],
        profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
        aic_metrics=torch_npu.profiler.AiCMetrics.AiCoreNone,
    )

    model.train()
    with torch_npu.profiler.profile(
        activities=[
            torch_npu.profiler.ProfilerActivity.CPU,
            torch_npu.profiler.ProfilerActivity.NPU,
        ],
        schedule=torch_npu.profiler.schedule(wait=0, warmup=1, active=3, repeat=1),
        on_trace_ready=torch_npu.profiler.tensorboard_trace_handler(f"{os.path.expanduser('~')}/result"),
        experimental_config=experimental_config,
    ) as profiler:
        for epoch in range(5):
            total_loss = 0.0
            for inputs, labels in data_loader:
                inputs, labels = inputs.to(device), labels.to(device)
                optimizer.zero_grad()
                loss = criterion(model(inputs), labels)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            print(f"[Epoch {epoch + 1}/5] Average Loss: {total_loss / len(data_loader):.4f}")
            profiler.step()

if __name__ == "__main__":
    train()
EOF
```

> [!CAUTION]注意
>
> 上述脚本会自动查找空闲 NPU 并在该设备上执行。如需指定 NPU，请将 `device = f"npu:{find_idle_npu()}"` 修改为实际设备编号，例如 `device = "npu:0"`。

#### 2.2.2 启动训练和采集

在容器内执行：

```bash
python3 ~/train_sample.py
```

显示类似以下信息，且出现 `All profiling data parsed`，表示训练及性能数据解析成功：

```text
[INFO] Available (idle) NPU IDs: [0]
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

若脚本提示没有空闲 NPU，请结束其他 NPU 任务或在其完成后重试；若超过 5 分钟不完成，有可能是 NPU 异常或被抢占，请重新执行或指定其他空闲 NPU。

#### 2.2.3 查看采集结果

运行以下命令，定位本次最新生成的 Profiling 数据目录并查看目录结构：

```bash
PROF_DIR=$(ls -dt "${HOME}"/result/*_ascend_pt | head -n 1)
echo "${PROF_DIR}"
tree -L 2 "${PROF_DIR}"
```

以 `_ascend_pt` 结尾的目录就是后续执行 msprof-analyze 时需要传入的 Profiling 数据路径。实际文件取决于采集内容和导出类型，常见结构如下：

```text
msprof_{timestamp}_ascend_pt
├── ASCEND_PROFILER_OUTPUT
│   ├── analysis.db
│   ├── ascend_pytorch_profiler_{rank_id}.db
│   ├── kernel_details.csv
│   ├── op_statistic.csv
│   ├── operator_details.csv
│   ├── step_trace_time.csv
│   ├── trace_view.json
│   └── ...
├── FRAMEWORK
└── PROF_XXX
```

### 2.3 执行 Advisor 分析

在容器内执行以下命令，对最新生成的 Profiling 数据进行一次完整的专家建议分析：

```bash
msprof-analyze advisor all -d "${PROF_DIR}" -o "${HOME}/advisor_output"
```

命令执行成功后，终端会输出简要分析结果，并在 `${HOME}/advisor_output` 目录中生成 HTML 报告和 XLSX 明细文件。

若提示 `${PROF_DIR}` 为空或目录不存在，请返回 [第 2.2.3 节](#223-查看采集结果)，重新执行定位结果目录的命令。

### 2.4 查看分析结果

#### 2.4.1 查看结果文件

执行以下命令查看生成的报告：

```bash
tree -L 2 "${HOME}/advisor_output"
```

常见结果结构如下：

```text
advisor_output
├── mstt_advisor_{timestamp}.html
└── log
    └── mstt_advisor_{timestamp}.xlsx
```

| 输出 | 用途 | 查看建议 |
| --- | --- | --- |
| `mstt_advisor_{timestamp}.html` | 展示总体结论、问题优先级、原因和优化建议 | 建议优先打开 |
| `log/mstt_advisor_{timestamp}.xlsx` | 展示各分析模块的明细数据 | 用于进一步定位具体算子、API 或通信项 |

#### 2.4.2 将报告复制到宿主机

在容器内执行以下命令，并复制该命令输出的变量赋值语句：

```bash
echo "CONTAINER_ID=${HOSTNAME:-$(cat /etc/hostname)}; ADVISOR_OUTPUT=${HOME}/advisor_output"
```

切换至宿主机终端，粘贴并执行上一步复制的变量赋值语句，然后将报告目录复制到宿主机当前目录：

```bash
docker cp "${CONTAINER_ID}:${ADVISOR_OUTPUT}" ./
```

使用浏览器打开 `advisor_output/mstt_advisor_{timestamp}.html` 即可查看分析报告。

#### 2.4.3 报告解读示例

下面的示例报告检测出了 DataLoader 数据加载耗时问题，将其标记为最高优先级，并给出了相应的优化建议。

![Advisor 结果示意图](../figures/quick_start_dataloader.png)
<div style="text-align: center;">
<strong>图1</strong> Advisor 分析报告示例
</div>

**建议按以下顺序解读报告：**

1. **查看总体结论**：确认报告首页是否存在标记为高优先级的性能瓶颈。
2. **分析问题详情**：仔细阅读问题列表中的问题类型、影响程度以及具体的优化建议。
3. **定位明细数据**：如需定位算子或 API 层面的具体原因，可打开 `log/mstt_advisor_{timestamp}.xlsx` 结合模块名称深入分析。
4. **进行调优验证**：根据建议修改训练脚本、数据加载逻辑或通信配置后，重新采集 Profiling 数据并运行 Advisor 验证优化效果。

> **延伸阅读**：如需了解更多分析维度、参数说明及高级解读技巧，请参阅 《[专家建议](../user_guide/advisor_instruct.md)》。

至此，您已掌握 msprof-analyze 性能瓶颈基础分析方法，本次快速入门结束。如需深入了解其功能用法，请参考：

- 《[专家建议](../user_guide/advisor_instruct.md)》
- 《[性能比对](../user_guide/compare_tool_instruct.md)》
- 《[集群分析](../user_guide/cluster_analyse_instruct.md)》
- 《[高级特性导航](../advanced_features/README.md)》

## 3. 内网环境无公网访问权限的应对方案

### 3.1 Docker 镜像在隔离内网的获取方法

**方案一：配置 Docker 代理直接拉取**

适用于大多数 Linux 发行版且 Docker 版本 ≥ 18.0 的环境（不保证所有场景兼容）。若遇异常，请结合实际情况调整。

编辑 Docker 服务代理配置文件 `/etc/systemd/system/docker.service.d/http-proxy.conf`，内容示例如下（请根据实际环境替换用户名、密码、代理地址及端口）：

```text
[Service]
Environment="HTTP_PROXY=http://username:password@proxy.example.com:8080"
Environment="HTTPS_PROXY=http://username:password@proxy.example.com:8080"
Environment="NO_PROXY=localhost,127.0.0.1,.example.com"
```

保存后重载并重启 Docker 服务：

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

随后即可正常执行 `docker pull`。

**方案二：离线导入 CANN 镜像**

如果代理方案不可行，请先在内网 NPU 服务器上执行 [第 2.1.2 节](#212-宿主机自动识别并配置镜像环境变量)，记录 `MY_STUDY_VAR_CANN_IMAGE` 的完整值。然后在具备公网访问能力且 CPU 架构相同的中转机上执行以下命令，将第一行的值替换为刚才记录的镜像地址：

```bash
CANN_IMAGE='完整镜像地址'
docker pull "${CANN_IMAGE}"
docker save -o cann.tar "${CANN_IMAGE}"
```

将 `cann.tar` 通过 U 盘等方式传输至内网服务器后，在内网服务器执行以下命令加载：

```bash
docker load -i cann.tar
docker images | grep cann
```

加载完成后，按照 [第 3.2 节](#32-传输容器启动脚本) 传输容器启动脚本，再返回 [第 2.1.5 节](#215-宿主机启动容器) 启动容器。如果已切换宿主机 Shell，请重新执行 [第 2.1.2 节](#212-宿主机自动识别并配置镜像环境变量) 中的命令以恢复镜像环境变量。

### 3.2 传输容器启动脚本

在可访问当前网页的浏览器中输入如下链接，下载 `ctr_in.py` 脚本文件，并将其手动复制至内网服务器的 `~/` 目录：

```text
https://inst.obs.cn-north-4.myhuaweicloud.com/env/ctr_in.py
```

复制完成后，在内网服务器的宿主机上执行：

```bash
cd ~
chmod +x ctr_in.py
ls -l ctr_in.py
```

确认 `ctr_in.py` 存在且具有执行权限后，返回 [第 2.1.5 节](#215-宿主机启动容器) 启动容器。

### 3.3 离线安装 Python 依赖和 msprof-analyze

优先使用内网 pip 源安装依赖。若没有可用的内网软件源，请在具备公网访问能力，且 CPU 架构和 Python 版本均与内网 NPU 服务器相同的中转环境中，按以下方式下载所需安装包：

```bash
mkdir -p offline_wheels
python3 -m pip download xxx --dest offline_wheels # xxx 为需要下载的包名
```

将 `offline_wheels` 目录传输到内网服务器并复制到容器的用户主目录，然后在容器内执行：

```bash
pip3 install --no-index --find-links="${HOME}/offline_wheels" xxx # xxx 为需要安装的包名
```

安装完成后，返回 [第 2.1.7 节](#217-容器内验证环境是否安装正确) 执行验证命令，无需再次执行联网安装命令。

## 4. 常见问题（FAQ）

### 4.1 退出容器后如何重新进入？

在宿主机执行以下任一命令：

**方法一（推荐）**：执行 `~/ctr_in.py`，交互式选择目标容器（若仅有一个容器则自动进入）。

**方法二（原生命令）**：执行 `docker exec -it <container_name> bash`（请替换为实际容器名称）。

### 4.2 执行 Docker 命令遇到 permission denied 类错误提示？

可能当前用户未加入 Docker 用户组。可使用 root 权限在宿主机执行：

```bash
sudo usermod -aG docker <当前用户名>
```

执行后需要重新登录当前用户会话，或执行 `newgrp docker` 使用户组变更立即生效。不建议以 root 身份进行日常操作。
