# 开发指南

## 1. MindStudio Profiler Analyze开发软件

| 软件名 | 用途 |
| --- | --- |
| PyCharm（推荐）/ VS Code | 编写和调试 Python 代码 |
| Git | 拉取、管理和提交代码 |
| Python 虚拟环境工具（venv） | 隔离开发依赖 |
| Jupyter Notebook（可选） | 调试 Advisor 相关 Notebook 能力 |

## 2. 开发环境配置

| 软件名 | 版本要求 | 用途 |
| --- | --- | --- |
| Python | 3.7 及以上 | 主开发环境 |
| pip | 与 Python 配套 | 安装依赖和本地包 |
| wheel | 最新稳定版 | 构建 whl 包 |
| Git | 无硬性要求 | 代码管理 |

### 2.1 开发依赖

基础依赖定义在 `requirements/build.txt`，测试依赖定义在 `requirements/tests.txt`。

其中核心运行依赖包括：

- `click`
- `tabulate`
- `networkx`
- `jinja2`
- `PyYaml`
- `tqdm`
- `prettytable`
- `ijson`
- `xlsxwriter`
- `sqlalchemy`
- `numpy`
- `pandas`
- `psutil`
- `pybind11`

### 2.2 推荐环境准备

建议在仓库根目录下使用虚拟环境进行开发：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements/build.txt
pip install -r requirements/tests.txt
```

## 3. 开发步骤

### 3.1 代码下载与本地安装

```bash
git clone https://gitcode.com/Ascend/msprof-analyze
cd msprof-analyze
pip install --editable .
```

`setup.py` 中已注册命令行入口，安装完成后可直接使用如下命令验证：

```bash
msprof-analyze --help
msprof-analyze -V
```

### 3.2 项目目录说明

当前仓库的关键目录如下：

| 目录 | 说明 |
| --- | --- |
| `msprof_analyze/advisor` | 专家建议模块 |
| `msprof_analyze/cli` | 命令行入口和子命令注册 |
| `msprof_analyze/cluster_analyse` | 集群分析主模块 |
| `msprof_analyze/compare_tools` | 性能比对模块 |
| `msprof_analyze/prof_common` | 公共能力模块 |
| `msprof_analyze/prof_exports` | 各类分析结果导出模块 |
| `requirements` | 依赖清单 |
| `test/ut` | 单元测试 |
| `test/st` | 系统测试 |
| `docs/zh` | 中文文档 |

### 3.3 命令行入口开发

`msprof-analyze` 的命令入口定义在 `msprof_analyze/cli/entrance.py`。当前已注册的主要子命令如下：

| 子命令 | 说明 |
| --- | --- |
| `advisor` | 专家建议分析 |
| `compare` | 性能比对 |
| `cluster` | 集群分析 |
| `auto-completion` | 自动补全 |

开发时需要注意：

1. 若用户未显式输入子命令但携带参数，工具会默认补充 `cluster` 子命令。
2. 若用户不带任何参数，工具会默认展示 `cluster --help`。
3. 命令帮助的展示顺序由 `COMMAND_PRIORITY` 控制。

若新增命令行子命令，通常需要同步修改：

1. `msprof_analyze/cli` 下新增对应 CLI 文件。
2. `msprof_analyze/cli/entrance.py` 中注册子命令。
3. 用户文档中新增参数和示例说明。

### 3.4 常见功能开发入口

#### 3.4.1 开发 Advisor 能力

当新增专家建议分析逻辑时，主要关注：

- `msprof_analyze/advisor/advisor_backend`
- `msprof_analyze/advisor/analyzer`
- `msprof_analyze/advisor/rules`
- `msprof_analyze/advisor/result`

适用场景：

1. 新增规则识别逻辑。
2. 调整建议生成策略。
3. 扩展 HTML / XLSX 结果呈现。

#### 3.4.2 开发 Compare 能力

当新增性能比对逻辑时，主要关注：

- `msprof_analyze/compare_tools/compare_backend`
- `msprof_analyze/compare_tools/compare_interface`

适用场景：

1. 扩展 GPU/NPU 或 NPU/NPU 比对维度。
2. 调整算子识别和对齐策略。
3. 增强比对结果导出内容。

#### 3.4.3 开发 Cluster Analyze 能力

当新增集群分析能力时，主要关注：

- `msprof_analyze/cluster_analyse/analysis`
- `msprof_analyze/cluster_analyse/cluster_data_preprocess`
- `msprof_analyze/cluster_analyse/cluster_kernels_analysis`
- `msprof_analyze/cluster_analyse/communication_group`
- `msprof_analyze/cluster_analyse/recipes`

其中：

1. 面向用户可单独调用的进阶分析能力，通常落在 `recipes`。
2. 若需要新增导出格式或查询封装，通常需要联动 `msprof_analyze/prof_exports`。
3. 若涉及数据库读取和通用工具，优先复用 `msprof_analyze/prof_common`。

#### 3.4.4 开发自定义 Recipe 分析能力

新增 Recipe 时，建议遵循现有规则：

1. 在 `msprof_analyze/cluster_analyse/recipes` 下创建同名目录和同名 Python 文件。
2. 继承 `BaseRecipeAnalysis` 并实现 `run` 函数。
3. 需要额外参数时，实现 `add_parser_argument`。
4. 若需要新增数据库查询封装，可在 `msprof_analyze/prof_exports` 中新增导出类。

详细开发方式请参见：

- `docs/zh/advanced_features/custom_analysis_guide.md`

### 3.5 本地运行常用命令

```bash
# 专家建议
msprof-analyze advisor all -d ./prof_data -o ./advisor_output

# 性能比对
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output

# 集群分析
msprof-analyze cluster -m all -d ./cluster_data -o ./cluster_output
```

如需基于源码快速验证命令改动，建议优先采用 `pip install --editable .` 方式运行，而不是每次重新构建 whl 包。

## 4. 测试与验证

### 4.1 单元测试

仓库提供了统一的单元测试入口：

```bash
python3 test/run_ut.py
```

单元测试主要覆盖：

- `advisor`
- `cluster_analyse`
- `compare_tools`
- `prof_common`

运行成功后，会在 `test/report` 下生成测试结果和覆盖率文件。

### 4.2 系统测试

仓库提供了系统测试入口：

```bash
python3 test/run_st.py
```

当前系统测试主要覆盖：

- `advisor`
- `cluster_analyse`
- `compare_tools`

脚本内部采用并行方式拉起各模块测试，并设置了超时控制。

### 4.3 覆盖率统计

如需生成 Python 覆盖率报告，可执行：

```bash
bash test/ut_coverage.sh
```

执行后将在 `test/ut_coverage` 目录下生成：

- `coverage.xml`
- `python_coverage_report.log`
- `final.xml`

若需要比较分支增量覆盖率，可执行：

```bash
bash test/ut_coverage.sh diff master
```

### 4.4 安装包验证

如需验证发布包构建流程，可执行：

```bash
python3 setup.py bdist_wheel
```

构建完成后会在 `dist` 目录下生成：

```text
msprof_analyze-{version}-py3-none-any.whl
```

随后可使用如下命令验证安装：

```bash
pip3 install ./dist/msprof_analyze-{version}-py3-none-any.whl
msprof-analyze --help
```

## 5. 文档联动更新

功能开发完成后，若改动影响用户使用方式或输出结果，需要同步更新文档。

| 改动类型 | 需同步更新的文档 |
| --- | --- |
| 安装、编译、升级方式 | `docs/zh/getting_started/install_guide.md` |
| 快速体验流程 | `docs/zh/getting_started/quick_start.md` |
| Advisor 功能 | `docs/zh/user_guide/advisor_instruct.md` |
| Compare 功能 | `docs/zh/user_guide/compare_tool_instruct.md` |
| Cluster 功能 | `docs/zh/user_guide/cluster_analyse_instruct.md` |
| Recipe 扩展能力 | `docs/zh/advanced_features/README.md` |
| 自定义 Recipe 开发方式 | `docs/zh/advanced_features/custom_analysis_guide.md` |
| 版本发布信息 | `docs/zh/release_notes.md` |

## 6. 提交流程建议

1. 在功能开发完成后，先执行本地安装验证。
2. 至少完成一轮 `UT`，必要时补充 `ST`。
3. 若涉及用户可见行为变化，同步补充文档和示例命令。
4. 若新增分析能力，说明其输入数据要求、输出文件和适用场景。
