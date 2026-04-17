
<h1 align="center">MindStudio Profiler Analyze</h1>
<div align="center">
  <p>🚀 <b>Ascend Profile Data Analysis Tool</b></p>

[📖 Documentation](./docs/en/getting_started/quick_start.md) |
[🔥 Ascend Community](https://www.hiascend.com/developer/software/mindstudio) |
[🌐Release](https://gitcode.com/Ascend/msprof-analyze/releases)

</div>

## 📢 What's New

* [2025.12.30] Added the `module_statistic` feature, which automatically analyzes PyTorch model hierarchies to help accurately locate performance bottlenecks.

## 📌 Overview

MindStudio Profiler Analyze (`msprof-analyze`) is a profile data analysis tool designed for AI training and inference scenarios. It analyzes, compares, and diagnoses the collected profile data to help locate performance bottlenecks in computation, communication, scheduling, and cluster scenarios.

## 📖 Features

| Feature| Description                                                                        | Document| Source Code Directory                                                      |
| --- |------------------------------------------------------------------------------| --- |------------------------------------------------------------|
| advisor| Automatically identifies potential issues in computation, scheduling, and communication based on profile data and provides optimization suggestions.                                            | [advisor](./docs/en/user_guide/advisor_instruct.md)| [advisor](./msprof_analyze/advisor)                    |
| compare| Analyzes performance gaps across various scenarios, including GPU-NPU and NPU-NPU comparisons.                                            | [compare](./docs/en/user_guide/compare_tool_instruct.md)| [compare_tools](./msprof_analyze/compare_tools)        |
| cluster_analyse| Summarizes cluster communication data and outputs results that can be visualized in MindStudio Insight.                                 | [cluster_analyse](./docs/en/user_guide/cluster_analyse_instruct.md)| [cluster_analyse](./msprof_analyze/cluster_analyse)    |
| Recipe Analysis Rules| Provides customizable recipe analysis rules based on DB-format profile data. Currently, more than 20 multi-dimensional analysis capabilities, such as breakdown comparison, host delivery, computation, and communication, are available for flexible expansion.| [Recipe Analysis Rules](./docs/en/advanced_features/README.md)| [recipes](./msprof_analyze/cluster_analyse/recipes) |

## 🛠️ Tool Installation

You are advised to install the tool directly using `pip`.

```bash
pip install -U msprof-analyze
```

For details about WHL package download and building from source code, see [MindStudio Profiler Analyze Installation Guide](./docs/en/getting_started/install_guide.md).

## 🚀 Quick Start

Common `msprof-analyze` commands are as follows:

```bash
# cluster
msprof-analyze cluster -m all -d ./cluster_data

# advisor
msprof-analyze advisor all -d ./prof_data -o ./advisor_output

# compare
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output
```

Taking profile data from a ResNet-50 model training task as an example, [Quick Start](docs/en/getting_started/quick_start.md) guides you through the entire process from collecting profile data and performing `advisor` analysis to viewing the analysis results. It helps you quickly experience the core functions of this tool.

## 🔍 Directory Structure

The key directories are as follows. For details, see [Project Directory](./docs/en/dir_structure.md).

```text
msprof-analyze
├── config                      # Configuration file directory
├── docs                        # Documentation directory
├── msprof_analyze              # Main code package directory
│   ├── advisor                 # Expert suggestion module
│   ├── cli                     # Command-line interface module
│   ├── cluster_analyse         # Cluster analysis module
│   ├── compare_tools           # Performance comparison module
│   ├── prof_common             # Common module
│   └── prof_exports            # Export module
├── requirements                # Dependency management directory
├── test                        # Test directory
└── README.md                   # Project description
```

## 📝 References

- [Custom Analysis Rule Development Guide](docs/en/advanced_features/custom_analysis_guide.md)
- [Release Notes](docs/en/release_notes.md)
- [License Notice](docs/en/legal/license_notice.md)
- [Security Statement](docs/en/legal/security_statement.md)
- [Disclaimer](/docs/en/legal/disclaimer.md)

## 💬 Suggestions and Feedback

You are welcome to contribute to the community. If you have any questions or suggestions, please submit [issues](https://gitcode.com/Ascend/msprof-analyze/issues). We will reply as soon as possible. Thank you for your support.

## 🤝 Acknowledgments

This tool is jointly developed by the following Huawei departments:

- Ascend Computing MindStudio Development Department
- Huawei Cloud AI Compute Service
- Ascend Computing Ecosystem Enablement Department
- 2012 Network Laboratories

Thank you to everyone in the community for your PRs. We warmly welcome contributions to `msprof-analyze`.

## About the MindStudio Team

The Huawei MindStudio full-pipeline development toolchain team is dedicated to providing an end-to-end solution for building Ascend AI applications, accelerating the processes of training, inference, and operator development. For more information about the related products and documentation, visit the [Ascend Community](https://www.hiascend.com/developer/software/mindstudio).
