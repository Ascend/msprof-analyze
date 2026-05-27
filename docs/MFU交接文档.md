

# MFU 重构测试——交接文档

> **日期**: 2026-05-27
> **作者**: AI Agent (Codex)
> **状态**: mstx 事件采集问题排查中

---

## 一、任务背景

重构了 MFU（Model FLOPs Utilization）计算逻辑，核心变化：

- **旧方案**：解析 trace_view.json → 拿到算子 type/shape/dtype → 通过策略公式反推 FLOPs → 计算 MFU
- **新方案**：推理阶段通过 operator hook 实时计算 FLOPs → 通过 mstx mark 写入 CANN profiler → trace_view.json 中直接读取 FLOPs → 计算 MFU

**3 个原始需求**：

1. 在测试环境中添加 Profiler 开关（`MFU_RECORD` 环境变量），默认开启
2. 测试整体流程，先确保数据采集到 trace_view.json 中
3. 修改的地方需要充分日志

---

## 二、代码改动清单

### 2.1 核心修改文件（已修改，需保留）

| 文件 | 改动内容 |
|---|---|
| `msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_hook_manager.py` | 添加 MFU_RECORD 环境变量开关、PID 隔离文件输出、mstx 事件记录、8 个算子 hook |
| `msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/npu_flop_formulas.py` | 添加 linear/addmm FLOPs 公式、npu_fused_infer_attention_score 的 GQA 公式 |
| `msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/npu_flop_registry.py` | 注册新的算子 target（如 linear -> torch.nn.functional:linear） |

### 2.2 mfu_hook_manager.py 关键改动说明

```

[Mfu\_refactor\_design.md](file:///c:/Users/admin/20260630/msprof-analyze/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_refactor_design.md)

├── \_MFU\_RECORD\_ENV = "MFU\_RECORD"      # 环境变量开关，默认开启
├── \_MFU\_OUTPUT\_DIR\_ENV = "MFU\_OUTPUT\_DIR"  # 输出目录配置
├── is\_mfu\_enabled()                    # 检查开关状态
│
├── \_build\_target\_ops\_from\_registry()   # 从 registry 读取 targets，构建 hook 目标
│   └── hooks: \['npu\_fusion\_attention', 'npu\_fused\_infer\_attention\_score',
│                'npu\_fused\_infer\_attention\_score\_\_out', 'mm', 'bmm',
│                'matmul', 'linear', 'addmm']
│
├── \_find\_existing\_refs()               # 找到其他模块中对原始函数的引用并替换
│
└── MFUHookManager:
├── install()                       # 安装所有 hook（由 sitecustomize.py 触发）
├── flush\_flops\_to\_file()           # 写入 PID 隔离的 JSON 文件
├── \_enter\_record\_function()        # ★ mstx 三级回退策略
└── \_exit\_record\_function()         # ★ 对应的退出逻辑

```

---

## 三、当前进展

### 3.1 已完成 ✓

| 项目 | 状态 | 说明 |
|---|---|---|
| MFU_RECORD 开关 | ✅ | 环境变量 `MFU_RECORD=1` 默认开启，`MFU_RECORD=0` 关闭 |
| FLOPs 数据采集 | ✅ | 算子 hook 生效，FLOPs 数值正确写入 JSON 文件 |
| PID 隔离输出 | ✅ | 每个进程输出独立文件 `mfu_flops_data_pid{pid}.json` |
| 多算子覆盖 | ✅ | 已覆盖 linear(~146 TFLOPs)、npu_fused_infer_attention_score(~0.001 TFLOPs)、matmul(~0 TFLOPs) 等 |
| sitecustomize.py 注入 | ✅ | hook 在 vllm 进程启动时自动安装 |
| 充分日志 | ✅ | INFO 级别日志覆盖了 hook 安装、调用、FLOPs 计算、文件输出全流程 |

### 3.2 上一次完整测试结果

```

MFU\_RECORD=1 跑 vllm + Qwen2.5-0.5B-Instruct + torch profiler:

linear:                        146.36 TFLOPs (10255 calls)
npu\_fused\_infer\_attention\_score: 0.001 TFLOPs (1080 calls)
matmul:                          0.000 TFLOPs (3 calls)
────────────────────────────────────────
Total: 146.36 TFLOPs

````

FLOPs 数据采集本身是正常工作的。

---

## 四、当前问题：mstx 事件不包含 label 信息

### 4.1 问题现象

mstx `range_start("mfu_flops:103079215104:linear", stream)` 调用成功，但 trace_view.json 中只记录了 mstx 事件的操作类型，**不包含我们传入的 label 字符串**：

```json
// 实际出现在 trace_view.json 中的 mstx 事件：
{
  "ph": "X",
  "name": "mstx_range_start_op",   // ← 只是操作类型，没有 "mfu_flops:xxx:linear"
  "pid": 30354,
  "dur": 13.76,
  "cat": "cpu_op",                  // ← 也没有标记为 mfu 相关的 category
  "args": {
    "Sequence number": -1,
    "Fwd thread id": 0
  }
}
````

**这说明 label 信息在 msprof 解析 raw data → trace\_view\.json 的过程中丢失了。**

### 4.2 排查过程

| 步骤 | 方法                                                 | 结果                                                                             |
| -- | -------------------------------------------------- | ------------------------------------------------------------------------------ |
| 1  | 直接用 `import mstx; mstx.range_start(label)`         | `range_id=0` — CANN profiler 未激活时不生效                                           |
| 2  | 改用 `torch_npu.npu.mstx.range_start(label, stream)` | 同样 `range_id=0`                                                                |
| 3  | 加 `LD_PRELOAD=libmspti.so`                         | `range_id` 正常递增（1,2,3...），mstx 事件出现在 trace\_view\.json 中，共 6660 个——但 label 不保留 |
| 4  | 检查 SQLite 数据库                                      | `ascend_pytorch_profiler_0.db` 和 `analysis.db` 中无 mfu/mstx label 数据            |
| 5  | 搜索 CANN profiler mstx 配置                           | 发现 `_ExperimentalConfig(mstx=False)` — 默认关闭                                    |

### 4.3 关键发现

```python
# torch_npu.profiler._ExperimentalConfig 中有 mstx 开关
# 文件: torch_npu/profiler/experimental_config.py:73
class _ExperimentalConfig:
    def __init__(self, ..., mstx: bool = False, ...):
        #                               ↑ 默认关闭！
```

还有 `mstx_domain_include` 和 `mstx_domain_exclude` 参数用于控制哪些 domain 的 mstx 事件被采集。

### 4.4 推测根因

CANN profiler 的 mstx 事件采集分为两层：

1. **记录层**：`torch_npu.npu.mstx.range_start(label, stream)` 将 label 发送给 CANN runtime
2. **采集层**：msprof/CANN profiler 需要配置 `mstx=True` 才会将 mstx 的 label 数据采集到 raw data 中

目前 vllm 的 `--profiler-config '{"profiler":"torch",...}'` 创建 torch profiler 时，没有传入 `experimental_config=_ExperimentalConfig(mstx=True)`，导致 CANN profiler 虽然记录了 mstx 事件（事件操作类型可见），但 label 信息没有被采集到 raw data → trace\_view\.json 中丢失。

***

## 五、下一步建议

### 方案 A（推荐）：在 vllm profiler 初始化时设置 `mstx=True`

追踪 vllm 创建 torch profiler 的代码路径，确保传入：

```python
from torch_npu.profiler import _ExperimentalConfig

experimental_config = _ExperimentalConfig(mstx=True)
# 将 experimental_config 传入 torch.profiler.profile() 或 CANN profiler 初始化
```

**需要排查**：vllm 的 profiler 创建位置在 vllm\_ascend 插件中，需要找到对应的代码路径。

### 方案 B：通过环境变量启用 mstx

检查是否有环境变量可以全局启用 mstx，类似：

```bash
export ASCEND_PROFILER_MSTX=1
export ASCEND_PROFILER_OPTIONS='{"PROFILE_MSTX":"true"}'
```

### 方案 C：如果 label 确实无法保存在 trace\_view\.json 中

不依赖 label→trace\_view\.json 的路径，改为：

1. 推理阶段：FLOPs 写入 JSON 文件（当前已实现）
2. 分析阶段：从 JSON 文件读取 FLOPs，通过 timestamp + pid 与 trace\_view\.json 中的 mstx\_range\_start\_op/range\_end\_op 事件做关联

但此方案需要额外的关联逻辑，且 mstx 事件如果跟 FLOPs 不通 PID 则需要更复杂的匹配。

***

## 六、测试环境信息

| 项目        | 值                              |
| --------- | ------------------------------ |
| 远程主机      | 192.168.9.123                  |
| SSH 用户    | liuchengju                     |
| Docker 容器 | wgw\_pro                       |
| NPU 设备    | ASCEND\_RT\_VISIBLE\_DEVICES=4 |
| 模型        | /data/Qwen2.5-0.5B-Instruct    |
| vllm 端口   | 8009                           |
| Python 环境 | /usr/local/python3.11.14       |

***

## 七、工作目录文件状态

### 7.1 核心项目代码（保留）

```
msprof_analyze/
└── cluster_analyse/cluster_kernels_analysis/operator_mfu/
    ├── mfu_hook_manager.py      ← 已修改，核心 hook 逻辑
    ├── npu_flop_registry.py     ← 已修改，算子注册
    ├── npu_flop_formulas.py     ← 已修改，FLOPs 公式
    ├── mfu_refactor_design.md   ← 设计文档（未修改）
    └── ...
```

### 7.2 测试脚本（项目根目录下，后续需要清理）

根目录有 **大量测试/排查脚本**，这些都是测试过程中生成的，**后续应删除**：

**test\_\*.py（37 个文件）**— 自动化端到端测试脚本：

| 文件                                              | 用途                     |
| ----------------------------------------------- | ---------------------- |
| `test_mfu_smoke.py`                             | 本地冒烟测试（无 NPU）          |
| `test_mfu_e2e.py`                               | 早期端到端测试                |
| `test_e2e_mfu.py → test_e2e_mfu4.py`            | 各版本端到端测试               |
| `test_e2e_linear.py`                            | linear 算子测试            |
| `test_e2e_fia.py`                               | FusedInferAttention 测试 |
| `test_e2e_mstx.py`                              | mstx 集成测试              |
| `test_e2e_correct_config.py`                    | 正确 profiler config 测试  |
| `test_e2e_out_hook.py`                          | .out 变体 hook 测试        |
| `test_e2e_pid_file.py`                          | PID 隔离文件测试             |
| `test_e2e_flops_file.py`                        | FLOPs 文件输出测试           |
| `test_vllm_final.py / test_vllm_final2.py`      | vllm 完整测试              |
| `test_vllm_complete.py / test_vllm_graceful.py` | vllm 测试                |
| `test_vllm_with_profile_api.py`                 | vllm profiler API 测试   |
| `test_mstx_*.py`（系列）                            | mstx 各种方案测试            |
| `test_no_ldpreload.py`                          | 无 LD\_PRELOAD 方案测试     |
| `test_npu4.py / test_npu_devices.py`            | NPU 设备探测               |
| `test_record_function.py`                       | record\_function 方案测试  |
| `test_mfu_remote.py`                            | 远程测试脚本                 |

**check\_\*.py（53 个文件）**— 排查/调试脚本：

| 文件                           | 用途                             |
| ---------------------------- | ------------------------------ |
| `check_mstx_*.py`（系列）        | mstx API/事件/patch/detail/db 排查 |
| `check_trace_*.py`（系列）       | trace\_view\.json 内容排查         |
| `check_profiler_*.py`（系列）    | profiler 配置排查                  |
| `check_exp_config.py`        | ExperimentalConfig 排查          |
| `check_annotation_detail.py` | annotation 事件详情排查              |
| `check_sqlite_detail.py`     | SQLite 数据排查                    |
| `check_msprof_*.py`          | msprof import/export 排查        |
| `check_vllm_*.py`（系列）        | vllm 状态排查                      |
| `check_fia_*.py`（系列）         | FusedInferAttention 排查         |
| `check_engine_*.py`（系列）      | EngineCore 排查                  |
| ... 等                        | 各种调试排查                         |

**其他辅助脚本（保留/清理判断）**：

| 文件                                             | 说明              |
| ---------------------------------------------- | --------------- |
| `deploy_mfu_to_remote.py`                      | 部署工具脚本，可保留      |
| `kill_remote_vllm.py` / `force_kill_remote.py` | 远程杀进程工具，可保留     |
| `calc_mfu_demo.py` / `calc_full_mfu.py`        | MFU 计算 demo，可保留 |
| `debug_*.py` / `find_*.py`                     | 调试/查找工具，建议清理    |

### 7.3 推荐清理命令

```powershell
# 进入项目根目录
cd c:\Users\admin\20260630\msprof-analyze

# 批量删除测试脚本（请先确认！）
Remove-Item test_*.py -Force
Remove-Item check_*.py -Force
Remove-Item debug_*.py -Force
Remove-Item find_*.py -Force
Remove-Item calc_*.py -Force
Remove-Item setup_*.py -Force
```

***

## 八、人工测试步骤指导

### 前置条件

1. SSH 到远程主机：`ssh liuchengju@192.168.9.123`
2. 进入 Docker 容器：`docker exec -itu root wgw_pro bash`
3. 确认 NPU 可用：`npu-smi info` 查看设备 4 是否空闲

### Step 1：确保远程容器中代码是最新的

在本机（Windows PowerShell）执行：

```powershell
cd c:\Users\admin\20260630\msprof-analyze
python deploy_mfu_to_remote.py
```

如果 `deploy_mfu_to_remote.py` 不可用，手动执行：

```powershell
# 设置变量
$SSH = "liuchengju@192.168.9.123"
$CONTAINER = "wgw_pro"

# 先找到容器中 msprof_analyze 的安装路径
ssh $SSH "docker exec -e MFU_RECORD=0 $CONTAINER python3 -c 'import msprof_analyze; print(msprof_analyze.__file__)'"

# 拷贝文件（假设路径是 /usr/local/python3.11.14/lib/python3.11/site-packages）
scp msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/mfu_hook_manager.py $SSH`:/tmp/
ssh $SSH "docker cp /tmp/mfu_hook_manager.py ${CONTAINER}:/usr/local/python3.11.14/lib/python3.11/site-packages/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/"

scp msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/npu_flop_formulas.py $SSH`:/tmp/
ssh $SSH "docker cp /tmp/npu_flop_formulas.py ${CONTAINER}:/usr/local/python3.11.14/lib/python3.11/site-packages/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/"

scp msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/npu_flop_registry.py $SSH`:/tmp/
ssh $SSH "docker cp /tmp/npu_flop_registry.py ${CONTAINER}:/usr/local/python3.11.14/lib/python3.11/site-packages/msprof_analyze/cluster_analyse/cluster_kernels_analysis/operator_mfu/"
```

### Step 2：确保 sitecustomize.py 已部署

```bash
# 在容器中检查
docker exec wgw_pro python3 -c "import sitecustomize" 2>&1

# 如果报错 ImportError，需要部署：
docker exec wgw_pro bash -c "cat > /usr/local/python3.11.14/lib/python3.11/site-packages/sitecustomize.py << 'EOF'
import os
if os.environ.get('MFU_RECORD', '1').strip().lower() not in ('0', 'false', 'off', 'no'):
    try:
        from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.mfu_hook_manager import MFUHookManager
        MFUHookManager.install()
        print('[MFU] Hooks installed via sitecustomize.py')
    except Exception as e:
        print(f'[MFU] Failed to install hooks: {e}')
EOF"
```

### Step 3：释放 NPU 内存

```bash
# 在容器中杀掉所有残留进程
docker exec wgw_pro bash -c 'kill -9 -1 2>/dev/null'
# 等待 5 秒
sleep 5
```

### Step 4：启动 vllm 服务（带 profiler）

```bash
# 在容器中执行
docker exec -d wgw_pro bash -c '
export ASCEND_RT_VISIBLE_DEVICES=4
export MFU_RECORD=1
export MFU_OUTPUT_DIR=/workspace/vllm_profile
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_ASSETS_CACHE=/tmp/vllm_cache

rm -rf /workspace/vllm_profile

vllm serve /data/Qwen2.5-0.5B-Instruct \
    --port 8009 \
    --profiler-config '"'"'{"profiler":"torch","torch_profiler_dir":"./vllm_profile"}'"'"' \
    --trust-remote-code \
    > /tmp/vllm_server.log 2>&1 &

echo "PID=$!"
'
```

```bash
# 如果在容器中，直接执行 
export ASCEND_RT_VISIBLE_DEVICES=4
export MFU_RECORD=1
export MFU_OUTPUT_DIR=/workspace/vllm_profile
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_ASSETS_CACHE=/tmp/vllm_cache

rm -rf /workspace/vllm_profile

vllm serve /data/Qwen2.5-0.5B-Instruct \
    --port 8009 \
    --profiler-config '{"profiler":"torch","torch_profiler_dir":"./vllm_profile"}' \
    --trust-remote-code \
    > /tmp/vllm_server.log 2>&1 &

echo "PID=$!"
```

``` bash
# 等待服务就绪（约 90-120 秒）
# 检查是否就绪：

docker exec wgw_pro curl -s http://localhost:8009/health
# 返回 HTTP 200 即就绪
```
### Step 5：开始 profiling、发送请求、停止 profiling

```bash 
# ① 如果在容器中开始 profiling
curl -s -X POST http://localhost:8009/start_profile

# ② 发送推理请求（curl 实现，prompt 重复 10 次）
curl -s -X POST http://localhost:8009/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/data/Qwen2.5-0.5B-Instruct",
    "prompt": "Hello world Hello world Hello world Hello world Hello world Hello world Hello world Hello world Hello world Hello world ",
    "max_tokens": 30,
    "temperature": 0
  }'

# ③ 等待 5 秒后停止 profiling，再等待 15 秒让数据落盘（合并为一行）
sleep 5 && curl -s -X POST http://localhost:8009/stop_profile && sleep 15
```

```bash
# ① 开始 profiling
docker exec wgw_pro curl -s -X POST http://localhost:8009/start_profile

# ② 发送推理请求
docker exec wgw_pro python3 -c "
import json, urllib.request
data = json.dumps({
    'model': '/data/Qwen2.5-0.5B-Instruct',
    'prompt': 'Hello world ' * 10,
    'max_tokens': 30,
    'temperature': 0
}).encode()
req = urllib.request.Request(
    'http://localhost:8009/v1/completions',
    data=data,
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req, timeout=120) as resp:
    result = json.loads(resp.read().decode())
    print(result.get('choices', [{}])[0].get('text', 'NO RESULT')[:100])
"

# ③ 等待几秒后停止
sleep 5
docker exec wgw_pro curl -s -X POST http://localhost:8009/stop_profile

# ④ 等待 profiling 数据写入磁盘
sleep 15
```

### Step 6：停止 vllm

```bash
docker exec wgw_pro pkill -TERM -f vllm
sleep 10
```

### Step 7：验证结果

```bash
# ① 查看 mstx 日志（确认 hook 是否调用）
docker exec wgw_pro grep "mstx.range_start" /tmp/vllm_server.log | head -10
# 期望看到：
# [MFU] mstx.range_start: mfu_flops:68719476736:linear, range_id=X
# 如果 range_id=0 说明 mstx 未激活

# ② 查看 FLOPs 数据文件
docker exec wgw_pro python3 -c "
import json, glob
for f in glob.glob('/workspace/vllm_profile/mfu_flops_data_pid*.json'):
    with open(f) as fh:
        d = json.load(fh)
    s = d['summary']
    print(f'{f}: total_flops={s[\"total_flops\"]/1e12:.2f} TFLOPs')
    for op, flops in sorted(s.get('total_flops_by_op', {}).items(), key=lambda x: -x[1]):
        print(f'  {op}: {flops/1e12:.4f} TFLOPs')
"

# ③ 查看 trace_view.json 中的 mstx 事件
PROF_DIR=$(docker exec wgw_pro bash -c 'ls -d /workspace/vllm_profile/rank0*_ascend_pt')
docker exec wgw_pro python3 -c "
import json
with open('$PROF_DIR/ASCEND_PROFILER_OUTPUT/trace_view.json') as f:
    data = json.load(f)
mstx = [e for e in data if 'mstx' in str(e.get('name','')).lower()]
print(f'mstx events: {len(mstx)}')
mfu = [e for e in data if 'mfu' in str(json.dumps(e)).lower()]
print(f'events containing mfu: {len(mfu)}')
# 期望：mfu events > 0
"

# ④ 运行 msprof import 生成 SQLite（可选）
docker exec wgw_pro msprof import -dir $PROF_DIR
```

### Step 8：如果要测试 mstx 开关（当前核心待解决问题）

```bash
# ★ 关键：尝试通过环境变量或配置启用 CANN profiler 的 mstx 采集

# 尝试 1：设置 ASCEND_PROFILER_OPTIONS
docker exec wgw_pro bash -c '
export ASCEND_RT_VISIBLE_DEVICES=4
export ASCEND_PROFILER_OPTIONS='"'"'{"PROFILE_MSTX":"true"}'"'"'
export MFU_RECORD=1

python3 -c "
import torch
import torch_npu
torch.npu.set_device(0)
import mstx

# 创建带 mstx=True 的 profiler
from torch_npu.profiler import _ExperimentalConfig
import torch.profiler

exp_config = _ExperimentalConfig(mstx=True)
with torch.profiler.profile(
    activities=[torch.profiler.ProfilerActivity.CPU],
    experimental_config=exp_config,
) as prof:
    rid = torch_npu.npu.mstx.range_start('test_label_mfu_100', torch_npu.npu.current_stream())
    print(f'range_id={rid}')  # 期望非 0
    torch_npu.npu.mstx.range_end(rid)

print('Done. Check if label appears in profiler output.')
"
'

# 尝试 2：查看 vllm_ascend 的 profiler 实现
docker exec wgw_pro bash -c 'find /usr/local/python3.11.14/lib/python3.11/site-packages/vllm_ascend* -name "*.py" | xargs grep -l "profiler\|profile\|ProfilerConfig" 2>/dev/null'
```

***

## 九、关键调试命令速查

```bash
# 查看 vllm 日志（实时）
docker exec wgw_pro tail -f /tmp/vllm_server.log

# 查看 MFU hook 安装确认
docker exec wgw_pro grep "\[MFU\]" /tmp/vllm_server.log | head -20

# 查看 mstx range_id
docker exec wgw_pro grep "range_start\|range_end" /tmp/vllm_server.log | head -10

# 查看 FLOPs 文件内容
docker exec wgw_pro cat /workspace/vllm_profile/mfu_flops_data_pid*.json

# 查看 profiling 输出目录
docker exec wgw_pro ls -la /workspace/vllm_profile/

# 查看 trace_view.json 大小
docker exec wgw_pro ls -lh /workspace/vllm_profile/rank0*_ascend_pt/ASCEND_PROFILER_OUTPUT/trace_view.json

# 强杀所有容器进程（释放 NPU）
docker exec wgw_pro bash -c 'kill -9 -1 2>/dev/null'

# 查看 NPU 状态
docker exec wgw_pro npu-smi info
```

***

## 十、总结

| 维度                           | 状态                                                   |
| ---------------------------- | ---------------------------------------------------- |
| MFU\_RECORD 开关               | ✅ 已完成，环境变量 `MFU_RECORD`                              |
| FLOPs 数据采集（JSON 文件）          | ✅ 正常工作，146+ TFLOPs                                   |
| mstx 事件记录到 trace\_view\.json | ⚠️ 事件类型可见，**label 丢失**                               |
| 问题定位                         | 已定位到 `_ExperimentalConfig(mstx=False)` 默认关闭          |
| 下一步                          | 需要通过 profiler config 或环境变量启用 CANN profiler 的 mstx 采集 |
| 测试脚本清理                       | 根目录有 90+ 测试/排查脚本，建议清理                                |

