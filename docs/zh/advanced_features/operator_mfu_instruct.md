# 算子 MFU 分析

## 简介

算子 MFU 分析（`operator_mfu`）用于基于 Profiling 数据计算算子的模型 FLOPs 利用率（Model FLOPs Utilization，MFU），帮助识别核心计算算子是否充分利用芯片理论算力。

该能力从采集侧写入的 `mfu_flops` MSTX range 中读取算子 FLOPs，再结合 Device 侧 kernel 耗时、kernel 输入数据类型和芯片理论峰值，输出：

* kernel 级 MFU 明细：展示每个有效 kernel 的 MFU、实际 TFLOPS、理论峰值和 FLOPs。
* module 级 MFU 统计：如果采集数据中包含 `Module` domain 的 MSTX range，则按模型层级聚合各算子的平均 MFU。

`operator_mfu` 是独立分析能力，MFU 不再由 `module_statistic` 输出。

## 使用前准备

**环境准备**

完成 msprof-analyze 工具安装，具体请参见《[msprof-analyze工具安装指南](../getting_started/install_guide.md)》。

**数据准备**

1. 配置并采集带 FLOPs range 的 Profiling 数据。

   采集侧在 `torch_npu.profiler.profile` 开启 `with_flops=True` 后，会在 profiler start 阶段安装 FLOPs hook；被支持的算子调用时，hook 会自动计算 FLOPs，并以 `mfu_flops` domain 写入 MSTX range，range message 格式为：

   ```text
   <FLOPs>-<op_name>
   ```

   示例配置如下：

   ```python
   experimental_config = torch_npu.profiler._ExperimentalConfig(
       profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
       aic_metrics=torch_npu.profiler.AiCMetrics.PipeUtilization,
       msprof_tx=True,
       mstx=True,
       data_simplification=False,
       export_type=[
           torch_npu.profiler.ExportType.Text,
           torch_npu.profiler.ExportType.Db,
       ],
   )

   prof = torch_npu.profiler.profile(
       activities=[
           torch_npu.profiler.ProfilerActivity.CPU,
           torch_npu.profiler.ProfilerActivity.NPU,
       ],
       schedule=torch_npu.profiler.schedule(wait=1, warmup=1, active=3),
       on_trace_ready=torch_npu.profiler.tensorboard_trace_handler("./result"),
       record_shapes=True,
       profile_memory=False,
       with_stack=False,
       with_flops=True,
       with_modules=True,
       experimental_config=experimental_config,
   )
   ```

   说明：

   * `with_flops=True` 用于开启采集侧 FLOPs hook。
   * 当前采集侧实现中，自动 FLOPs hook 的触发条件为 `with_flops=True` 且 `msprof_tx=True`。`mstx=True` 是新的 MSTX 参数，示例中同时保留以兼容当前 hook 触发逻辑和 MSTX 采集。
   * `export_type` 必须包含 `Db`，解析侧需要读取 DB 中的 `MSTX_EVENTS`、`PYTORCH_API`、`COMPUTE_TASK_INFO` 和 `TASK` 等表。
   * `record_shapes=True` 用于保留 kernel shape 和数据类型信息。
   * `profiler_level` 建议设置为 `Level1` 及以上，以采集 MFU 计算所需的 kernel 信息。
   * 如果配置了 `mstx_domain_include`，需要包含 `mfu_flops`；如果需要 module 级 MFU 聚合，还需要包含 `Module`。
   * 当前 MFU 计算不再使用 `flash_attn_args` domain 的手动 mark；FlashAttention 的 FLOPs 由采集侧公式根据算子入参自动计算。

2. 添加模型层级 MSTX 打点（可选）。

   如果只需要 kernel 级 MFU 明细，可以不添加模型层级打点。如果需要生成 module 级 MFU 统计，需要在模型代码中调用 `torch_npu.npu.mstx.range_start/range_end`，并使用 `Module` domain 记录模型层级范围。

   ```python
   original_call = nn.Module.__call__

   def custom_call(self, *args, **kwargs):
       module_name = self.__class__.__name__
       mstx_id = torch_npu.npu.mstx.range_start(module_name, domain="Module")
       result = original_call(self, *args, **kwargs)
       torch_npu.npu.mstx.range_end(mstx_id, domain="Module")
       return result

   nn.Module.__call__ = custom_call
   ```

## 算子 MFU 分析

**命令格式**

```bash
msprof-analyze -m operator_mfu -d ./result --export_type text
```

**参数说明**

| 参数 | 可选/必选 | 说明 |
| ---- | --------- | ---- |
| -m | 必选 | 设置为 `operator_mfu`，使能算子 MFU 分析能力。 |
| -d | 必选 | 集群性能数据文件夹路径。 |
| -o | 可选 | 指定输出文件路径。 |
| --export_type | 可选 | 指定输出文件类型，可选 `db` 或 `text`。 |

更多参数详细介绍请参见 msprof-analyze 的[参数说明](./README.md#参数说明)。

**输出说明**

`export_type` 设置为 `text` 时，每张卡最多生成两个 Excel 文件：

* `operator_mfu_kernel_{rank_id}.xlsx`：kernel 级 MFU 明细。
* `operator_mfu_module_{rank_id}.xlsx`：module 级 MFU 统计。仅当采集数据包含 `Module` domain 的 MSTX range 时生成。

`export_type` 设置为 `db` 时，结果保存到 `cluster_analysis.db`：

* `OperatorMFU`：kernel 级 MFU 明细。
* `ModuleMFU`：module 级 MFU 统计。仅当采集数据包含 `Module` domain 的 MSTX range 时写入。

`OperatorMFU` 主要字段如下：

| 字段名称 | 说明 |
| -------- | ---- |
| rankID | Rank ID。 |
| opName | 框架侧算子名称。 |
| kernelName | Device 侧 kernel 名称。 |
| kernelStart(ns) | kernel 开始时间，单位纳秒。 |
| kernelEnd(ns) | kernel 结束时间，单位纳秒。 |
| kernelDuration(ns) | kernel 执行时长，单位纳秒。 |
| mfu | MFU 比值，未乘以 100%。 |
| actual_tflops | 按当前 kernel 时长计算的实际 TFLOPS。 |
| chip_peak_tflops | 按 kernel 输入数据类型匹配到的芯片理论峰值，单位 TFLOPS。 |
| flops | 采集侧记录的算子 FLOPs。 |
| flops_op_name | `mfu_flops` range 中记录的算子名称。 |
| input_shapes | kernel 输入 shape。 |
| output_shapes | kernel 输出 shape。 |

`ModuleMFU` 主要字段如下：

| 字段名称 | 说明 |
| -------- | ---- |
| rankID | Rank ID。 |
| parentModule | 上层 Module 名称。 |
| module | 最底层 Module 名称。 |
| opName | 框架侧算子名称。 |
| kernelList | 框架侧算子下发到 Device 侧执行的 kernel 序列。 |
| totalKernelDuration(ns) | 框架侧算子对应 Device 侧 kernel 运行总时间，单位纳秒。 |
| avgKernelDuration(ns) | 框架侧算子对应 Device 侧 kernel 平均运行时间，单位纳秒。 |
| opCount | 框架侧算子在采集周期内运行的次数。 |
| avgMFU | 按同一 kernel 位置聚合得到的平均 MFU，百分比格式。 |

## 计算逻辑

### 采集侧 FLOPs range

采集侧 `FlopsHookManager` 会在 profiler start 时安装算子 hook，在 profiler stop 时卸载 hook。对于已注册 FLOPs 公式的算子，hook 的执行流程如下：

1. 调用 FLOPs 公式，根据算子入参 shape、layout、group 信息或 attention mask 信息计算 FLOPs。
2. 如果 FLOPs 为非负数，则调用 `torch_npu.npu.mstx.range_start(f"{flops}-{op_name}", domain="mfu_flops")`。
3. 执行原始算子。
4. 调用 `torch_npu.npu.mstx.range_end(range_id, domain="mfu_flops")`。

未注册 FLOPs 公式的算子不会生成 `mfu_flops` range。

### 解析侧 MFU

解析侧 `operator_mfu` 使用以下数据计算 MFU：

* 从 `MSTX_EVENTS` 查询 `mfu_flops` domain 的 range，并解析 message 中的 `<FLOPs>-<op_name>`。
* 从 `PYTORCH_API`、`COMPUTE_TASK_INFO`、`COMMUNICATION_OP`、`COMMUNICATION_SCHEDULE_TASK_INFO` 和 `TASK` 等表查询框架算子到 Device kernel 的关联关系。
* 从 kernel shape 数据中读取 kernel 时长、输入 shape、输出 shape 和输入数据类型。
* 通过 profiler 目录中的芯片信息获取对应数据类型的理论峰值。

MFU 计算公式如下：

```text
actual_tflops = FLOPs / (kernelDuration(ns) * 1e-9) / 1e12
mfu = FLOPs / (kernelDuration(ns) * 1e-9) / chipPeakFLOPS
```

其中 `chipPeakFLOPS` 为当前芯片、当前数据类型对应的理论峰值。解析侧使用同一 `mfu_flops` range 内首个 kernel 的输入数据类型匹配峰值；如果无法解析输入类型，默认按 FP16 处理。

一个 `mfu_flops` range 会匹配其时间范围内启动的框架算子，再关联这些算子下发的 kernel。解析侧会按 `kernel_ts` 和 `kernel_end` 对重复 kernel 去重，并对每个有效 kernel 分别计算 MFU。

## 当前支持的 FLOPs 公式

统一口径：

* 矩阵乘按 multiply-add 计为两次操作，即 `2 * M * K * N`。
* 融合算子默认只统计核心矩阵乘或 Attention 主体。
* 通信、数据重排、transpose、bias、scale、mask、Softmax、dropout、量化/反量化和激活等融合后处理不额外计入 FLOPs。

| 算子 | FLOPs 计算逻辑 |
| ---- | -------------- |
| `torch.mm` | `2 * M * K * N`。 |
| `torch.bmm` | `2 * B * M * K * N`。 |
| `torch.matmul` | 根据向量、矩阵和 broadcast batch 维度解析后计算；通用矩阵场景为 `2 * prod(batch_shape) * M * K * N`。 |
| `torch.nn.functional.linear` | `2 * prod(input.shape[:-1]) * out_features * in_features`。 |
| `torch.addmm` | `2 * M * K * N`，只统计 `mat1 @ mat2`。 |
| `torch_npu.npu_all_gather_base_mm` | `2 * (m_local * world_size) * K * N`，只统计 AllGather 后的 GEMM。 |
| `torch_npu.npu_transpose_batchmatmul` | 先按 `perm_x1/perm_x2` 解析参与 GEMM 的 shape，再按矩阵乘计算；三维 Batch GEMM 场景为 `2 * B * M * K * N`。 |
| `torch_npu.npu_grouped_matmul` | 如果 `x` 和 `weight` 分组一一对应，计算 `sum_i(2 * M_i * K_i * N_i)`；如果一个 `x` 对应多个 `weight`，按 `group_list` 拆分 token 后累加各组 GEMM。 |
| `torch_npu.npu_quant_matmul_gelu` | `2 * total_m * K * N`，只统计量化矩阵乘主体。 |
| `torch_npu.npu_grouped_matmul_swiglu_quant_v2` | `2 * M * K * N`，只统计 Grouped GEMM 主体。 |
| `torch_npu.npu_alltoallv_gmm` | 路由专家 GMM 为 `2 * T_route * H1 * N1`；如果传入共享专家 `mm_x/mm_weight`，额外加 `2 * BS * H2 * N2`。 |
| `torch_npu.npu_gmm_alltoallv` | 路由专家 GMM 为 `2 * T_route * H1 * N1`；如果传入共享专家 `mm_x/mm_weight`，额外加 `2 * BS * H2 * N2`。 |
| `torch_npu.npu_fusion_attention` | 只统计 `Q @ K^T` 和 `P @ V`：`2 * score_elems * q_dim + 2 * score_elems * value_dim`。普通 layout 按 `input_layout` 解析 batch、head、seq 和 head_dim；`TND` layout 使用 `actual_seq_qlen/actual_seq_kvlen` 计算有效序列长度。 |
| `torch_npu.npu_fused_infer_attention_score` | 与 `npu_fusion_attention` 同一口径，支持 `num_heads` 和 `num_key_value_heads`。 |
| `torch_npu.npu_block_sparse_attention` | 只统计有效 block pair 中的 `Q @ K^T` 和 `P @ V`：`2 * score_elems * q_dim + 2 * score_elems * value_dim`，其中 `score_elems` 按 `block_sparse_mask` 中有效块的 `q_tokens * kv_tokens` 累加。 |

Attention 中 `score_elems` 表示实际参与 QK/PV 计算的 attention score 元素数量，已包含 batch 和 head。稠密场景为 `batch * head * q_seq * kv_seq`；因果或稀疏场景会按 `sparse_mode` 或 block mask 减少有效 score 元素数。
