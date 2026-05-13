
<h1 align="center">MindStudio Profiler Analyze</h1>
<div align="center">
  <p>🚀 <b>昇腾性能分析工具</b></p>

[![doc](https://badgen.net/badge/doc/readthedocs/green)](https://mindstudio-profiler-docs.readthedocs.io/zh-cn/latest/msprof-analyze/)
[![License](https://badgen.net/badge/License/MulanPSL-2.0/blue)](https://raw.gitcode.com/Ascend/msinsight/files/master/License)
[![Version](https://badgen.net/badge/Version/26.0.0-alpha.1/green)](https://gitcode.com/Ascend/msprof-analyze/releases) 
[![Ascend](https://img.shields.io/badge/Hardware-Ascend-orange.svg)](https://www.hiascend.com/)

</div>

## 📢 最新消息

* [2025.12.30]：新增 `module_statistic` 分析能力：提供的针对PyTorch模型自动解析模型层级结构的分析能力，帮助精准定位性能瓶颈。

## 📌 简介

MindStudio Profiler Analyze（`msprof-analyze`）是面向 AI 训练与推理场景的性能分析工具，基于采集得到的 profiling 数据进行统计、比对和诊断，帮助定位计算、通信、调度及集群场景下的性能瓶颈。

## 📖 功能介绍

| 功能名称 | 功能简介                                                                         | 文档 | 源码目录                                                       |
| --- |------------------------------------------------------------------------------| --- |------------------------------------------------------------|
| 专家建议 | 基于性能数据自动识别计算、调度、通信等潜在问题，并输出优化建议。                                             | [专家建议](./docs/zh/user_guide/advisor_instruct.md) | [advisor](./msprof_analyze/advisor)                    |
| 性能比对 | 支持 GPU/NPU、NPU/NPU 等多种场景的性能差异分析。                                             | [性能比对](./docs/zh/user_guide/compare_tool_instruct.md) | [compare_tools](./msprof_analyze/compare_tools)        |
| 集群分析 | 汇总集群通信数据，输出结果支持在 MindStudio Insight 中可视化查看。                                  | [集群分析](./docs/zh/user_guide/cluster_analyse_instruct.md) | [cluster_analyse](./msprof_analyze/cluster_analyse)    |
| 扩展分析 | 基于 DB 类型性能数据，提供可自定义的 Recipe 分析规则，目前已涵盖拆解对比、Host 下发、计算、通信等 20 余种多维度分析能力，便于灵活扩展。 | [扩展分析](./docs/zh/advanced_features/README.md) | [recipes](./msprof_analyze/cluster_analyse/recipes) |

## 🛠️ 工具安装

推荐直接通过 `pip` 安装：

```bash
pip install -U msprof-analyze
```

如需 whl 包下载、源码编译，请参见 《[msprof-analyze工具安装指南](./docs/zh/getting_started/install_guide.md)》。

## 🚀 快速入门

`msprof-analyze` 常用分析命令如下：

```bash
# 集群通信汇总
msprof-analyze cluster -m all -d ./cluster_data

# 专家建议
msprof-analyze advisor all -d ./prof_data -o ./advisor_output

# 性能比对
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output
```

以 ResNet50 模型训练任务为例，《[快速入门](./docs/zh/getting_started/quick_start.md)》贯穿从采集性能数据、执行 Advisor 分析到查看分析结果的完整流程，帮助您快速体验工具的核心功能。

## 🔍 目录结构

关键目录如下，详细信息参见 《[目录结构说明](./docs/zh/dir_structure.md)》。

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

- 《[自定义分析规则开发指导](docs/zh/advanced_features/custom_analysis_guide.md)》
- 《[版本说明](docs/zh/release_notes.md)》
- 《[License 声明](docs/zh/legal/license_notice.md)》
- 《[安全声明](docs/zh/legal/security_statement.md)》
- 《[免责声明](docs/zh/legal/disclaimer.md)》

## 💬 建议与交流

欢迎大家为社区做贡献。如果有任何疑问或建议，请提交 [Issues](https://gitcode.com/Ascend/msprof-analyze/issues)，我们会尽快回复。感谢您的支持。

诚邀参与[满意度问卷调查](https://rdccucd.wjx.cn/vm/PKPfKqO.aspx)抽取惊喜好礼😎。

| 💬 技术交流群 | 📢 官方公众号 | 🤝 更多加入渠道 |
| :---: | :---: | :--- |
| <img src="https://raw.gitcode.com/Ascend/msinsight/raw/master/docs/zh/user_guide/figures/readme/officialGroupChat.jpg" width="120"><br><sub>*扫码直接加入技术交流群*</sub> | <img src="https://raw.gitcode.com/Ascend/msinsight/raw/master/docs/zh/user_guide/figures/readme/officialAccount.jpg" width="120"><br><sub>*扫码关注获取最新动态*</sub> |欢迎扫码关注技术交流群跟官方公众号。这里是 MindStudio 用户与开发者最快捷的交流阵地：<br> **快速提问：** 与社区小伙伴即时探讨技术问题<br>**掌握动态：** 第一时间获取版本发布与功能更新通知<br> **经验共享：** 与其他开发者交流最佳实践  <br>🛠️ **其他渠道**：<br>👉 昇腾助手：[![WeChat](https://img.shields.io/badge/WeChat-07C160?style=flat-square&logo=wechat&logoColor=white)](https://gitcode.com/Ascend/msit/blob/master/docs/zh/figures/readme/xiaozhushou.png)<br>👉 昇腾论坛：[![Website](https://img.shields.io/badge/Website-%231e37ff?style=flat-square&logo=RSS&logoColor=white)](https://www.hiascend.com/forum/) |

## 🤝 致谢

本工具由华为公司的下列部门联合贡献：

- 昇腾计算 MindStudio 开发部
- 华为云昇腾云服务
- 昇腾计算生态使能部
- 2012 网络实验室

感谢来自社区的每一个 PR，欢迎贡献 `msprof-analyze`。

## 关于MindStudio团队

华为 MindStudio 全流程开发工具链团队致力于提供端到端的昇腾 AI 应用开发解决方案，使能开发者高效完成训练开发、推理开发和算子开发。更多信息请访问 [昇腾社区](https://www.hiascend.com/developer/software/mindstudio) 和 [昇腾论坛](https://www.hiascend.com/forum/)。
