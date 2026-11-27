# 算子 MBU 分析

## 1. 简介

算子 MBU 分析（`operator_mbu`）通过 Profiling 数据分析关键算子的模型带宽利用率（Model Bandwidth Utilization，MBU），帮助识别核心算子对芯片理论 HBM 带宽的利用程度。

该功能从 Device 侧 `COMPUTE_TASK_INFO` 中按算子类型（opType）圈定 Matmul / FlashAttention / GroupedMatmul 等关键算子，再由 kernel 的输入/输出 shape 与数据类型计算访存字节，结合 kernel 耗时与芯片理论 HBM 峰值带宽，输出 kernel 级 MBU 明细，支持写入 `cluster_analysis.db` 的 `OperatorMBU` 表或导出为 `MBU.csv`。

与 MFU 不同，MBU 关注访存效率：把“FLOPs / 算力峰值”换成“访存字节 / HBM 带宽峰值”。访存字节由 kernel shape 与 dtype 在解析侧直接算出，**不依赖采集侧 `with_flops` / msTX 打点**，只需常规带 shape 的 Profiling 数据即可。

`operator_mbu` 是独立分析能力，只做 kernel 级分析，不进行 module 级聚合。

## 2. 使用前准备

**环境准备**

完成 msprof-analyze 工具安装，具体请参见《[msprof-analyze工具安装指南](../install_guide/msprof-analyze_install_guide.md)》。

**数据准备**

采集带 kernel shape 信息的 Profiling 数据即可，无需开启 `with_flops` 或 msTX。关键开关：`record_shapes=True`（保留输入/输出 shape 和数据类型）、`profiler_level` 为 `Level1` 及以上、`export_type` 包含 `Db`。

示例配置如下：

```python
experimental_config = torch_npu.profiler._ExperimentalConfig(
    profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
    export_type=[
        torch_npu.profiler.ExportType.Db,
    ],
)

prof = torch_npu.profiler.profile(
    activities=[
        torch_npu.profiler.ProfilerActivity.CPU,
        torch_npu.profiler.ProfilerActivity.NPU,
    ],
    record_shapes=True,
    experimental_config=experimental_config,
    on_trace_ready=torch_npu.profiler.tensorboard_trace_handler("./result"),
)
```

> [!NOTE]
>
> * `record_shapes=True` 用于保留 kernel 的输入/输出 shape 与数据类型信息，这些信息是计算访存字节的必要输入。
> * `export_type` 必须包含 `Db`，解析侧需要读取 DB 中的 `COMPUTE_TASK_INFO` 和 `TASK` 表。
> * `profiler_level` 建议设置为 `Level1` 及以上，以采集 MBU 计算所需的 kernel 信息。

## 3. 功能介绍

**命令格式**

```bash
msprof-analyze -m operator_mbu -d <profiling_path> [-o <output_path>] [--export_type <export_type>] [--chip_peak_bandwidth <GB/s>]
```

**参数说明**

| 参数 | 可选/必选 | 说明 |
| ---- | --------- | ---- |
| -m | 必选 | 设置为 `operator_mbu`，启动算子 MBU 分析。 |
| -d | 必选 | 集群性能数据文件父目录路径。 |
| -o | 可选 | 分析结果输出路径，默认输出在 `-d` 参数指定的目录下。 |
| --export_type | 可选 | 分析结果导出类型，可取 `db` 或 `text`，默认为 `db`。设置为 `db` 时结果写入 `cluster_analysis.db`；设置为 `text` 时生成 `MBU.csv`。 |
| --chip_peak_bandwidth | 可选 | 芯片理论 HBM 峰值带宽，单位 GB/s，必须为有限正数，非法值报错。不传时仅输出访存字节与实测带宽，MBU 列留空。 |
| --step_id | 可选 | 仅分析所选迭代时间范围内开始的 kernel，起止边界均包含；不传时分析全部迭代。 |

更多参数详细介绍请参见 msprof-analyze 的[参数说明](./README.md#51-参数说明)。

> [!NOTE]
> 当前 Profiling 数据（`device/info.json` 等）不包含芯片型号与 HBM 峰值带宽信息，因此峰值带宽需由用户按目标芯片的官方规格通过 `--chip_peak_bandwidth` 传入；未传入时 MBU 无法计算，但访存字节与实测带宽仍会输出。

**使用示例**

```bash
msprof-analyze -m operator_mbu -d ./result --export_type text --chip_peak_bandwidth 1600
```

**输出说明**

msprof-analyze 会在 `-o` 参数指定路径下生成 `cluster_analysis_output` 文件夹，在该文件夹生成如下结果：

* `--export_type` 设置为 `text` 时，生成如下文件：

    * `OperatorMbu/MBU.csv`：所有 rank 合并后的 kernel 级 MBU 明细，含 `Rank ID` 列以区分各卡。

* `--export_type` 设置为 `db` 时，生成 `cluster_analysis.db` 文件，在该文件中生成如下表：

    * `OperatorMBU`：所有 rank 合并后的 kernel 级 MBU 明细，含 `rank_id` 列以区分各卡。

具体文件介绍请参见[输出结果文件说明](#4-输出结果文件说明)。

## 4. 输出结果文件说明

如下字段以 `cluster_analysis.db` 文件为例。`MBU.csv` 的内容与之相同，仅列名改为首字母大写的表头风格，例如 `achieved_bandwidth(GB/s)` 对应 `Achieved Bandwidth(GB/s)`；缩写保持全大写，例如 `rank_id` 对应 `Rank ID`、`mbu` 对应 `MBU`。

`OperatorMBU` 主要字段如下：

| 字段名称 | 说明 |
| -------- | ---- |
| rank_id | Rank ID。 |
| kernel_name | Device 侧 kernel 名称。 |
| op_type | Device 侧算子类型（如 `MatMulV2`、`FlashAttentionScore`、`GroupedMatmul`）。 |
| kernel_start(ns) | kernel 开始时间，单位 ns。 |
| kernel_end(ns) | kernel 结束时间，单位 ns。 |
| kernel_duration(ns) | kernel 执行时长，单位 ns。 |
| access_bytes | kernel 的访存字节数，等于输入张量字节与输出张量字节之和。 |
| achieved_bandwidth(GB/s) | 按当前 kernel 时长计算的实际访存带宽，单位 GB/s。 |
| chip_peak_bandwidth(GB/s) | 由 `--chip_peak_bandwidth` 传入的芯片理论 HBM 峰值带宽，单位 GB/s；未传入时为空。 |
| mbu | MBU 比值（未乘以 100%）；未传入峰值带宽时为空。 |
| input_shapes | kernel 输入 shape。 |
| output_shapes | kernel 输出 shape。 |

## 5. 计算逻辑

### 5.1 关键算子圈定

解析侧从 `COMPUTE_TASK_INFO` 读取每个 kernel 的 opType，按算子类型圈定关键算子：

* Matmul：`MatMulV2`、`MatMulV3`
* FlashAttention：`FlashAttentionScore`
* GroupedMatmul：`GroupedMatmul`、`GroupedMatMul`

非上述类型的算子不会出现在 `MBU.csv` 中。该方式不依赖采集侧 `with_flops` / msTX Range。

### 5.2 访存字节口径

`operator_mbu` 按输入/输出张量字节之和估算一次 kernel 的访存量：

```text
access_bytes = Σ输入张量字节 + Σ输出张量字节
```

每个张量的字节数由其 shape 元素个数乘以数据类型字节数得到，即 `prod(shape) * dtype_size(dtype)`。其中 `dtype_size` 按数据类型映射到每元素字节数（如 `FLOAT`/`FLOAT32` 为 4 字节，`FLOAT16`/`BF16` 为 2 字节，`INT8`/`FP8`/`HIFLOAT8`/`FLOAT8_E4M3FN`/`FLOAT8_E5M2` 为 1 字节，`INT64`/`DOUBLE` 为 8 字节）。`INT4`/`UINT4` 按每元素 4 bit、每个张量向上取整到完整字节估算。支持 `DT_` 前缀；缺失或未知 dtype 仍按 FP16（2 字节）回退，未知类型会记录告警并缓存查询结果以减少重复告警，回退值可能使结果偏高或偏低。

**shape 限制：** 含动态/非法维度（小于等于 0，如 -1）、空 shape 或解析失败的张量均跳过。当前输入格式不能区分空 shape 是标量、缺失信息还是空分隔段，因此暂不将空 shape 按标量的一个元素计算。一个 kernel 中只累加可解析的张量，跳过部分张量可能低估访存字节及 MBU；全部跳过时该 kernel 不输出。遇到这些情况应补充有效 shape 后重新分析，不应将部分张量的结果视为完整访存量。

### 5.3 MBU

MBU 计算公式如下：

```text
achieved_bandwidth = access_bytes / (kernelDuration(ns) * 1e-9)
mbu = achieved_bandwidth / chipPeakBandwidth
```

其中 `chipPeakBandwidth` 来自 `--chip_peak_bandwidth` 参数（GB/s，内部换算为 Byte/s 参与计算）。输出结果中的实测带宽与芯片峰值带宽均以 GB/s 输出，MBU 比值为无量纲。当 kernel 时长或访存字节非法（小于等于 0）时，该 kernel 不计入结果；解析侧仅去除完全重复的查询记录，保留 `globalTaskId` 不同的并发任务。未传入 `--chip_peak_bandwidth` 时，MBU 与 Chip Peak Bandwidth 列留空，仅输出访存字节与实测带宽。计算阶段保留原始精度，输出时带宽保留两位小数、MBU 保留四位小数。

## 6. 当前支持的算子

| 算子族 | Device 侧 opType |
| ---- | ---- |
| Matmul | `MatMulV2`、`MatMulV3` |
| FlashAttention | `FlashAttentionScore` |
| GroupedMatmul | `GroupedMatmul`、`GroupedMatMul` |

> [!NOTE]
> Matmul 与 FlashAttention 按 kernel 记录的输入/输出张量字节求和估算，不代表硬件实测 HBM 流量。GroupedMatmul 的访存字节口径取决于采集侧记录分组 shape 的方式（整段拼接张量 vs 逐组重复），建议结合含该算子的真实 Profiling 数据校验后再作为最终口径。
