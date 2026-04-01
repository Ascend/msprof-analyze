# 项目目录

详细项目介绍如下：

```ColdFusion
msprof-analyze
├── config                       # 配置文件目录
├── docs                         # 文档目录
├── msprof_analyze               # 主代码包目录
│   ├── advisor                  # 性能分析建议器模块
│   │   ├── advisor_backend      # 建议器后端实现
│   │   ├── analyzer             # 性能分析器模块
│   │   ├── common               # 通用功能模块
│   │   ├── config               # 配置管理模块
│   │   ├── dataset              # 数据集处理模块
│   │   ├── display              # 显示输出模块
│   │   ├── interface            # 接口定义模块
│   │   ├── result               # 结果处理模块
│   │   ├── rules                # 规则定义模块
│   │   └── utils                # 工具函数模块
│   ├── cli                      # 命令行接口模块
│   ├── cluster_analyse          # 集群分析核心模块
│   │   ├── analysis             # 分析算法实现
│   │   ├── cluster_data_preprocess # 集群数据预处理
│   │   ├── cluster_kernels_analysis # 集群内核分析
│   │   ├── cluster_utils        # 集群工具函数
│   │   ├── common_func          # 通用功能
│   │   ├── communication_group  # 通信组管理
│   │   ├── prof_bean            # 性能数据Bean定义
│   │   ├── recipes              # 分析能力模块
│   │   └── resources            # 资源文件目录
│   ├── compare_tools            # 性能对比工具模块
│   │   ├── compare_backend      # 对比后端实现
│   │   └── compare_interface    # 比较接口定义
│   ├── prof_common              # 性能分析通用模块
│   └── prof_exports             # 性能数据导出模块
├── requirements                 # 依赖管理目录
└── test                         # 测试目录
```
