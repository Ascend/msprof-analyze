# MFU 采集侧重构设计文档

> **归档说明（2026-06-01）**：本文是迁移前设计草稿。采集侧已经迁移到 `torch_npu.profiler`，当前实现详见 `docs/zh/design/MFU采集与计算重构设计文档.md`。

## 一、背景

当前 MFU（Model FLOPs Utilization）的计算完全在解析侧（msprof-analyze）完成。解析侧从 Profiler DB 的 `COMPUTE_TASK_INFO` 表中读取 kernel 的 shape 信息，再通过 FLOPs 策略公式计算 FLOPs，最后除以 `duration × chip_peak` 得到 MFU。

这种方式存在以下问题：

- FlashAttention 等算子需要用户手动通过 `mstx.mark` 打点记录额外参数（`input_layout`、`sparse_mode` 等），用户负担重
- 解析侧需要维护复杂的 FLOPs 计算策略，且每新增一个算子都要同时修改采集侧打点和解析侧计算
- 时间对齐逻辑（`merge_asof`）复杂且不够精确

## 二、重构目标

将 FLOPs 计算从解析侧前移到采集侧：

1. 在采集侧通过 monkey-patch hook 拦截昇腾算子调用
2. 使用注册的 FLOPs 公式直接计算 FLOPs
3. 通过 `mstx.mark` 将 FLOPs 值写入 Profiler 数据
4. 解析侧直接读取 FLOPs 值，不再自行计算

## 三、整体架构

```
采集侧（训练进程内）
┌─────────────────────────────────────────────────┐
│  torch_npu.profiler.profile() 开启              │
│  └─ _ExperimentalConfig(record_mfu=True)        │
│       │                                         │
│       ▼                                         │
│  MFUHookManager.install()                       │
│  └─ monkey-patch 目标算子 → wrapped_function    │
│       │                                         │
│       ▼                                         │
│  用户代码调用 torch_npu.npu_fusion_attention()  │
│  └─ wrapped_function 被调用                      │
│       ├─ 调用栈深度检查（包含关系判定）          │
│       ├─ 从 flop_registry 查找 FLOPs 公式       │
│       ├─ 计算FLOPs → mstx.mark(flops, "mfu_flops")│
│       └─ 调用原始算子，返回结果                  │
│                                                 │
│  torch_npu.profiler.profile() 关闭              │
│  └─ MFUHookManager.uninstall()                  │
└─────────────────────────────────────────────────┘

解析侧（msprof-analyze）
┌─────────────────────────────────────────────────┐
│  MFUCalculator.run()                            │
│  └─ 从 MSTX_EVENTS 读取 domain="mfu_flops" 的  │
│     marker 事件，message 即为 FLOPs 值          │
│  └─ 从 COMPUTE_TASK_INFO 获取 input_types       │
│     （用于确定 chip_peak 数据类型）              │
│  └─ MFU = FLOPs / (duration_ns × 1e-9) / peak  │
└─────────────────────────────────────────────────┘
```

## 四、模块设计

### 4.1 自定义 FLOPs Registry（`npu_flop_registry.py`）

独立的 FLOPs 公式注册表，与 `torch.utils.flop_counter.flop_registry` 解耦。

```python
# 注册表
_npu_flop_registry: dict[str, Callable] = {}

def register_npu_flop(op_name: str):
    """装饰器，注册昇腾算子的 FLOPs 计算公式"""
    def decorator(func):
        if op_name in _npu_flop_registry:
            raise RuntimeError(f"Duplicate registration for {op_name}")
        _npu_flop_registry[op_name] = func
        return func
    return decorator

def get_flop_func(op_name: str):
    """查找 FLOPs 计算函数，依次查自定义 registry 和 flop_counter registry"""
    if op_name in _npu_flop_registry:
        return _npu_flop_registry[op_name]
    # fallback: 查 flop_counter 的 registry
    from torch.utils.flop_counter import flop_registry
    for key, func in flop_registry.items():
        if getattr(key, '__name__', None) == op_name or str(key) == op_name:
            return func
    return None
```

**注册示例**：

```python
@register_npu_flop("npu_fusion_attention")
def npu_fusion_attention_flops(query, key, value, *, input_layout, sparse_mode=0,
                                actual_seq_qlen=None, actual_seq_kvlen=None, **kwargs):
    # 直接接收 tensor 参数，内部提取 shape
    ...
```

### 4.2 Hook 管理器（`mfu_hook_manager.py`）

负责 monkey-patch 的安装和卸载，以及调用栈跟踪。

```python
class MFUHookManager:
    _local = threading.local()  # 线程安全的调用栈

    @classmethod
    def install(cls, target_ops: dict[str, Callable]):
        """安装 hook，target_ops = {op_name: original_func}"""

    @classmethod
    def uninstall(cls):
        """卸载 hook，恢复原始函数"""

    @classmethod
    def _wrapped_function(cls, op_name, original_func):
        """生成 wrapped 函数，使用 bool 标志防止嵌套调用重复记录 FLOPs"""
```

**包含关系判定逻辑**：

- 使用 `threading.local()` 维护一个 bool 标志 `_local.in_hook`
- 进入 wrapped 函数时，检查 `in_hook` 是否为 `True`
  - `True` → 嵌套调用，直接执行原始函数并返回（guard clause）
  - `False` → 最外层调用，设置 `in_hook = True`，执行原始函数后记录 FLOPs，`finally` 中重置为 `False`
- 内层调用不会进入 `try/finally`，不存在误重置标志的问题

### 4.3 FLOPs 计算与 mstx 记录

wrapped 函数的核心逻辑：

```python
def _wrapped_function(op_name, original_func):
    def wrapper(*args, **kwargs):
        if getattr(cls._local, 'in_hook', False):
            return original_func(*args, **kwargs)

        cls._local.in_hook = True
        try:
            result = original_func(*args, **kwargs)
            flop_func = get_flop_func(op_name)
            if flop_func is not None:
                try:
                    flops = flop_func(*args, **kwargs)
                    torch_npu.npu.mstx.mark(message=str(flops), domain='mfu_flops')
                except Exception as e:
                    logger.warning(f"Failed to compute flops for {op_name}: {e}")
            else:
                logger.warning(f"No FLOPs formula registered for {op_name}")
            return result
        finally:
            cls._local.in_hook = False

    return wrapper
```

### 4.4 Profiler 开关

在 `torch_npu.profiler._ExperimentalConfig` 中新增 `record_mfu` 配置项（此部分在 torch\_npu 仓库中实现，本次先在 msprof-analyze 中预留接口）。

```python
# torch_npu 侧（本次不实现，仅预留接口）
class _ExperimentalConfig:
    def __init__(self, ..., record_mfu=False):
        self.record_mfu = record_mfu
```

### 4.5 解析侧适配

修改 `MFUCalculator`，从 mstx mark 中直接读取 FLOPs 值，不再通过策略公式计算。

**新增 SQL 查询**：

```sql
SELECT
    mstx.startNs,
    str_msg.value AS flops
FROM
    MSTX_EVENTS mstx
LEFT JOIN
    STRING_IDS str_msg ON mstx.message = str_msg.id
LEFT JOIN
    STRING_IDS str_domain ON mstx.domainId = str_domain.id
LEFT JOIN
    ENUM_MSTX_EVENT_TYPE mstx_type ON mstx_type.id = mstx.eventType
WHERE
    mstx_type.name = 'marker' AND str_domain.value = 'mfu_flops'
ORDER BY mstx.startNs
```

**MFU 计算逻辑变化**：

- 旧：`FLOPs = 策略公式计算(shape, dtype, args)` → `MFU = FLOPs / (duration × peak)`
- 新：`FLOPs = mstx mark 中的值` → `MFU = FLOPs / (duration × peak)`
- 数据类型仍从 `COMPUTE_TASK_INFO.inputDataTypes` 获取

## 五、文件变更清单

### 新增文件

| 文件                                  | 职责                                        |
| ----------------------------------- | ----------------------------------------- |
| `operator_mfu/npu_flop_registry.py` | 自定义 FLOPs 注册表 + 注册装饰器                     |
| `operator_mfu/mfu_hook_manager.py`  | Hook 管理器（安装/卸载/嵌套调用防护）                    |
| `operator_mfu/npu_flop_formulas.py` | 昇腾算子 FLOPs 公式定义（首批：MatMul、FlashAttention） |

### 修改文件

| 文件                               | 变更内容                             |
| -------------------------------- | -------------------------------- |
| `operator_mfu/mfu_calculator.py` | 适配新的 FLOPs 获取方式（从 mstx 读取而非策略计算） |
| `operator_mfu/__init__.py`       | 导出公共 API                         |
| `prof_exports/mfu_export.py`     | 新增 `MfuFlopsExport` 查询类          |

### 不变文件

| 文件                                | 说明         |
| --------------------------------- | ---------- |
| `operator_mfu/chip_peak_flops.py` | 芯片峰值计算逻辑不变 |
| `operator_mfu/operator_flops.py`  | 保留，兼容旧数据解析 |

## 六、数据流对比

### 旧数据流

```
用户代码 → torch_npu.profiler 采集 → DB(COMPUTE_TASK_INFO + MSTX_EVENTS)
→ msprof-analyze 查询 shape → 策略公式计算 FLOPs → 计算 MFU
```

### 新数据流

```
用户代码 → monkey-patch hook 拦截 → 计算 FLOPs → mstx.mark(flops, "mfu_flops")
→ torch_npu.profiler 采集 → DB(COMPUTE_TASK_INFO + MSTX_EVENTS)
→ msprof-analyze 查询 flops → 直接使用 → 计算 MFU
```

## 七、兼容性设计

- 解析侧同时支持新旧两种数据格式
- 优先从 `mfu_flops` domain 读取 FLOPs
- 如果没有 `mfu_flops` mark，fallback 到旧的策略公式计算
- `operator_flops.py` 保留不删除，作为 fallback 使用
