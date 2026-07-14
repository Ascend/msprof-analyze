
<h1 align="center">MindStudio Profiler Analyze</h1>
<div align="center">
<p><b><span style="font-size:24px;">昇腾性能分析工具</span></b></p>

 [![快速入门](https://badgen.net/badge/快速入门/QuickStart/blue)](docs/zh/quick_start/msprof-analyze_quick_start.md)
 [![AI问答(DeepWiki)](https://badgen.net/badge/AI问答/DeepWiki/blue)](https://deepwiki.com/mindstudio-docs/master) 
 [![AI问答(ZRead)](https://badgen.net/badge/AI问答/ZRead/blue)](https://zread.ai/mindstudio-docs/master) 
 [![精确搜索](https://badgen.net/badge/精确搜索/ReadTheDocs/blue)](https://mindstudio-profiler-docs.readthedocs.io/zh-cn/latest/msprof-analyze/) 
 [![昇腾社区](https://badgen.net/badge/昇腾社区/Community/blue)](https://www.hiascend.com/cn/developer/software/mindstudio) 
 [![报告问题](https://badgen.net/badge/报告问题/Issues/blue)](https://gitcode.com/Ascend/msprof-analyze/issues) 

</div>

## ✨ 最新消息

🔹 [2025.12.30]：新增 `module_statistic` 功能：自动解析PyTorch模型层级结构，精准定位性能瓶颈。  

## ℹ️ 简介

MindStudio Profiler Analyze（`msprof-analyze`）是面向 AI 训练与推理场景的性能分析工具，基于采集得到的 profiling 数据进行统计、比对和诊断，帮助定位计算、通信、调度及集群场景下的性能瓶颈。

## ⚙️ 功能介绍

| 功能名称 | 功能简介                                                   | 源码                                           |
| --- |--------------------------------------------------------|----------------------------------------------|
| [专家建议](./docs/zh/user_guide/advisor_instruct.md) | 基于性能数据自动识别计算、调度、通信等潜在问题，并输出优化建议。                       | [查看](./msprof_analyze/advisor)               |
| [性能比对](./docs/zh/user_guide/compare_tool_instruct.md) | 支持 GPU/NPU、NPU/NPU 等多种场景的性能差异分析。                       | [查看](./msprof_analyze/compare_tools)         |
| [集群分析](./docs/zh/user_guide/cluster_analyse_instruct.md) | 汇总集群通信数据，输出结果支持在 MindStudio Insight 中可视化查看。            | [查看](./msprof_analyze/cluster_analyse)       |
| [进阶分析](./docs/zh/advanced_features/README.md) | 基于DB性能数据，自定义Recipe规则，涵盖拆解对比、Host下发、计算通信等20+分析能力，可灵活扩展。 | [查看](./msprof_analyze/cluster_analyse/recipes) |

## 🚀 快速入门

**10 分钟实战体验**  
以 ResNet50 训练为例，覆盖**采集数据、执行 Advisor 分析与查看分析结果**全流程。点击立即开始：《[msprof-analyze 快速入门](docs/zh/quick_start/msprof-analyze_quick_start.md)》。

**极简命令行速查**  
若已熟悉操作流程，可直接执行分析命令，示例如下：

```bash
# 集群通信汇总
msprof-analyze cluster -m all -d ./cluster_data
# 专家建议
msprof-analyze advisor all -d ./prof_data -o ./advisor_output
# 性能比对
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output
```

## 📦 安装指南

推荐直接通过 `pip` 安装：

```bash
pip install -U msprof-analyze
```

如需 whl 包下载、源码编译，请参见 《[msprof-analyze工具安装指南](./docs/zh/install_guide/msprof-analyze_install_guide.md)》。

## 📘 使用指南

工具的详细使用方法，请参见 《[msprof-analyze使用指南](./docs/zh/user_guide/cluster_analyse_instruct.md)》。

## 🌌 智能检索

为提升文档查阅效率，我们提供多种高效检索方式：

🔹 [AI 问答（DeepWiki）](https://deepwiki.com/mindstudio-docs/master)：自然语言问答，快速把握项目架构与模块关系。   
🔹 [AI 问答（ZRead）](https://zread.ai/mindstudio-docs/master)：中文问答体验更优，精准定位功能用法与细节。   
🔹 [精确搜索（ReadTheDocs）](https://mindstudio-docs-master.readthedocs.io)：关键词全文检索，直达接口、参数与报错等信息。 

## ⚖️ 相关说明

🔹 《[版本说明](https://gitcode.com/Ascend/msprof-analyze/releases)》  
🔹 《[许可证声明](docs/zh/legal/license_notice.md)》  
🔹 《[安全声明](docs/zh/legal/security_statement.md)》  
🔹 《[免责声明](docs/zh/legal/disclaimer.md)》  

## 🤝 建议与交流

欢迎大家为社区做贡献。如果有任何疑问或建议，请提交 [Issues](https://gitcode.com/Ascend/msprof-analyze/issues)，我们会尽快回复。感谢您的支持。

诚邀参与[满意度问卷调查](https://rdccucd.wjx.cn/vm/PKPfKqO.aspx)抽取惊喜好礼😎。

| 💬 技术交流群 | 📢 官方公众号 | 🤝 更多加入渠道 |
| :---: | :---: | :--- |
| <img src="https://raw.gitcode.com/Ascend/msinsight/raw/master/docs/zh/user_guide/figures/readme/officialGroupChat.png" width="120"><br><sub>*扫码直接加入技术交流群*</sub> | <img src="https://raw.gitcode.com/Ascend/msinsight/raw/master/docs/zh/user_guide/figures/readme/officialAccount.png" width="120"><br><sub>*扫码关注获取最新动态*</sub> |欢迎扫码关注技术交流群跟官方公众号。这里是 MindStudio 用户与开发者最快捷的交流阵地：<br> **快速提问：** 与社区小伙伴即时探讨技术问题<br>**掌握动态：** 第一时间获取版本发布与功能更新通知<br> **经验共享：** 与其他开发者交流最佳实践  <br>🛠️ **其他渠道**：<br>👉 昇腾助手：[![WeChat](https://img.shields.io/badge/WeChat-07C160?style=flat-square&logo=wechat&logoColor=white)](https://gitcode.com/Ascend/msit/blob/master/docs/zh/figures/readme/xiaozhushou.png)<br>👉 昇腾论坛：[![Website](https://img.shields.io/badge/Website-%231e37ff?style=flat-square&logo=RSS&logoColor=white)](https://www.hiascend.com/forum/) |

## 🙏 致谢

本工具由华为公司的下列部门联合贡献：  
🔹 昇腾计算MindStudio开发部  
🔹 昇腾计算生态使能部  
🔹 华为云昇腾云服务  
🔹 2012 网络实验室

感谢来自社区的每一个 PR，欢迎贡献 `msprof-analyze`。
