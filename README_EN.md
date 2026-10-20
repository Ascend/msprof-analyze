
<h1 align="center">MindStudio Profiler Analyze</h1>
<div align="center">
<p><b><span style="font-size:24px;">Ascend Performance Analysis Tool</span></b></p>

[![Quick Start](https://badgen.net/badge/Quick%20Start/QuickStart/blue)](docs/en/quick_start/msprof-analyze_quick_start.md)
[![AI Q&A (DeepWiki)](https://badgen.net/badge/AI%20Q%26A/DeepWiki/blue)](https://deepwiki.com/mindstudio-docs/master)
[![AI Q&A (ZRead)](https://badgen.net/badge/AI%20Q%26A/ZRead/blue)](https://zread.ai/mindstudio-docs/master)
[![Exact Search](https://badgen.net/badge/Exact%20Search/ReadTheDocs/blue)](https://mindstudio-profiler-docs.readthedocs.io/zh-cn/latest/msprof-analyze/)
[![Ascend Community](https://badgen.net/badge/Ascend%20Community/Community/blue)](https://www.hiascend.com/en/developer/software/mindstudio)
[![Report an Issue](https://badgen.net/badge/Report%20an%20Issue/Issues/blue)](https://gitcode.com/Ascend/msprof-analyze/issues)

</div>

English | [简体中文](./README.md)

## ✨ What's New

🔹 [2025.12.30]: Added the `module_statistic` feature, which automatically analyzes the hierarchical structure of PyTorch models to accurately locate performance bottlenecks.

## ℹ️ Overview

MindStudio Profiler Analyze (`msprof-analyze`) is a performance analysis tool for AI training and inference scenarios. It performs statistical analysis, comparisons, and diagnostics on collected profile data to help locate performance bottlenecks in computation, communication, scheduling, and cluster scenarios.

## ⚙️ Features

| Feature | Description | Source Code |
| --- | --- | --- |
| [`advisor`](./docs/en/user_guide/advisor_instruct.md) | Automatically identifies potential issues in computation, scheduling, and communication based on profile data and provides optimization suggestions. | [View](./msprof_analyze/advisor) |
| [`compare`](./docs/en/user_guide/compare_tool_instruct.md) | Supports performance comparison in various scenarios, including GPU/NPU and NPU/NPU comparisons. | [View](./msprof_analyze/compare_tools) |
| [`cluster_analyse`](./docs/en/user_guide/cluster_analyse_instruct.md) | Summarizes cluster communication data, with results that can be visualized in MindStudio Insight. | [View](./msprof_analyze/cluster_analyse) |
| [Advanced Analysis](./docs/en/advanced_features/README.md) | Provides customizable recipe rules based on `db`-format profile data, covering more than 20 analysis capabilities, including breakdown comparison, host-side dispatch, and computation and communication analysis, with flexible extensibility. | [View](./msprof_analyze/cluster_analyse/recipes) |

## 🚀 Quick Start

**10-Minute Hands-On Experience**  
Using ResNet-50 training as an example, this guide covers the entire process of **collecting data, running `advisor` analysis, and viewing the analysis results**. Click here to get started: [msprof-analyze Quick Start](docs/en/quick_start/msprof-analyze_quick_start.md).

**Quick Command-Line Reference**  
If you are already familiar with the workflow, you can directly run the analysis commands. Examples are as follows:

```bash
# Cluster communication aggregation
msprof-analyze cluster -m all -d ./cluster_data
# Expert advice
msprof-analyze advisor all -d ./prof_data -o ./advisor_output
# Performance comparison
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output
```

## 📦 Installation Guide

You are advised to install the tool directly using `pip`:

```bash
pip install -U msprof-analyze
```

For details about downloading the WHL package and building from source code, see [msprof-analyze Installation Guide](./docs/en/install_guide/msprof-analyze_install_guide.md).

## 📘 User Guide

For detailed instructions on using the tool, see [msprof-analyze User Guide](./docs/en/user_guide/cluster_analyse_instruct.md).

## 🌌 Intelligent Search

To improve the efficiency of document retrieval, we provide multiple efficient search methods:

🔹 [AI Q&A (DeepWiki)](https://deepwiki.com/mindstudio-docs/master): Natural-language Q&A for quickly understanding the project architecture and relationships between modules.  
🔹 [AI Q&A (ZRead)](https://zread.ai/mindstudio-docs/master): Provides enhanced Q&A experience and accurately locates feature usage and details.  
🔹 [Exact Search (ReadTheDocs)](https://mindstudio-docs-master.readthedocs.io): Supports full-text keyword searches for direct access to information such as APIs, parameters, and error messages.

## ⚖️ References

🔹 [Release Notes](https://gitcode.com/Ascend/msprof-analyze/releases)  
🔹 [License Notice](docs/en/legal/license_notice.md)  
🔹 [Security Statement](docs/en/legal/security_statement.md)  
🔹 [Disclaimer](docs/en/legal/disclaimer.md)

## 🤝 Suggestions and Feedback

You are welcome to contribute to the community. If you have any questions or suggestions, please submit an [issue](https://gitcode.com/Ascend/msprof-analyze/issues), and we will reply as soon as possible. Thank you for your support.

You are also welcome to participate in the [satisfaction survey](https://rdccucd.wjx.cn/vm/PKPfKqO.aspx) for a chance to win surprise gifts 😎.

| 💬 Technical Discussion Group | 📢 Official WeChat Account | 🤝 More Ways to Join |
| :---: | :---: | :--- |
| <img src="https://raw.gitcode.com/Ascend/msinsight/raw/master/docs/zh/user_guide/figures/readme/officialGroupChat.png" width="120"><br><sub>*Scan the QR code to join the technical discussion group*</sub> | <img src="https://raw.gitcode.com/Ascend/msinsight/raw/master/docs/zh/user_guide/figures/readme/officialAccount.png" width="120"><br><sub>*Scan the QR code to follow the account for the latest updates*</sub> | Scan the QR codes to join the technical discussion group and follow the official WeChat account. This is a convenient communication platform for MindStudio users and developers:<br>**Ask questions:** Discuss technical issues with community members in real time<br>**Stay updated:** Get the latest version releases and feature updates as soon as they are available<br>**Share experience:** Exchange best practices with other developers<br>🛠️ **Other channels**:<br>👉 Ascend Assistant: [![WeChat](https://img.shields.io/badge/WeChat-07C160?style=flat-square\&logo=wechat\&logoColor=white)](https://gitcode.com/Ascend/msit/blob/master/docs/zh/figures/readme/xiaozhushou.png)<br>👉 Ascend Forum: [![Website](https://img.shields.io/badge/Website-%231e37ff?style=flat-square\&logo=RSS\&logoColor=white)](https://www.hiascend.com/forum/) |

## 🙏 Acknowledgments

This tool was jointly contributed by the following Huawei departments:

🔹 Ascend Computing MindStudio Development Department  
🔹 Ascend Computing Ecosystem Enablement Department  
🔹 Huawei Cloud AI Compute Service  
🔹 2012 Network Laboratories

Thank you to everyone in the community for your PRs. We warmly welcome your contributions to `msprof-analyze`.
