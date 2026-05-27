# vllm-ascend 服务模式 Profiling 采集操作指南

## 环境信息

| 项目 | 值 |
|---|---|
| 远程服务器 | 192.168.9.123 |
| 用户名/密码 | liuchengju / liuchengju |
| 容器 | docker exec -itu root wgw_pro bash |
| vllm-ascend 版本 | 0.18.0rc1 |
| 模型路径 | /data/models/Qwen3-8B/ |
| 可用 NPU 卡 | ASCEND_RT_VISIBLE_DEVICES=1（仅1卡） |
| 服务端口 | 8009 |

---

## 〇、从本地 Windows 远程操作服务器

本指南所有命令都需要在远程服务器的容器内执行。从本地 Windows 连接服务器有两种方式：

### 方式一：直接 SSH + docker exec（适合交互式操作）

```bash
ssh liuchengju@192.168.9.123
docker exec -itu root wgw_pro bash
```

### 方式二：paramiko Python 脚本（推荐，适合自动化批量操作）

本地 Windows 安装 paramiko 后，通过 Python 脚本远程执行容器内命令，避免 SSH 密钥交互和 shell 引号嵌套问题。

```bash
pip install paramiko
```

封装远程执行函数：

```python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.9.123', username='liuchengju', password='liuchengju')

def run(cmd, timeout=300):
    full_cmd = f"docker exec wgw_pro bash -c '{cmd}'"
    print(f">>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(full_cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(f"[STDERR] {err}")
    return out, err
```

后续所有章节中的容器内命令，都可以通过 `run()` 函数远程执行，例如：

```python
# 查看数据目录
run("ls -la /workspace/vllm_profile/")

# 解析 profiling 数据
run("msprof import -dir /workspace/vllm_profile/rank0_*_ascend_pt/")

# 运行 msprof-analyze
run("msprof-analyze advisor all -d /workspace/vllm_profile/rank0_*_ascend_pt/ -pt pytorch")

ssh.close()
```

> **提示**：命令中含单引号时，需转义为 `\'` 或改用双引号。复杂 JSON 参数建议写入脚本文件再执行。

### 方式三：smart-terminal 工具（适合 AI Agent 自动化操作）

使用 MCP smart-terminal 工具进行交互式 SSH 连接，适合在 AI Agent 环境中自动化执行远程命令。

#### 完整操作流程

```
步骤 1: 启动终端会话
┌─────────────────────────────────────────────────────────────┐
│ terminal_start                                              │
│   参数: cwd (工作目录, 可选)                                  │
│   返回: sessionId (必须保存，后续操作都需要)                   │
└─────────────────────────────────────────────────────────────┘

步骤 2: 发送 SSH 连接命令
┌─────────────────────────────────────────────────────────────┐
│ terminal_write                                               │
│   参数: sessionId, data: "ssh 用户名@服务器IP"                 │
│ terminal_send_key                                            │
│   参数: sessionId, key: "Enter"                              │
└─────────────────────────────────────────────────────────────┘

步骤 3: 首次连接处理（仅首次需要）
┌─────────────────────────────────────────────────────────────┐
│ terminal_read → 若输出包含 "Are you sure you want to continue"│
│ terminal_write → data: "yes"                                │
│ terminal_send_key → key: "Enter"                             │
└─────────────────────────────────────────────────────────────┘

步骤 4: 输入密码
┌─────────────────────────────────────────────────────────────┐
│ terminal_read → 等待出现 "password:" 提示                     │
│ terminal_write → data: "密码"                               │
│ terminal_send_key → key: "Enter"                             │
│ 注意: 密码输入是静默的，不会显示回显                           │
└─────────────────────────────────────────────────────────────┘

步骤 5: 执行远程命令
┌─────────────────────────────────────────────────────────────┐
│ terminal_write → data: "命令内容"                            │
│ terminal_send_key → key: "Enter"                             │
│ terminal_read → 获取命令输出结果                              │
│   参数: timeout (建议 3000-5000ms)                           │
│         idleTimeout (建议 1000-2000ms)                       │
└─────────────────────────────────────────────────────────────┘

步骤 6: 关闭会话（可选）
┌─────────────────────────────────────────────────────────────┐
│ terminal_stop                                                │
│   参数: sessionId                                            │
└─────────────────────────────────────────────────────────────┘
```

#### 示例：连接服务器并查看 Docker 容器

```
# 1. 启动终端
terminal_start(cwd="C:\\Users\\admin\\workspace")
→ sessionId: "fab6fbf2"

# 2. SSH 连接
terminal_write(sessionId="fab6fbf2", data="ssh liuchengju@192.168.9.123")
terminal_send_key(sessionId="fab6fbf2", key="Enter")

# 3. 确认密钥（首次连接）
terminal_read(sessionId="fab6fbf2") → "Are you sure you want to continue?"
terminal_write(sessionId="fab6fbf2", data="yes")
terminal_send_key(sessionId="fab6fbf2", key="Enter")

# 4. 输入密码
terminal_read(sessionId="fab6fbf2") → "password:"
terminal_write(sessionId="fab6fbf2", data="liuchengju")
terminal_send_key(sessionId="fab6fbf2", key="Enter")

# 5. 执行命令
terminal_write(sessionId="fab6fbf2", data="docker ps")
terminal_send_key(sessionId="fab6fbf2", key="Enter")
terminal_read(sessionId="fab6fbf2", timeout=5000) → 获取容器列表

# 6. 进入容器
terminal_write(sessionId="fab6fbf2", data="docker exec -itu root wgw_pro bash")
terminal_send_key(sessionId="fab6fbf2", key="Enter")

# 7. 关闭会话
terminal_stop(sessionId="fab6fbf2")
```

#### 关键参数说明

| 参数 | 说明 | 建议值 |
|------|------|--------|
| `sessionId` | 会话标识，由 `terminal_start` 返回 | 必须保存并复用 |
| `timeout` | 读取超时时间 | 3000-5000 ms |
| `idleTimeout` | 空闲超时时间 | 1000-2000 ms |
| `key` | 特殊按键 | `Enter`, `Tab`, `Escape`, `Ctrl-C` 等 |

#### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 命令无响应 | `timeout` 设置过短 | 增加 timeout 到 5000ms 以上 |
| 密码输入失败 | 密码输入是静默的 | 输入后直接 Enter，无需等待回显 |
| 会话丢失 | sessionId 错误 | 确保 sessionId 正确传递 |
| 输出被截断 | 未调用 `terminal_read` | 每次命令后调用 `terminal_read` 获取完整输出 |

---

## 一、启动 vllm 服务（带 Profiler）

### 完整启动命令

```bash
export ASCEND_RT_VISIBLE_DEVICES=1

vllm serve /data/models/Qwen3-8B/ \
  --enable_prefix_caching \
  --port 8009 \
  --async-scheduling \
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"./vllm_profile"}'
```

### 关键参数说明

| 参数 | 说明 |
|---|---|
| `--profiler-config` | **必须添加**，否则 `/start_profile` 和 `/stop_profile` 端点不会注册（返回 404） |
| `"profiler":"torch"` | 指定 profiler 类型为 torch，启用 Ascend PyTorch Profiler |
| `"torch_profiler_dir":"./vllm_profile"` | profiling 数据输出目录（相对于 /workspace/） |

### --profiler-config 完整字段

```
ProfilerConfig(
  profiler='torch',                    # profiler 类型，必须设置
  torch_profiler_dir='',               # 输出目录
  torch_profiler_with_stack=False,     # 是否记录调用栈
  torch_profiler_with_flops=False,     # 是否记录 FLOPS
  torch_profiler_use_gzip=True,        # 是否 gzip 压缩
  torch_profiler_dump_cuda_time_total=True,
  torch_profiler_record_shapes=False,  # 是否记录 tensor 形状
  torch_profiler_with_memory=False,    # 是否记录内存
  ignore_frontend=False,
  delay_iterations=0,
  max_iterations=0,
  warmup_iterations=0,
  active_iterations=5,
  wait_iterations=0,
)
```

### 启动验证

启动后日志中应出现以下关键信息，表示 profiling 端点已注册：

```
(APIServer pid=xxx) INFO ... [async_llm.py:191] Torch profiler enabled. AsyncLLM CPU traces will be collected under /workspace/vllm_profile
(APIServer pid=xxx) WARNING ... [api_router.py:41] Profiler with mode 'torch' is enabled in the API server. This should ONLY be used for local development!
```

### 后台启动方式

```bash
# 写入脚本文件（避免 shell 引号嵌套问题）
cat > /tmp/start_vllm_profiler.sh << 'EOF'
#!/bin/bash
export ASCEND_RT_VISIBLE_DEVICES=1
vllm serve /data/models/Qwen3-8B/ \
  --enable_prefix_caching \
  --port 8009 \
  --async-scheduling \
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"./vllm_profile"}'
EOF

chmod +x /tmp/start_vllm_profiler.sh
nohup /tmp/start_vllm_profiler.sh > /tmp/vllm_profiler.log 2>&1 &
```

> **注意**：如果通过 SSH 远程执行，JSON 引号容易在多层 shell 嵌套中被破坏，建议用 base64 编码或写入脚本文件的方式避免。

---

## 二、Profiling 采集操作

### 标准流程：启动采集 → 发送请求 → 停止采集

```bash
# ① 开始 profiling
curl -X POST http://localhost:8009/start_profile
# 返回 200 表示成功

# ② 发送推理请求（根据需要选择 API）
# Completions API
curl -X POST http://localhost:8009/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"/data/models/Qwen3-8B/","prompt":"Beijing is a","max_tokens":20,"temperature":0}'

# Chat Completions API
curl -X POST http://localhost:8009/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"/data/models/Qwen3-8B/","messages":[{"role":"user","content":"Hello"}],"max_tokens":20}'

# ③ 停止 profiling
curl -X POST http://localhost:8009/stop_profile
# 返回 200 表示成功，数据会异步写入磁盘
```

### Python 脚本方式（推荐，避免 curl 引号问题）

```python
import urllib.request
import json
import time

# ① 开始 profiling
req = urllib.request.Request('http://localhost:8009/start_profile', method='POST')
resp = urllib.request.urlopen(req)
print(f"start_profile: {resp.status}")

# ② 发送推理请求
data = json.dumps({
    "model": "/data/models/Qwen3-8B/",
    "prompt": "Beijing is a",
    "max_tokens": 20,
    "temperature": 0
}).encode()
req2 = urllib.request.Request(
    'http://localhost:8009/v1/completions',
    data=data,
    headers={'Content-Type': 'application/json'}
)
resp2 = urllib.request.urlopen(req2)
result = json.loads(resp2.read())
print(f"completion: {json.dumps(result, indent=2)}")

# ③ 等待推理完成后停止 profiling
time.sleep(3)
req3 = urllib.request.Request('http://localhost:8009/stop_profile', method='POST')
resp3 = urllib.request.urlopen(req3)
print(f"stop_profile: {resp3.status}")

# ④ 等待 profiling 数据写入磁盘
time.sleep(10)
```

---

## 三、Profiling 数据输出

### 目录结构

数据保存在 `/workspace/vllm_profile/` 目录下：

```
/workspace/vllm_profile/
├── dc1903d4f8fc_<pid>.async_llm.<ts>.pt.trace.json.gz   # AsyncLLM CPU trace（PyTorch profiler 格式）
└── rank0_<pid>_<timestamp>_ascend_pt/                    # Ascend NPU profiling 数据
    ├── ASCEND_PROFILER_OUTPUT/
    │   └── trace_view.json                                # ★ 算子级 trace（Chrome Trace 格式，可用 msprof-analyze 分析）
    ├── PROF_<id>_<timestamp>_<random>/
    │   ├── host/                                          # Host 侧数据
    │   │   ├── info.json
    │   │   └── sample.json
    │   └── device_1/                                      # Device 侧数据
    │       ├── info.json
    │       └── sample.json
    ├── FRAMEWORK/                                         # 框架层数据
    ├── logs/                                              # Profiling 日志
    ├── profiler_metadata.json
    └── profiler_info_0.json
```

### 关键文件说明

| 文件 | 大小 | 说明 |
|---|---|---|
| `ASCEND_PROFILER_OUTPUT/trace_view.json` | ~24MB | **核心文件**，包含 NPU 算子级耗时数据，可用 msprof-analyze 分析 |
| `*.async_llm.*.pt.trace.json.gz` | ~800B | AsyncLLM CPU 侧 trace |
| `profiler_metadata.json` | - | Profiling 元数据 |

### trace_view.json 数据格式示例

```json
[
  {"ph": "X", "name": "Event::synchronize", "pid": 2687, "tid": 2687, "ts": "...", "dur": 297.34, "cat": "cpu_op", ...},
  {"ph": "X", "name": "aten::as_strided", "pid": 2687, "tid": 2687, "ts": "...", "dur": 36.7, "cat": "cpu_op", ...},
  {"ph": "X", "name": "aten::slice", "pid": 2687, "tid": 2687, "ts": "...", "dur": 62.83, "cat": "cpu_op", ...}
]
```

---

## 四、常见问题排查

### 1. /start_profile 返回 404 Not Found

**原因**：启动 vllm 时未添加 `--profiler-config` 参数，profiling 端点未注册。

**解决**：启动时添加 `--profiler-config '{"profiler":"torch","torch_profiler_dir":"./vllm_profile"}'`。

### 2. --profiler-config JSON 解析失败

**原因**：多层 shell 引号嵌套导致 JSON 被截断。

**解决**：
- 写入脚本文件再执行（推荐）
- 使用 base64 编码传递
- 使用 heredoc：`cat > /tmp/script.sh << 'EOF' ... EOF`

### 3. curl 发送请求返回 "Method Not Allowed" 或 "Unsupported Media Type"

**原因**：curl 在多层 shell 嵌套中 `-H` 头或 `-d` 数据被破坏。

**解决**：使用 Python urllib/requests 发送请求，或将 JSON 数据写入文件后用 `curl -d @/tmp/req.json` 发送。

### 4. 日志出现 "Incorrect schedule: Stop profiler while current state is RECORD"

**原因**：在 profiling 仍在 RECORD 状态时停止，可能导致数据不完整。

**解决**：在 `start_profile` 和 `stop_profile` 之间多等几秒，确保有足够的 wait/warmup 迭代。

### 5. 日志出现 "Failed to get acl to npu flow events"

**原因**：CANN profiling 数据解析时的非致命警告，通常不影响 trace_view.json 的生成。

**解决**：可忽略，检查 trace_view.json 是否正常生成即可。

---

## 五、msprof 解析 Profiling 数据

采集完成后，使用 CANN 自带的 `msprof` 工具解析原始数据，生成 CSV、SQLite 等可分析文件。

### 解析命令

```bash
PROF_DIR=$(ls -d /workspace/vllm_profile/rank0*_ascend_pt)

# ① 解析原始数据，生成 sqlite 和 csv
msprof import -dir $PROF_DIR

# ② 导出完整分析结果
msprof --export=on --output=$PROF_DIR
```

> **注意**：`msprof import` 可能报 `[ERROR] Running profiling failed`，但 sqlite 和 csv 文件已正常生成，可忽略。

### 解析后生成的文件（ASCEND_PROFILER_OUTPUT/ 目录）

| 文件 | 大小 | 说明 |
|---|---|---|
| `trace_view.json` | ~24MB | NPU 算子级 trace（Chrome Trace 格式） |
| `op_statistic.csv` | ~1KB | **算子类型统计**，含 OP Type、Core Type、Count、Total Time、Ratio |
| `kernel_details.csv` | ~3.4MB | **算子内核详情**，含每个算子实例的流水线利用率 |
| `operator_details.csv` | ~1.1MB | **算子执行详情**，含 Host/Device 耗时 |
| `api_statistic.csv` | ~4KB | **CANN API 统计**，含 acl 层 API 耗时 |
| `step_trace_time.csv` | ~227B | **迭代轨迹**，含 Computing/Communication/Free 时间 |
| `ascend_pytorch_profiler_0.db` | ~9.4MB | SQLite 数据库 |
| `analysis.db` | ~8KB | 分析数据库 |

### op_statistic.csv 关键字段

```
Device_id,OP Type,Core Type,Count,Total Time(us),Min Time(us),Avg Time(us),Max Time(us),Ratio(%)
1,MatMulV2,AI_CORE,2820,238282.08,29.06,84.497,846.28,84.677
1,FusedInferAttentionScore,MIX_AIC,720,15562.12,20.5,21.614,24.68,5.53
1,split_qkv_rmsnorm_rope_kernel_2,AI_VECTOR_CORE,684,7425.8,9.56,10.856,14.72,2.639
```

| 字段 | 说明 |
|---|---|
| `OP Type` | 算子类型（如 MatMulV2、FusedInferAttentionScore） |
| `Core Type` | 执行单元：AI_CORE（矩阵计算）、AI_VECTOR_CORE（向量计算）、MIX_AIC（混合） |
| `Count` | 调用次数 |
| `Total Time(us)` | 总耗时（微秒） |
| `Ratio(%)` | 耗时占比，**>40% 可能存在瓶颈** |

---

## 六、msprof-analyze 性能分析

解析后的数据可用 `msprof-analyze` 进行深度性能分析和优化建议。

### 安装（容器内）

```bash
pip install msprof-analyze
```

### 运行分析

```bash
PROF_DIR=$(ls -d /workspace/vllm_profile/rank0*_ascend_pt)

# 全维度分析（调度 + 计算 + 通信）
msprof-analyze advisor all -d $PROF_DIR -pt pytorch

# 仅分析调度（算子下发、融合算子时间线）
msprof-analyze advisor schedule -d $PROF_DIR -pt pytorch

# 仅分析计算（算子性能、图结构）
msprof-analyze advisor computation -d $PROF_DIR -pt pytorch
```

### 分析输出

| 文件 | 说明 |
|---|---|
| `/workspace/log/mstt_advisor_<timestamp>.xlsx` | 详细分析报告（Excel），含问题诊断和优化建议 |
| `/workspace/operator_tuning_file_<timestamp>.cfg` | 待调优算子列表（JSON） |

### Qwen3-8B 单卡推理分析结论

| 序号 | 问题类别 | 描述 | 建议 |
|---|---|---|---|
| 1 | 算子耗时 | MatMulV2 占 84.68%，为主要计算瓶颈 | 正常，矩阵乘法是 LLM 推理核心算子 |
| 2 | Host 下发瓶颈 | 可融合算子序列中 host 瓶颈耗时占比 0.664 | 检查 NPU 非亲和操作，评估算子融合可能性 |
| 3 | 可融合算子 | 检测到 75 个有融合价值的算子序列 | 联系开发人员评估算法层面是否可融合 |
| 4 | 算子瓶颈 | mte/cube/vector/scalar 比均未超 80% | 需调整耗时最长的算子（MatMulV2 等） |

---

## 七、完整操作速查（采集 → 解析 → 分析）

```bash
# === 在容器内执行 ===

# 1. 杀掉已有 vllm 进程
pkill -9 -f vllm

# 2. 清理旧 profiling 数据
rm -rf /workspace/vllm_profile/*

# 3. 启动带 profiler 的 vllm 服务
export ASCEND_RT_VISIBLE_DEVICES=1
nohup vllm serve /data/models/Qwen3-8B/ \
  --enable_prefix_caching --port 8009 --async-scheduling \
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"./vllm_profile"}' \
  > /tmp/vllm_profiler.log 2>&1 &

# 4. 等待服务就绪（约 2-3 分钟）
tail -f /tmp/vllm_profiler.log  # 看到 "Uvicorn running" 即可

# 5. 采集 profiling
curl -X POST http://localhost:8009/start_profile
curl -X POST http://localhost:8009/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"/data/models/Qwen3-8B/","prompt":"Beijing is a","max_tokens":20,"temperature":0}'
sleep 3
curl -X POST http://localhost:8009/stop_profile
sleep 10

# 6. 解析 profiling 数据
PROF_DIR=$(ls -d /workspace/vllm_profile/rank0*_ascend_pt)
msprof import -dir $PROF_DIR
msprof --export=on --output=$PROF_DIR

# 7. 查看解析结果
ls -lh $PROF_DIR/ASCEND_PROFILER_OUTPUT/
cat $PROF_DIR/ASCEND_PROFILER_OUTPUT/op_statistic.csv

# 8. 运行 msprof-analyze 性能分析
msprof-analyze advisor all -d $PROF_DIR -pt pytorch

# 9. 查看分析报告
ls -lh /workspace/log/mstt_advisor_*.xlsx
cat /workspace/operator_tuning_file_*.cfg
```
