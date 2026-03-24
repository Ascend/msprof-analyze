
<h1 align="center">MindStudio Profiler Analyze</h1>
<div align="center">
  <p>🚀 <b>昇腾性能分析工具</b></p>

[📖工具文档](./docs/zh/getting_started/quick_start.md) |
[🔥昇腾社区](https://www.hiascend.com/developer/software/mindstudio) |
[🌐Release](https://gitcode.com/Ascend/msprof-analyze/releases)

</div>

## 📢 最新消息

* [2025.12.30]：新增 `module_statistic` 分析能力：提供的针对PyTorch模型自动解析模型层级结构的分析能力，帮助精准定位性能瓶颈。

## 📌 简介

MindStudio Profiler Analyze（`msprof-analyze`）是面向 AI 训练与推理场景的性能分析工具，基于采集得到的 profiling 数据进行统计、比对和诊断，帮助定位计算、通信、调度及集群场景下的性能瓶颈。

## 功能介绍

| 功能点 | 功能简介                                                                         | 资料链接 | 源码目录                                                       |
| --- |------------------------------------------------------------------------------| --- |------------------------------------------------------------|
| **专家建议** | 基于性能数据自动识别计算、调度、通信等潜在问题，并输出优化建议。                                             | [点击查看](./docs/zh/user_guide/advisor_instruct.md) | [点击查看](./msprof_analyze/advisor)                           |
| **性能比对** | 支持 GPU/NPU、NPU/NPU 等多种场景的性能差异分析。                                             | [点击查看](./docs/zh/user_guide/compare_tool_instruct.md) | [点击查看](./msprof_analyze/compare_tools)                     |
| **集群分析** | 汇总集群通信数据，输出结果支持在 MindStudio Insight 中可视化查看。                                  | [点击查看](./docs/zh/user_guide/cluster_analyse_instruct.md) | [点击查看](./msprof_analyze/cluster_analyse)                   |
| **扩展分析** | 基于 DB 类型性能数据，提供可自定义的 Recipe 分析规则，目前已涵盖拆解对比、Host 下发、计算、通信等 20 余种多维度分析能力，便于灵活扩展。 | [点击查看](./docs/zh/advanced_features/README.md) | [点击查看](./msprof_analyze/cluster_analyse/recipes) |

### 工具安装

推荐直接通过 `pip` 安装：

```bash
pip install -U msprof-analyze
```

如需 whl 包下载、源码编译，请参见 [《安装指南》](./docs/zh/getting_started/install_guide.md)。

## 快速入门

`msprof-analyze` 常用分析命令如下：

```bash
# 集群通信汇总
msprof-analyze cluster -m all -d ./cluster_data

# 专家建议
msprof-analyze advisor all -d ./prof_data -o ./advisor_output

# 性能比对
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output
```

以 ResNet50 模型训练任务为例，[《快速入门》](./docs/zh/getting_started/quick_start.md)贯穿从采集性能数据、执行 Advisor 分析到查看分析结果的完整流程，帮助您快速体验工具的核心功能。

## 目录结构

关键目录如下，详细信息参见 [《目录结构说明》](./docs/zh/dir_structure.md)。

```text
msprof-analyze
├── config                      # 配置文件目录
├── docs                        # 文档目录
├── msprof_analyze              # 主代码包目录
│   ├── advisor                 # 专家建议模块
│   ├── cli                     # 命令行入口
│   ├── cluster_analyse         # 集群分析模块
│   ├── compare_tools           # 性能比对模块
│   ├── prof_common             # 公共能力模块
│   └── prof_exports            # 导出模块
├── requirements                # 依赖管理目录
├── test                        # 测试目录
└── README.md                   # 项目说明文档
```

## 📝 相关说明

- [《自定义分析规则开发指导》](docs/zh/advanced_features/custom_analysis_guide.md)
- [《版本说明》](docs/zh/release_notes.md)
- [《License 声明》](docs/zh/legal/license_notice.md)
- [《安全声明》](docs/zh/legal/security_statement.md)
- [《免责声明》](docs/zh/legal/disclaimer.md)

## 💬 建议与交流

欢迎大家为社区做贡献。如果有任何疑问或建议，请提交 [Issues](https://gitcode.com/Ascend/msprof-analyze/issues)，我们会尽快回复。感谢您的支持。

## 🤝 致谢

本工具由华为公司的下列部门联合贡献：

- 昇腾计算 MindStudio 开发部
- 华为云昇腾云服务
- 昇腾计算生态使能部
- 2012 网络实验室

感谢来自社区的每一个 PR，欢迎贡献 `msprof-analyze`。

## 关于MindStudio团队

华为 MindStudio 全流程开发工具链团队致力于提供端到端的昇腾 AI 应用开发解决方案，使能开发者高效完成训练开发、推理开发和算子开发。欢迎通过 [昇腾社区](https://www.hiascend.com/developer/software/mindstudio) 了解更多相关产品与资料。
