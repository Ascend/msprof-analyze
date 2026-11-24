# 内存快照分析

## 1. 简介

msprof-analyze 通过 `pt-snap` 子命令提供 PyTorch / TorchNPU 内存快照的离线分析能力，同时提供 Python API，无需单独安装快照分析工具。
它通过回放内存分配与释放事件，将 `.pkl` / `.pickle` 快照转换为 SQLite 数据库（SnapshotDB），便于重复查询和生成报告。

主要用途：

- 将内存快照解析为可直接使用 MindStudio Insight 打开的分片数据，进行可视化分析。
- 查看内存变化和峰值，定位高占用事件及对应调用栈。
- 分析指定事件后的存活内存，生成交互式 HTML 调用栈内存树。
- 筛查未释放内存候选，辅助分析生命周期和分配器内存差距。
- 拆分大快照，并支持完整分片数据集的查询。

## 2. 快速上手

下文使用从业务程序采集导出的内存快照 `snapshot.pkl` 作为输入，设备 ID 以 `0` 为例。`snapshot.pkl` 仅为示例文件名，请替换为实际导出的 `.pkl` / `.pickle` 文件路径。

尚未采集快照时，请根据运行设备参考以下指南，在目标业务阶段记录内存分配历史并导出快照：

- GPU / PyTorch：参见 [PyTorch 内存快照采集指南](https://docs.pytorch.org/docs/stable/torch_cuda_memory.html)。
- 昇腾 NPU / TorchNPU：参见 [Ascend PyTorch 内存快照指南](https://gitcode.com/Ascend/pytorch/blob/master/docs/zh/developer_notes/memory_management/memory_snapshot.md)。

### 2.1 分片解析并使用 MindStudio Insight 打开

将 PyTorch / TorchNPU 内存快照解析为 MindStudio Insight 可直接打开的分片数据：

```bash
msprof-analyze pt-snap import snapshot.pkl --events-per-slice 500000 --format msinsight --no-focus
```

操作步骤：

1. 执行上述命令，默认在原始快照旁生成 `snapshot.pkl.msinsight` 目录。`--events-per-slice 500000` 表示每个设备按每片 500000 个真实事件进行分片，`--format msinsight` 指定 MindStudio Insight 可读取的输出格式。
2. 在 MindStudio Insight 中打开生成的 `snapshot.pkl.msinsight` 完整目录，即可对分片解析结果进行可视化分析，无需在界面中重新解析原始 pickle 快照。
3. 移动解析结果或复制到可视化分析环境时，保留目录中的 `manifest.json`、分片数据库及其它文件，并保持原有目录结构。

可用 `--output-dir analysis-output` 指定输出父目录，用 `--device 0` 只解析指定设备。分片解析仍需完整加载原始 pickle，应预留足够内存。

用于 MindStudio Insight 的解析命令必须显式指定 `--format msinsight`；省略该参数时，分片导入默认生成用于命令行分析的原生格式。以下章节介绍单库导入和命令行查询，也可将上述完整目录作为分析目标继续使用。

### 2.2 导入快照

```bash
msprof-analyze pt-snap import snapshot.pkl --no-focus
```

默认在原文件旁生成 `snapshot.pkl.db`。`--no-focus` 表示不改变项目默认分析目标；省略该选项会更新当前工作目录中的 `.pt-snap/focus.json`。

可用 `--output-dir analysis-output` 指定输出父目录。导入可能重建并替换同名数据库，`--no-focus` 不代表禁止覆盖；请使用独立输出目录，避免覆盖需要保留的结果。

### 2.3 查看设备和事件范围

```bash
msprof-analyze pt-snap overview snapshot.pkl.db --json
```

从返回的 `devices` 中确认 `device_id` 和事件范围，再替换后续命令中的设备 ID。已有数据库或完整数据集可从这一步开始。

### 2.4 查看峰值并生成归因报告

```bash
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use memory_peak --json
msprof-analyze pt-snap report peak-memory snapshot.pkl.db --device 0 --metric active --limit 20
```

第一条命令返回各内存指标的峰值及对应事件 ID；第二条生成可读报告，展示所选峰值事件后的活跃内存及调用栈归因。`--metric` 可选 `active`、`allocated`、`reserved`。

### 2.5 生成交互式 HTML 内存树

将 `1234` 替换为前一步返回的实际事件 ID：

```bash
msprof-analyze pt-snap report memory-tree snapshot.pkl.db --device 0 --event-id 1234 --format html > memory-tree.html
```

用浏览器打开 `memory-tree.html`，查看该事件后的存活内存在调用链中的分布。

### 2.6 命令行分片解析与分析

大快照可以按每个设备的真实事件数量分片解析，生成包含 `manifest.json` 和分片数据库的完整数据集：

```bash
msprof-analyze pt-snap import snapshot.pkl --events-per-slice 500000 --no-focus --json
```

默认输出目录为 `snapshot.pkl.pt-snap-native-v2`；`500000` 表示每片的真实事件数量。可添加 `--device 0` 只解析指定设备，或用 `--output-dir analysis-output` 指定输出父目录。分片不会避免初始 pickle 的完整加载，仍需预留足够内存。

后续分析传入完整数据集目录或其中的 `manifest.json`，无需逐个操作分片数据库：

```bash
# 查看数据集状态、设备和分片信息
msprof-analyze pt-snap overview snapshot.pkl.pt-snap-native-v2 --json
msprof-analyze pt-snap metadata snapshot.pkl.pt-snap-native-v2 --json

# 跨分片查询整体峰值，并生成峰值归因报告
msprof-analyze pt-snap query snapshot.pkl.pt-snap-native-v2 --device 0 --template-use memory_peak --json
msprof-analyze pt-snap report peak-memory snapshot.pkl.pt-snap-native-v2 --device 0 --metric active --limit 20

# 检查指定分片中的事件，分片索引从 0 开始
msprof-analyze pt-snap query snapshot.pkl.pt-snap-native-v2 --device 0 --template-use event --slice 1 -n 20 --json
```

`--slice` 用于事件检查，不是所有查询和报告的通用参数。请保留完整数据集及其目录结构；单个分片数据库不能代替完整数据集进行整体分析。也可以对完整数据集设置 `focus`，后续省略目标路径。

### 2.7 拆分快照文件

`split` 生成可独立回放的快照文件，与直接解析为分片数据库不同。以下命令按设备将快照拆为 4 片，默认输出 pickle：

```bash
msprof-analyze pt-snap split snapshot.pkl --slices 4 --output snapshot-slices

# 单独导入其中一个文件，再按普通数据库查询
msprof-analyze pt-snap import snapshot-slices/snapshot__device-0__slice-0.pkl --no-focus
```

也可按每片最多包含的原始 trace 条目数拆分，`--max-entries` 与 `--slices` 必须二选一：

```bash
msprof-analyze pt-snap split snapshot.pkl --device 0 --max-entries 50000 --output snapshot-slices-by-size
```

输出目录必须不存在。可通过 `--format json` 输出便于检查的 JSON 文件，但 `import` 不接受这些 JSON 文件；后续需要导入时使用默认 pickle 格式。单个拆分文件只覆盖相应片段，不能当作完整快照进行整体分析。

### 2.8 常用查询

```bash
# 列出模板，查看指定模板的参数说明
msprof-analyze pt-snap query --list
msprof-analyze pt-snap query --template-info leak_detection

# 筛查未释放内存候选，最多返回 20 行
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use leak_detection -n 20 --json

# 查看各峰值事件处的分配器内存差距
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use allocator_gap --json
```

| 模板 | 用途 |
| --- | --- |
| `memory_peak` | 查看 allocated、active、reserved 峰值及事件 ID |
| `allocation` | 查看随事件变化的内存水位 |
| `event` / `block` | 查询具体内存事件或内存块 |
| `active_blocks_at_event` | 查看指定事件后的活跃内存块 |
| `active_memory_callstack_at_event` | 按调用栈聚合指定事件后的活跃内存 |
| `leak_detection` | 筛查捕获范围内未完成释放的动态内存候选 |

需要反复分析同一目标时，可设置默认目标，后续命令省略路径：

```bash
msprof-analyze pt-snap focus snapshot.pkl.db --device 0
msprof-analyze pt-snap report peak-memory
```

`focus` 会写项目配置；希望保持项目状态不变时，继续显式传入数据库路径即可。

## 3. 使用前准备

### 3.1 环境准备

完成 msprof-analyze 安装，具体请参见《[msprof-analyze 安装指南](../install_guide/msprof-analyze_install_guide.md)》。

使用已集成内存快照分析能力的 msprof-analyze，Python 版本要求为 **3.7.5+**。离线导入和分析不需要安装 PyTorch、CUDA、CANN，也不需要 GPU/NPU；采集快照则需要对应的框架和设备环境。

```bash
msprof-analyze pt-snap --help
```

### 3.2 数据准备与约束

已有 SnapshotDB `.db` 文件可直接分析；已有完整数据集时，可指定数据集目录或 `manifest.json`。只有原始快照时，先执行导入。

> [!NOTE]
>
> 只处理可信的 pickle 文件：反序列化可能执行代码，导入和拆分都不是沙箱。

## 4. 功能介绍

### 4.1 命令总览与公共约定

| 完整命令 | 用途 |
| --- | --- |
| `msprof-analyze pt-snap import` | 将原始快照解析为单库或分片数据库 |
| `msprof-analyze pt-snap split` | 将原始快照拆成可独立回放的文件 |
| `msprof-analyze pt-snap overview` | 查看设备、事件边界及数据集概况 |
| `msprof-analyze pt-snap metadata` | 查看导入元数据和状态 |
| `msprof-analyze pt-snap query` | 发现查询模板、查看参数并执行查询 |
| `msprof-analyze pt-snap report memory-tree` | 生成指定事件后的调用栈内存树 |
| `msprof-analyze pt-snap report peak-memory` | 生成峰值内存归因报告 |
| `msprof-analyze pt-snap focus` | 查看或设置默认分析目标 |
| `msprof-analyze pt-snap config` | 查看或清理旧版全局配置 |
| `msprof-analyze pt-snap capabilities` | 查看版本、全部查询模板及能力契约 |

```bash
msprof-analyze pt-snap --help
msprof-analyze pt-snap --version
msprof-analyze pt-snap report --help
msprof-analyze pt-snap query --help
```

`--version` 可简写为 `-v`，显示内存快照分析组件版本。每个子命令均支持 `--help`；帮助参数应放在对应命令之后。

所有表中列出的叶子命令均支持 `--json`，用于输出机器可读结果；默认输出便于阅读的文本。JSON 的具体结构依命令而异。执行失败时检查退出码和错误信息，不能只判断是否生成了输出文件。`report memory-tree --format html` 不可与 `--json` 同用。

下文的 `TARGET` 表示 `.db`、完整数据集目录或 `manifest.json`。支持省略 `TARGET` 的命令按以下顺序解析目标：显式路径、`PT_SNAP_DB_PATH` 环境变量、从当前目录向上找到的最近 `.pt-snap/focus.json`、旧版全局配置。显式传入目标时，建议同时指定 `--device`；不会自动沿用其他目标的设备配置。多设备数据应明确选择一个设备，工具不会把不同设备的峰值相加。

### 4.2 import：解析快照

语法：`msprof-analyze pt-snap import SNAPSHOT [选项]`。`SNAPSHOT` 为可信的 `.pkl` 或 `.pickle` 文件。

| 参数 | 默认值与说明 |
| --- | --- |
| `--output-dir`, `-o` | 默认原始文件所在目录；指定输出父目录 |
| `--device`, `-d` | 默认处理可用设备；指定时只解析该设备 |
| `--no-focus` | 默认关闭，即导入后更新项目默认目标；开启后跳过该更新 |
| `--force` | 默认关闭；强制重建单库或原生分片结果，不允许替换已有兼容格式输出 |
| `--events-per-slice` | 默认不分片；正整数，指定每设备每片的真实事件数 |
| `--format` | 未指定分片容量时默认 `single-db`；指定容量时默认 `pt-snap-native-v2`；也接受 `msinsight` / `compatibility-v1` |
| `--json` | 输出路径、格式、复用状态等结构化结果 |

`single-db` 不可与 `--events-per-slice` 同用；显式选择 `pt-snap-native-v2` 必须提供该容量。结果满足缓存条件时可复用，`--force` 用于显式重建。兼容格式使用独立的输出冲突检查，输出已存在时应改用新的输出位置。

`msinsight` 格式用于在 MindStudio Insight 中打开解析结果；不支持 OOM 或未知事件类型，遇到此类输入时会报错。

```bash
msprof-analyze pt-snap import snapshot.pkl --device 0 --output-dir analysis-output --no-focus --json
msprof-analyze pt-snap import snapshot.pkl --events-per-slice 500000 --format pt-snap-native-v2 --no-focus
msprof-analyze pt-snap import snapshot.pkl --force --no-focus
```

### 4.3 split：拆分快照

语法：`msprof-analyze pt-snap split SNAPSHOT --output NEW_DIR [拆分策略] [选项]`。

| 参数 | 默认值与说明 |
| --- | --- |
| `--output`, `-o` | 必填，新建输出目录；目录必须不存在，父目录必须存在 |
| `--device`, `-d` | 默认处理可用设备；指定时只拆分该设备 |
| `--slices`, `-s` | 正整数，按设备指定拆分片数；与 `--max-entries` 二选一 |
| `--max-entries`, `-m` | 正整数，按每片原始 trace 条目数拆分；与 `--slices` 二选一 |
| `--format` | 默认 `pickle`；可选 `pickle`、`json` |
| `--json` | 以 JSON 输出拆分结果清单，不改变生成文件的格式 |

两种拆分策略的示例见前文。输出文件名为 `<源文件主名>__device-<设备>__slice-<索引>.pkl` 或 `.json`。`--format json` 控制文件内容，`--json` 控制命令结果，两者用途不同。

### 4.4 overview：查看数据概况

语法：`msprof-analyze pt-snap overview [TARGET] [--json]`。

返回可用设备、事件范围及导入元数据状态；针对数据集还返回格式、状态和分片信息。它不执行内存归因，也不修改目标文件。

```bash
msprof-analyze pt-snap overview snapshot.pkl.db --json
msprof-analyze pt-snap overview snapshot.pkl.pt-snap-native-v2/manifest.json --json
```

### 4.5 metadata：查看导入信息

语法：`msprof-analyze pt-snap metadata [TARGET] [--json]`。

查看导入状态、状态原因和可用的元数据，辅助判断结果的来源及是否可复用。它与 `overview` 的区别是侧重导入记录，而非设备和事件概况。

```bash
msprof-analyze pt-snap metadata snapshot.pkl.db --json
```

### 4.6 query：查询数据

语法：`msprof-analyze pt-snap query [TARGET] [选项]`。

| 参数 | 默认值与说明 |
| --- | --- |
| `--list` | 列出查询模板，不需要分析目标 |
| `--category` | 按 `basic`、`statistical`、`business` 分类筛选模板；单独指定分类时列出该分类 |
| `--template-info` | 查看指定模板的参数、默认值、输出字段和数据集支持信息，不执行查询 |
| `--template-use` | 执行指定模板 |
| `--params` | JSON 对象字符串，传入模板参数；键名区分大小写 |
| `--device` | 指定设备，未指定时按目标配置及可用设备解析 |
| `--slice` | 指定数据集分片索引，仅用于事件检查；不作为通用跨分片筛选条件 |
| `-n` | 默认不限制返回行数；小于等于 0 也表示不限；不等于执行工作量限制 |
| `--exact-total` | 默认关闭；额外计算精确匹配总行数，可能增加查询成本 |
| `--timeout` | 秒；默认读取 `PT_SNAP_QUERY_TIMEOUT`，未设置则不限；小于等于 0 禁用超时 |
| `--max-work-rows` | 数据集工作行数预算，见公共资源限制 |
| `--max-work-bytes` | 数据集工作字节预算，见公共资源限制 |
| `--max-scratch-db-bytes` | 数据集派生数据库预算，见公共资源限制 |
| `--json` | 输出结构化查询结果及可用的完整性信息 |

```bash
msprof-analyze pt-snap query --list --category basic --json
msprof-analyze pt-snap query --template-info event --json
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use event --params '{"min_id":100,"max_id":700,"limit":20,"offset":20}' --exact-total --timeout 10 --json
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use active_blocks_at_event --params '{"event_id":1234,"min_size":1048576}' -n 20 --json
```

示例将 JSON 对象放在单引号中，适用于 Bash 和 PowerShell；其他 shell 需按各自规则转义。示例事件 ID 应替换为实际数据中的有效值。`--params` 中的 `limit` / `offset` 用于模板分页；`-n` 控制调用方返回行数，不能代替分页或工作预算。

#### 4.6.1 全部查询模板

| 模板 | 用途及主要参数 |
| --- | --- |
| `allocation` | 内存水位曲线；`min_id` / `max_id`、`min_allocated` / `min_active` / `min_reserved`、排序和分页 |
| `event` | 事件明细；`id`、事件范围、`action`、`address`、`size`、`stream`、内存水位筛选、`stack_bytes`、排序和分页 |
| `block` | 内存块明细；`id`、`address`、大小范围、`requestedSize`、分配和释放事件范围、排序和分页 |
| `event_frames` | 事件的结构化调用栈帧；必填 `event_id`，`frame_order` 默认 `original`，也可选 `root_first`；不支持完整分片数据集 |
| `memory_peak` | 各指标峰值及事件；可选 `start_id` / `end_id` 限定事件范围 |
| `allocator_gap` | 各峰值事件的同事件内存差距；可选 `start_id` / `end_id` |
| `active_blocks_at_event` | 指定事件后的活跃块；必填 `event_id`，可选 `include_static`、`min_size`、排序和分页 |
| `callstack_analysis` | 按完整调用栈聚合真实的带栈事件；`min_count` 默认 5，`min_size` 默认 0，可选 `limit` |
| `active_memory_callstack_at_event` | 指定事件后的调用栈内存聚合；必填 `event_id`，`include_static=true`、`min_size=0`、`top_n=20`、`stack_bytes=-1` |
| `active_memory_frame_tree_at_event` | 指定事件后的调用帧内存树；必填 `event_id`，可选 `include_static=true`、`min_size=0` |
| `leak_detection` | 未完成释放的捕获期分配候选；`min_size` 默认 0，可选 `limit` |
| `freed_block_lifetime` | 按分配至释放的事件距离统计已释放块；无模板参数，距离不是时间 |
| `preexisting_live` | 指定事件处仍存活的采集前分配；必填 `event_id` |

除 `event_frames` 外，上表模板均声明支持完整分片数据集。具体字段、排序枚举和边界语义以 `--template-info` 输出为准。支持完整数据集不代表可以把任意单片当作完整快照；数据缺少相应调用栈信息时，也无法恢复原始结构化帧。

### 4.7 report memory-tree：调用栈内存树

语法：`msprof-analyze pt-snap report memory-tree [TARGET] --event-id ID [选项]`。

| 参数 | 默认值与说明 |
| --- | --- |
| `--event-id` | 必填，分析该事件执行后的活跃内存 |
| `--device`, `-d` | 指定设备 |
| `--include-static` / `--exclude-static` | 默认包含静态组；选择是否包含静态内存 |
| `--min-size` | 默认 0，单个内存块的最小字节数 |
| `--format` | 默认 `text`；可选 `text`、`html`，均输出到标准输出 |
| `--timeout` | 查询期限，单位秒；小于等于 0 禁用 |
| `--max-work-rows` / `--max-work-bytes` / `--max-scratch-db-bytes` | 与 `query` 共用数据集资源限制，见后文 |
| `--json` | 输出结构化报告，只能与文本格式同用 |

```bash
msprof-analyze pt-snap report memory-tree snapshot.pkl.db --device 0 --event-id 1234 --exclude-static --min-size 1048576
msprof-analyze pt-snap report memory-tree snapshot.pkl.db --device 0 --event-id 1234 --format html > memory-tree.html
msprof-analyze pt-snap report memory-tree snapshot.pkl.pt-snap-native-v2 --device 0 --event-id 1234 --json
```

报告支持单库和完整数据集；调用树能提供的信息取决于数据中的调用帧。HTML 输出通过重定向保存，用浏览器打开。

### 4.8 report peak-memory：峰值归因

语法：`msprof-analyze pt-snap report peak-memory [TARGET] [选项]`。

| 参数 | 默认值与说明 |
| --- | --- |
| `--device`, `-d` | 指定设备 |
| `--metric` | 默认 `active`；可选 `active`、`allocated`、`reserved`，用于选择峰值事件 |
| `--include-static` / `--exclude-static` | 默认包含静态内存组 |
| `--limit`, `-n` | 默认 20，限制动态调用栈组数；静态组和采集前存活组额外展示 |
| `--stack-bytes` | 默认 -1 保留完整调用栈；0 只保留身份信息，正数限制每条调用栈文本的 UTF-8 字节数 |
| `--start-id` / `--end-id` | 可选，限定寻找峰值的真实事件范围 |
| `--timeout` | 整份报告共享的期限，单位秒；小于等于 0 禁用 |
| `--max-work-rows` / `--max-work-bytes` / `--max-scratch-db-bytes` | 与 `query` 共用数据集资源限制，见后文 |
| `--json` | 输出结构化报告，包括覆盖和截断等信息 |

```bash
msprof-analyze pt-snap report peak-memory snapshot.pkl.db --device 0 --metric reserved --start-id 100 --end-id 700 --limit 20 --stack-bytes 2048 --timeout 10 --json
```

选定指标决定在哪个事件做归因，报告仍分析该事件后的活跃内存；不能把调用栈归因总量直接当作 `reserved` 总量。`--stack-bytes` 不限制整份 JSON 大小，也不是 token 上限。

### 4.9 查询与报告的公共资源限制

以下参数适用于 `query`、`report memory-tree` 和 `report peak-memory`，限制完整数据集分析的中间工作量。它们不限制初始 pickle 加载内存，也不等于进程 RSS 上限。

| 参数 | 默认值 | 环境变量与约束 |
| --- | --- | --- |
| `--max-work-rows` | 100000 | `PT_SNAP_MAX_WORK_ROWS`；正整数，累计获取/输出的工作行数 |
| `--max-work-bytes` | 67108864（64 MiB） | `PT_SNAP_MAX_WORK_BYTES`；正整数，累计序列化工作字节数 |
| `--max-scratch-db-bytes` | 536870912（512 MiB） | `PT_SNAP_MAX_SCRATCH_DB_BYTES`；0 禁用派生数据库，否则范围为 4096～4294967296 |

显式参数优先于对应环境变量。预算不足时根据错误定位需要调整的项目；仅增大 `-n` 不会放宽工作预算。报告组合中的多个查询共享相应预算。查询和报告的 `--timeout` 未显式设置时读取 `PT_SNAP_QUERY_TIMEOUT`，未设置该变量则不限制时间。

### 4.10 focus：默认分析目标

语法：`msprof-analyze pt-snap focus [TARGET] [选项]`。

| 参数 | 默认值与说明 |
| --- | --- |
| `TARGET` | 省略且未传设备时查看当前目标；传入时设置目标 |
| `--device`, `-d` | 设置设备；只传设备时更新当前目标的设备配置 |
| `--session` | 验证路径并打印本会话所需的 shell `export`，不会直接修改父进程环境；不可与 `--device`、`--global` 同用 |
| `--global` | 保存到旧版全局配置；默认保存到当前项目 `.pt-snap/focus.json` |
| `--json` | 查看结构化状态；会话模式返回环境变量信息 |

```bash
msprof-analyze pt-snap focus --json
msprof-analyze pt-snap focus snapshot.pkl.db --device 0
msprof-analyze pt-snap focus --device 1
msprof-analyze pt-snap focus snapshot.pkl.pt-snap-native-v2 --session --json
msprof-analyze pt-snap focus snapshot.pkl.db --global --device 0
```

`--session` 的文本输出采用 POSIX shell 语法。PowerShell 用户可读取其 JSON 结果中的路径并设置 `$env:PT_SNAP_DB_PATH`。会话路径不携带设备配置，后续命令需显式传入设备。

### 4.11 config：旧版全局配置管理

语法：`msprof-analyze pt-snap config [选项]`。此命令操作旧版全局配置，不负责清除项目 focus 或环境变量。

| 参数 | 说明 |
| --- | --- |
| 无选项 | 查看全局配置内容 |
| `--path` | 显示全局配置文件路径 |
| `--clear` | 清除全局配置；不会删除分析数据库 |
| `--json` | 输出结构化结果 |

```bash
msprof-analyze pt-snap config --json
msprof-analyze pt-snap config --path
msprof-analyze pt-snap config --clear
```

`--path` 和 `--clear` 应分别执行；同时传入时优先显示路径，不执行清除。

### 4.12 capabilities：查看能力清单

语法：`msprof-analyze pt-snap capabilities [--json]`。不需要分析目标。

默认列出组件版本、模板分类、描述和参数名；JSON 结果进一步包含参数契约、输出结构、字段语义及数据集支持声明，适合在自动化调用前检查能力。

```bash
msprof-analyze pt-snap capabilities --json
```

## 5. 输出结果说明

### 5.1 输出文件

| 操作 | 默认输出 | 查看方式 |
| --- | --- | --- |
| 单库导入 | `snapshot.pkl.db` | 传入 `overview`、`query` 或 `report` |
| 原生分片导入 | `snapshot.pkl.pt-snap-native-v2/` | 保留目录及全部成员，以目录或 `manifest.json` 为目标 |
| MindStudio Insight 格式导入 | `snapshot.pkl.msinsight/` | 使用 MindStudio Insight 打开完整目录；命令行分析也可传入目录或 `manifest.json` |
| 拆分快照 | `--output` 指定目录下的 `.pkl` / `.json` | pickle 文件可分别重新导入；JSON 文件用于检查 |
| HTML 内存树 | 标准输出，通过重定向保存 | 浏览器打开生成的 HTML 文件 |
| JSON 查询和报告 | 标准输出 | 自动化读取，检查完整性和截断标记 |

### 5.2 结果解读与注意事项

- 内存大小以字节为单位，`1 MiB = 1,048,576 bytes`；事件 ID 表示事件顺序，不是时间戳。
- `allocated` 是已分配 block 的大小；`active` 还包含等待释放完成的 block；`reserved` 是分配器持有的 segment 总量，不代表整个进程或设备的全部内存。
- 各指标的峰值可能发生在不同事件，不能直接相减。使用 `allocator_gap` 或峰值报告查看同一事件的差值；差值大本身不能证明碎片或泄漏。
- `leak_detection` 给出候选，不代表已确认泄漏。报告受筛选和数量限制时可能不完整，应检查覆盖率，以及 JSON 中的 `has_more`、`truncated`、`total_is_exact` 等字段。
- 内建查询和报告只读源数据库；导入、拆分和设置 focus 会写文件。导入会完整加载 pickle，大快照需要预留足够内存。

其他命令和参数可通过 `msprof-analyze pt-snap <命令> --help` 查看。

## 6. Python API

```python
from pathlib import Path
from msprof_analyze.pt_snap import SnapshotAnalyzer

with SnapshotAnalyzer(db_path=Path("snapshot.pkl.db"), device_id=0) as analyzer:
    result = analyzer.execute_query("memory_peak")
    print(result["rows"])
```

使用 `with` 确保分析完成后释放数据库连接。
