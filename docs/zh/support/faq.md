# 常见问题

## 集群分析时提示 missing analysis DB file (analysis.db)

### 故障现象

执行 `msprof-analyze cluster -d <profiling_path>` 后输出 `missing analysis DB file (analysis.db) for N rank(s) [rank_id,...]; these ranks will be skipped`，这些 rank 会在依赖 `analysis.db` 的分析项中被跳过。若所有 rank 均无 `analysis.db`，`CommunicationGroupMap` 无法生成通信域表，`CommunicationTimeSum` 输出 `Create CommunicationGroupMap table failed! Skip CommunicationTimeSum.` 并跳过。

### 故障原因

`analysis.db` 仅在多卡/集群等存在通信的场景下生成。若只采集了纯计算数据，各 rank 目录下均无该文件，依赖该文件的分析项会被跳过，属于预期行为，并非工具异常。

### 故障处理

1. 检查每个 rank 子目录的 `ASCEND_PROFILER_OUTPUT` 目录下是否存在 `analysis.db`（MindSpore、msProf 数据中为 `communication_analyzer.db`），确认缺失的是全部 rank 还是部分 rank。
2. 检查采集命令或采集配置是否开启通信（HCCL）算子数据采集。未开启时，通信类分析项缺失属于预期行为，如需通信域分析结果请重新采集。
3. 检查目录结构是否符合 [集群输入目录要求](../user_guide/cluster_analyse_instruct.md#23-集群输入目录要求)：`-d` 指向集群根目录，每张卡对应一个 profiling 子目录，目录内保留 `ASCEND_PROFILER_OUTPUT` 和 `profiler_info_{rank_id}.json`。
4. 若确认已开启通信数据采集，检查数据转储或拷贝过程是否遗漏 `analysis.db`（例如仅拷贝了 `ascend_pytorch_profiler_{rank_id}.db`），以及是否为每个 rank 保留了完整的同名文件。

## 集群分析时提示 Cannot determine rank_id for the following paths

### 故障现象

执行 `msprof-analyze cluster -d <profiling_path>` 后输出 `Cannot determine rank_id for the following paths: [...]. Reason: profiler_info_{rank_id}.json is missing or invalid.`，警告中列出的路径不会被用于分析。若随后日志仍输出 `Finish allocate profiling data: N ranks`，说明分析使用的是其余可识别目录的数据（例如 msProf 数据），本次分析结果不包含这些路径的数据。

### 故障原因

工具无法从目录中识别出 rank（通常是 `profiler_info_{rank_id}.json` 缺失、被重命名，或文件名中的 rank 标识不是数字），对应目录会被排除在分析之外。

### 故障处理

1. 进入警告中列出的每个路径，确认 `profiler_info_{rank_id}.json` 存在，且 `profiler_info_` 与 `.json` 之间为纯数字的 rank_id。
2. 确认 `-d` 指向的根目录下只包含本次采集的各 rank 数据，目录结构与 [集群输入目录要求](../user_guide/cluster_analyse_instruct.md#23-集群输入目录要求) 中的示例一致。
