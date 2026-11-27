# Operator MBU Analysis

## Overview

`operator_mbu` estimates kernel-level Model Bandwidth Utilization (MBU) from device-side input/output tensor shapes, data types, and kernel durations. It supports Matmul, FlashAttention, and GroupedMatmul, combines results from all ranks, and does not perform module-level aggregation.

## Prerequisites

Install msprof-analyze following the [installation guide](../install_guide/msprof-analyze_install_guide.md). Collect Profiling data with `record_shapes=True`, `ProfilerLevel.Level1` or higher, and `ExportType.Db`. The exported database must include `COMPUTE_TASK_INFO`, `TASK`, and `STRING_IDS`. Neither `with_flops` nor msTX instrumentation is required.

For example:

```python
experimental_config = torch_npu.profiler._ExperimentalConfig(
    profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
    export_type=[torch_npu.profiler.ExportType.Db],
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

## Usage

```bash
msprof-analyze -m operator_mbu -d ./result --export_type text --chip_peak_bandwidth 1600
```

| Parameter | Description |
| --------- | ----------- |
| `-m` | Set to `operator_mbu`. |
| `-d` | Required parent directory of the collected profiling data. |
| `-o` | Optional output directory; defaults to the input directory. |
| `--export_type` | `db` (default) or `text`. |
| `--chip_peak_bandwidth` | Optional theoretical chip HBM bandwidth in GB/s, taken from the target chip's official specifications. Must be finite and positive; invalid values raise an error. If omitted, MBU and peak bandwidth are empty. |
| `--step_id` | Optional iteration selection. Includes kernels whose start times fall within the selected step's inclusive start/end boundaries. If omitted, all iterations are analyzed. |

## Output

Results are saved under `cluster_analysis_output`:

- `db`: table `OperatorMBU` in `cluster_analysis.db`.
- `text`: file `OperatorMbu/MBU.csv`, with the same data and human-readable column names.

| Database column | Description |
| --------------- | ----------- |
| `rank_id` | Rank identifier. |
| `kernel_name` | Device kernel name. |
| `op_type` | Device operator type. |
| `kernel_start(ns)` / `kernel_end(ns)` | Kernel start/end timestamps. |
| `kernel_duration(ns)` | Kernel duration. |
| `access_bytes` | Estimated input and output tensor bytes combined. |
| `achieved_bandwidth(GB/s)` | Estimated memory traffic divided by kernel duration. |
| `chip_peak_bandwidth(GB/s)` | User-supplied peak HBM bandwidth; empty if omitted. |
| `mbu` | Bandwidth divided by peak bandwidth, without multiplying by 100%; empty if peak bandwidth is omitted. |
| `input_shapes` / `output_shapes` | Input/output tensor shapes. |

## Calculation and Limitations

```text
access_bytes = sum(input tensor bytes) + sum(output tensor bytes)
achieved_bandwidth = access_bytes / (kernel_duration(ns) * 1e-9)
mbu = achieved_bandwidth / chip_peak_bandwidth
```

The formula uses bandwidth in bytes/s internally. Only final output is rounded: bandwidth in GB/s to two decimal places and MBU to four.

Tensor bytes are computed from the shape element count and dtype size. Supported types include FLOAT/FLOAT32 (4 bytes), FLOAT16/BF16 (2), INT8/UINT8/BOOL (1), INT16/UINT16 (2), INT32/UINT32 (4), INT64/UINT64/DOUBLE/FLOAT64 (8), and FP8/HIFLOAT8/FLOAT8_E4M3FN/FLOAT8_E5M2 (1). `DT_` prefixes are supported. INT4/UINT4 use 4 bits per element, rounded up to whole bytes per tensor. Missing or unknown dtypes fall back to 2 bytes; unknown types emit warnings with cached lookups to reduce repetition. This fallback can overestimate or underestimate traffic.

Tensors with non-positive dimensions, empty shapes, or unparsable shapes are skipped. Empty shapes cannot currently be distinguished from missing data or empty separators, so they are not treated as scalar tensors. Partially skipped kernels may underestimate traffic and MBU; kernels with no calculable bytes are omitted. Supply valid shapes before interpreting these results as complete traffic estimates.

Kernels with non-positive durations are omitted. Only identical query records are deduplicated; concurrent tasks with different `globalTaskId` values are retained. Missing calculation columns are reported in the log and analysis of that rank is skipped.

| Operator family | Supported device opTypes |
| --------------- | ------------------------ |
| Matmul | `MatMulV2`, `MatMulV3` |
| FlashAttention | `FlashAttentionScore` |
| GroupedMatmul | `GroupedMatmul`, `GroupedMatMul` |

Other operator types are excluded. For GroupedMatmul, verify whether the collected shapes represent concatenated tensors or repeated groups before interpreting the byte totals.
