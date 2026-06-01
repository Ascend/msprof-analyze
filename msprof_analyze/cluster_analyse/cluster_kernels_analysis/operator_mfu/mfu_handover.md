# MFU 采集侧重构 — 交接文档

> **归档说明（2026-06-01）**：本文是迁移前交接稿，其中列出的采集侧文件已从 `msprof-analyze` 移除并迁移到 `torch_npu.profiler`。当前实现详见 `docs/zh/design/MFU采集与计算重构设计文档.md`。

## 一、已完成工作

### 1. 新增文件

| 文件 | 职责 | 状态 |
|------|------|------|
| [npu_flop_registry.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/npu_flop_registry.py) | 自定义 FLOPs 注册表 + `register_npu_flop` 装饰器 + `get_flop_func` 查找函数 | ✅ 已完成并测试 |
| [mfu_hook_manager.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_hook_manager.py) | Monkey-patch Hook 管理器（安装/卸载/包含关系判定/线程安全） | ✅ 已完成并测试 |
| [npu_flop_formulas.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/npu_flop_formulas.py) | 昇腾算子 FLOPs 公式（首批：`npu_fusion_attention`） | ✅ 已完成并测试 |
| [mfu_refactor_design.md](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_refactor_design.md) | 重构设计文档 | ✅ 已完成 |

### 2. 修改文件

| 文件 | 变更内容 | 状态 |
|------|----------|------|
| [mfu_calculator.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_calculator.py) | 新增 `_calculate_mfu_from_recorded_flops` 方法，优先从 `mfu_flops` domain 读取 FLOPs；旧逻辑保留为 `_legacy` 后缀方法，作为 fallback | ✅ 已完成 |
| [mfu_export.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/prof_exports/mfu_export.py) | 新增 `MfuFlopsExport` 类和 `QUERY_MFU_FLOPS` SQL，查询 `domain='mfu_flops'` 的 mstx marker | ✅ 已完成 |
| [__init__.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/__init__.py) | 导出公共 API：`register_npu_flop`、`get_flop_func`、`MFUHookManager`、`MFUCalculator`；自动加载 `npu_flop_formulas` | ✅ 已完成 |

### 3. 测试结果

| 测试项 | 结果 |
|--------|------|
| 模块导入 | ✅ 全部通过 |
| FLOPs 公式（BNSD full/BSND/BSH/TND/causal） | ✅ 数值与旧 `operator_flops.py` 一致 |
| HookManager 安装/卸载 | ✅ 正确 patch 和 restore |
| HookManager 嵌套调用检测 | ✅ 栈非空时正确跳过记录 |
| HookManager 线程安全 | ✅ `threading.local()` 隔离各线程调用栈 |
| 解析侧新路径（`mfu_flops` domain） | ✅ SQL 和数据流已实现 |
| 解析侧旧路径 fallback | ✅ 无 `mfu_flops` mark 时自动 fallback |

## 二、架构概览

```
采集侧（训练进程内）
┌──────────────────────────────────────────────────────┐
│  register_npu_flop("npu_fusion_attention")           │
│  → 注册到 _npu_flop_registry                         │
│                                                      │
│  MFUHookManager.install({                            │
│      "npu_fusion_attention": (torch_npu, "npu_fusion_attention")│
│  })                                                  │
│  → monkey-patch 替换原始函数                          │
│                                                      │
│  调用 torch_npu.npu_fusion_attention(q, k, v, ...)   │
│  → wrapper 被触发                                     │
│    ├─ 检查调用栈（包含关系判定）                      │
│    ├─ get_flop_func("npu_fusion_attention")          │
│    │   → 先查 _npu_flop_registry                     │
│    │   → 再查 torch flop_registry                    │
│    ├─ flops = flop_func(q, k, v, ...)                │
│    ├─ mstx.mark(str(flops), domain="mfu_flops")      │
│    └─ 调用原始函数，返回结果                          │
│                                                      │
│  MFUHookManager.uninstall()                          │
│  → 恢复原始函数                                      │
└──────────────────────────────────────────────────────┘

解析侧（msprof-analyze）
┌──────────────────────────────────────────────────────┐
│  MFUCalculator.run()                                 │
│  ├─ 查询 MSTX_EVENTS 中 domain="mfu_flops" 的 mark  │
│  ├─ 有数据 → _calculate_mfu_from_recorded_flops()    │
│  │   → flops 直接从 mark message 读取                │
│  │   → MFU = flops / (duration × chip_peak)          │
│  └─ 无数据 → fallback 到旧逻辑（策略公式计算）       │
└──────────────────────────────────────────────────────┘
```

## 三、使用方式

### 采集侧（用户代码）

```python
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu import (
    MFUHookManager,
)

# 定义要 hook 的算子
target_ops = {
    "npu_fusion_attention": (torch_npu, "npu_fusion_attention"),
}

# 开启 profiler 时安装 hook
MFUHookManager.install(target_ops)

try:
    with torch_npu.profiler.profile(...) as prof:
        # 训练代码
        # 每次 npu_fusion_attention 调用都会自动计算 FLOPs 并写入 mstx mark
        pass
finally:
    # 关闭 profiler 时卸载 hook
    MFUHookManager.uninstall()
```

### 注册新的 FLOPs 公式

```python
from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu import register_npu_flop

@register_npu_flop("npu_matmul")
def npu_matmul_flops(a, b, **kwargs):
    m, k = a.shape
    k2, n = b.shape
    return m * n * k * 2
```

## 四、后续规划

### P0 — 必须完成（阻塞上线）

1. **torch_npu 侧集成**：在 `torch_npu.profiler._ExperimentalConfig` 中添加 `record_mfu` 配置项，profiler 开启/关闭时自动调用 `MFUHookManager.install()/uninstall()`
2. **MatMul 算子 FLOPs 公式**：在 `npu_flop_formulas.py` 中添加 `npu_bmmV2` 等 MatMul 类算子的 FLOPs 注册
3. **端到端集成测试**：在真实昇腾环境中验证采集→解析全流程

### P1 — 重要优化

4. **更多算子支持**：逐步添加 Conv、Softmax、LayerNorm 等算子的 FLOPs 公式
5. **性能测试**：评估 monkey-patch hook 对训练性能的影响
6. **scaled_dot_product_attention 兼容**：用户通过 `torch.nn.functional.scaled_dot_product_attention` 调用时，也需要能触发 FLOPs 记录

### P2 — 长期优化

7. **代码迁移**：将采集侧代码（`mfu_hook_manager.py`、`npu_flop_registry.py`、`npu_flop_formulas.py`）从 msprof-analyze 迁移到 torch_npu 仓库
8. **旧逻辑清理**：确认新路径稳定后，移除 `operator_flops.py` 中的策略计算代码和 `flash_attn_args` 相关逻辑
9. **`flop_counter` 注册兼容**：支持将自定义公式同时注册到 `torch.utils.flop_counter.flop_registry`，实现统一管理

## 五、已知限制

1. **当前仅支持 `npu_fusion_attention`**：MatMul 等算子的 FLOPs 公式尚未注册
2. **Profiler 开关未集成**：`_ExperimentalConfig.record_mfu` 需要在 torch_npu 仓库中实现
3. **未在真实昇腾环境测试**：mstx.mark 的写入和读取需要实际环境验证
4. **NZ 格式 MatMul 未支持**：`npu_flop_formulas.py` 中的 MatMul 公式需要支持昇腾 NZ 格式
5. **flop_counter registry 查找依赖 torch**：`get_flop_func` 的 fallback 路径需要 torch 可用，在纯解析环境中会跳过

## 六、关键文件索引

| 文件 | 说明 |
|------|------|
| [mfu_refactor_design.md](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_refactor_design.md) | 设计文档 |
| [npu_flop_registry.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/npu_flop_registry.py) | FLOPs 注册表 |
| [mfu_hook_manager.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_hook_manager.py) | Hook 管理器 |
| [npu_flop_formulas.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/npu_flop_formulas.py) | FLOPs 公式 |
| [mfu_calculator.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_calculator.py) | 解析侧 MFU 计算（已适配） |
| [mfu_export.py](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/prof_exports/mfu_export.py) | DB 查询（已新增 MfuFlopsExport） |
