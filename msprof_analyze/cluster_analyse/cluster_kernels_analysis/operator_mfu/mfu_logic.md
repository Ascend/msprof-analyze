# MFU（Model FLOPs Utilization）采集与计算逻辑

> **归档说明（2026-06-01）**：本文描述迁移前解析侧方案。当前实现以 `torch_npu.profiler` 的 `record_flops=True` 采集和 `mfu_flops` domain 解析为准，详见 `docs/zh/design/MFU采集与计算重构设计文档.md`。

## 一、概述

MFU（Model FLOPs Utilization，模型算力利用率）衡量的是算子实际执行的计算量占芯片理论峰值算力的比例。当前支持对 **MatMul** 和 **FlashAttention** 两类核心算子进行 MFU 计算。

核心公式：

```
MFU = 算子FLOPs / (算子执行耗时(s) × 芯片理论峰值FLOPS)
```

## 二、整体数据流

```
用户训练代码（mstx打点）
        │
        ▼
torch_npu.profiler 采集（export_type=Db, mstx=True, profiler_level≥level1）
        │
        ▼
Profiler DB（COMPUTE_TASK_INFO / TASK / MSTX_EVENTS / STRING_IDS 等表）
        │
        ▼
msprof-analyze（module_statistic recipe）
        │
        ▼
MFUCalculator.run() → 输出每个 kernel 的 MFU 值
```

## 三、数据采集（用户侧）

### 3.1 Profiler 配置

用户需使用 `torch_npu.profiler` 采集性能数据，关键配置如下：

```python
experimental_config = torch_npu.profiler._ExperimentalConfig(
    export_type=[torch_npu.profiler.ExportType.Db],  # 必须导出DB格式
    mstx=True,                                        # 开启mstx打点事件采集
    profiler_level=torch_npu.profiler.ProfilerLevel.Level1  # level1及以上才采集shape信息
)

with torch_npu.profiler.profile(
    activities=[torch_npu.profiler.ProfilerActivity.CPU, torch_npu.profiler.ProfilerActivity.NPU],
    experimental_config=experimental_config,
    on_trace_ready=torch_npu.profiler.tensorboard_trace_handler("./result_data")
) as prof:
    # 训练代码
    pass
```

### 3.2 MatMul 算子——无需额外打点

MatMul 算子的 MFU 计算所需信息（input_shapes、input_types、output_shapes）由 Profiler 在 `level1` 及以上等级自动采集，存储在 `COMPUTE_TASK_INFO` 表中。**用户无需额外编写打点代码。**

### 3.3 FlashAttention 算子——需要 mstx mark 打点

FlashAttention 算子除了 shape 信息外，还需要额外的参数（`input_layout`、`sparse_mode`、`actual_seq_qlen`、`actual_seq_kvlen`），这些参数无法从 Profiler 自动采集中获取，**必须由用户通过 `mstx.mark` 打点手动记录**。

打点方式：在调用 FlashAttention 接口前，通过 `torch_npu.npu.mstx.mark` 将参数以 JSON 字符串写入 `flash_attn_args` domain。

#### 针对 `torch_npu.npu_fusion_attention` 接口

```python
import json
import torch_npu

original_npu_fusion_attention = torch_npu.npu_fusion_attention
def custom_npu_fusion_attention(*args, **kwargs):
    info = {
        "input_layout": kwargs.get('input_layout'),
        "sparse_mode": kwargs.get('sparse_mode', 0),
        "actual_seq_qlen": kwargs.get('actual_seq_qlen', []),
        "actual_seq_kvlen": kwargs.get('actual_seq_kvlen', []),
    }
    torch_npu.npu.mstx.mark(message=json.dumps(info), domain='flash_attn_args')
    return original_npu_fusion_attention(*args, **kwargs)
torch_npu.npu_fusion_attention = custom_npu_fusion_attention
```

#### 针对 `torch.nn.functional.scaled_dot_product_attention` 接口

```python
import json
import torch

original_scaled_dot_product_attention = torch.nn.functional.scaled_dot_product_attention
def custom_scaled_dot_product_attention(*args, **kwargs):
    info = {
        "is_causal": kwargs.get('is_causal', False)
    }
    torch_npu.npu.mstx.mark(message=json.dumps(info), domain='flash_attn_args')
    return original_scaled_dot_product_attention(*args, **kwargs)
torch.nn.functional.scaled_dot_product_attention = custom_scaled_dot_product_attention
```

## 四、数据存储（Profiler DB 中的相关表）

| 表名 | 作用 | 关键字段 |
|------|------|----------|
| `COMPUTE_TASK_INFO` | 计算任务信息 | `name`, `opType`, `inputShapes`, `inputDataTypes`, `outputShapes`, `globalTaskId` |
| `TASK` | 任务执行时间信息 | `globalTaskId`, `startNs`, `endNs` |
| `MSTX_EVENTS` | mstx 打点事件 | `startNs`, `message`, `domainId`, `eventType`, `connectionId` |
| `STRING_IDS` | 字符串映射表 | `id`, `value` |
| `ENUM_MSTX_EVENT_TYPE` | mstx 事件类型枚举 | `id`, `name`（marker=3, range=2） |
| `PYTORCH_API` | PyTorch 框架层 API | `startNs`, `endNs`, `name`, `connectionId` |
| `CONNECTION_IDS` | 连接 ID 映射 | `id`, `connectionId` |
| `device_*/info.json.*` | 芯片设备信息 | `ai_core_num`, `aic_frequency` |

## 五、计算逻辑详解

### 5.1 入口：MFUCalculator.run()

```
MFUCalculator.run()
  ├── 1. ChipPeakFLOPSCalculator 初始化 → 读取芯片信息
  ├── 2. _query_kernel_shapes() → 从 DB 查询所有 kernel 的 shape 信息
  ├── 3. process_common_operator(MATMUL) → 计算 MatMul MFU
  └── 4. process_operator_with_additional_args_mark(FLASH_ATTENTION, 'flash_attn_args') → 计算 FA MFU
```

### 5.2 芯片理论峰值 FLOPS 计算

**文件**: [chip_peak_flops.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/chip_peak_flops.py)

从 `device_*/info.json.*` 文件中读取芯片参数：

```
Peak FLOPS = AICore数量 × AIC频率(MHz) × 每周期操作数 × 10^6
```

每周期操作数按数据类型不同：

| 数据类型 | 每周期操作数公式 | 值 |
|----------|-----------------|-----|
| FLOAT16/BF16 | 16 × 16 × 16 × 2 | 8192 |
| INT8 | 16 × 32 × 16 × 2 | 16384 |

### 5.3 Kernel Shape 信息查询

**文件**: [mfu_export.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/prof_exports/mfu_export.py) → `KernelShapeExport`

通过 SQL 从 `COMPUTE_TASK_INFO` JOIN `TASK` 查询，获取每个 kernel 的：
- `kernel_name`：kernel 名称
- `type`：算子类型（如 MatMulV2、FlashAttentionScore）
- `input_shapes`：输入 tensor 形状
- `input_types`：输入数据类型
- `output_shapes`：输出 tensor 形状
- `kernel_ts` / `kernel_end`：kernel 执行起止时间
- `task_duration`：kernel 执行耗时（ns）

### 5.4 MatMul MFU 计算

**流程**（`process_common_operator`）：

1. 从 shapes_df 中筛选 `type` 为 `MatMulV2` 或 `MatMulV3` 的记录
2. 按 `input_shapes`、`input_types`、`output_shapes` 分组
3. 对每组创建 `MatmulFLOPs` 策略实例，计算 FLOPs
4. 计算 MFU

**FLOPs 公式**（[operator_flops.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/operator_flops.py) → `MatmulFLOPs`）：

```
FLOPs = m × n × k × 2
```

其中 m、n、k 的解析支持两种输入格式：
- **ND 格式**（2维）：`output_shapes[0] = [m, n]`，`k` 从 `input_shapes[0]` 中取与 m 不同的维度
- **NZ 格式**（4维，昇腾特殊排布）：将 4 维 reshape 为 2 维后再按 ND 逻辑解析

### 5.5 FlashAttention MFU 计算

**流程**（`process_operator_with_additional_args_mark`）：

1. 查询 cpu-op 与 device-kernel 的关联关系（`FrameworkOpToKernelExport`）
2. 从 shapes_df 中筛选 `type` 为 `FlashAttentionScore` 的记录
3. 将 kernel 信息与 op-kernel 关联表做 inner join
4. 查询 `MSTX_EVENTS` 中 domain 为 `flash_attn_args` 的 marker 事件
5. **时间对齐**：使用 `pd.merge_asof` 将 mstx marker 与 cpu-op 按时间前向匹配（tolerance=3ms）
6. 去重：每个 kernel 只保留时间最近的 marker
7. 按 `input_shapes`、`input_types`、`operator_args` 分组
8. 对每组创建 `FlashAttentionFLOPs` 策略实例，计算 FLOPs
9. 计算 MFU

**FLOPs 公式**（`FlashAttentionFLOPs`）：

#### 通用 Layout（BNSD/BSND/BSH/SBH）

```
full_attention = 2 × B × N × S_q × S_kv × (D_q + D_kv)
```

根据 `sparse_mode` 调整：
- `sparse_mode=0`：全量 attention，FLOPs = full_attention
- `sparse_mode=2`（causal）或 `sparse_mode=3`（且 S_q==S_kv）：FLOPs = full_attention × 0.5
- 其他情况根据 S_q 与 S_kv 的关系做比例折算

#### TND Layout

```
FLOPs = 2 × N × (D_q + D_kv) × dot(q_lens, kv_lens)
```

其中 `q_lens` 和 `kv_lens` 从 `actual_seq_qlen` / `actual_seq_kvlen` 差分解析得到。

### 5.6 MFU 最终计算

```python
MFU = FLOPs / (task_duration_ns × 1e-9) / chip_peak_FLOPS
```

- `task_duration_ns`：kernel 执行耗时（纳秒），转秒需 ×1e-9
- `chip_peak_FLOPS`：芯片理论峰值（FLOPS/s）
- 结果为 0~1 之间的浮点数，表示算力利用率

## 六、数据类型映射

算子输入数据类型到峰值计算所用数据类型的映射：

| 输入类型 | 映射到 | 说明 |
|----------|--------|------|
| FLOAT / FLOAT16 | FLOAT16 | 半精度 |
| BF16 / DT_BF16 | FLOAT16 | BFloat16 按半精度计算峰值 |
| INT8 | INT8 | 整型 |

## 七、调用入口

MFU 计算由 `module_statistic` recipe 触发，调用链路：

```
msprof-analyze -m module_statistic -d ./result --export_type text
        │
        ▼
ModuleStatisticRecipe._calculate_kernel_mfu()
        │
        ▼
MFUCalculator(data_map, op_kernel_df).run()
```

`op_kernel_df`（cpu-op 与 device-kernel 的关联关系）由 recipe 在调用前预先查询好并传入。

## 八、关键文件索引

| 文件 | 职责 |
|------|------|
| [mfu_calculator.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_calculator.py) | MFU 计算主流程，数据查询与组装 |
| [operator_flops.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/operator_flops.py) | FLOPs 计算策略（MatMul / FlashAttention） |
| [chip_peak_flops.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/chip_peak_flops.py) | 芯片理论峰值 FLOPS 计算 |
| [mfu_export.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/prof_exports/mfu_export.py) | DB 查询：KernelShapeExport、OperatorArgsExport |
| [module_statistic_export.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/prof_exports/module_statistic_export.py) | DB 查询：FrameworkOpToKernelExport（op-kernel关联） |
