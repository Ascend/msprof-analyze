# 昇腾迁移融合算子API替换样例

部分torch原生的API在下发和执行时会包括多个小算子，下发和执行耗时较长，可以通过替换成NPU API来使能融合算子，提升训练性能。

torch_npu API的功能和参数描述见[API列表](https://www.hiascend.com/document/detail/zh/Pytorch/710/apiref/torchnpuCustomsapi/context/torch_npu接口列表.md)。

## 优化器替换

替换优化器一般都能有较大的性能受益，可以优先考虑将torch原生的优化器替换为[昇腾提供的亲和优化器](https://www.hiascend.com/document/detail/zh/Pytorch/710/ptmoddevg/trainingmigrguide/performance_tuning_0036.html)。下文以AdamW优化器为例，其他优化器的替换方式一致。

### torch_npu.optim.NpuFusedAdamW

torch原生代码示例如下：

```python
import torch
optimizer = torch.optim.AdamW(
  model.parameters(),
  learning_rate,
  momentum=momentum,
  weight_decay=weight_decay
)
```

torch_npu代码示例如下：

```python
import torch_npu
from torch_npu.contrib import transfer_to_npu

optimizer = torch_npu.optim.NpuFusedAdamW(
  model.parameters(),
  learning_rate,
  momentum=momentum,
  weight_decay=weight_decay
)
```

## 亲和API替换

### optimizer.clip_grad_norm_fused_

在替换为npu亲和梯度裁剪api之前，请确保代码中已使用npu亲和优化器。

torch原生代码示例如下：

```python
import torch
optimizer = torch.optim.AdamW(model.parameters(), lr = lr)
torch.nn.utils.clip_grad_norm_(parameters=model.parameters(), max_norm=10, norm_type=2)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

optimizer = torch_npu.optim.NpuFusedAdamW(model.parameters(), lr = lr)
optimizer.clip_grad_norm_fused_(max_norm=10, norm_type=2)
```

### torch_npu.npu_confusion_transpose

**示例一**

torch原生代码示例如下：

```python
import torch

data = torch.rand(64, 3, 64, 128).cuda()
batch, channel, height, width = data.shape
result = torch.permute(data, (0, 2, 1, 3)).reshape(height, batch, channel*width)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

data = torch.rand(64, 3, 64, 128).cuda()
batch, channel, height, width = data.shape
result = torch_npu.npu_confusion_transpose(data, (0, 2, 1, 3), (height, batch, channel*width), transpose_first=True)
```

**示例二**

torch原生代码示例如下：

```python
import torch

data = torch.rand(64, 3, 64, 128).cuda()
batch, channel, height, width = data.shape
result = data.view(batch, height*channel*width).transpose(1, 0)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

data = torch.rand(64, 3, 64, 128).cuda()
batch, channel, height, width = data.shape
result = torch_npu.npu_confusion_transpose(data, (1, 0), (batch, height*channel*width), transpose_first=False)
```

### torch_npu.npu_scaled_masked_softmax

注意atten_mask和atten_scores张量最后一维的取值范围为32-8192，且必须为32的整数倍。

torch原生代码示例如下：

```python
import torch
x = torch.randn([64, 8, 128, 256]).cuda()
mask = torch.randn([1, 1, 128, 256]).cuda() >= 1
scale = 0.8

output = torch.softmax((x * scale).masked_fill(mask, -1*torch.inf), dim=-1)
# shape is (64, 8, 128, 256)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

x = torch.randn([64, 8, 128, 256]).cuda()
mask = torch.randn([1, 1, 128, 256]).cuda() >= 1
scale = 0.8

output = torch_npu.npu_scaled_masked_softmax(x, mask, scale)
# shape is (64, 8, 128, 256)
```

### torch_npu.fast_gelu

**示例一**

替换torch.nn.functional.fast_gelu方法，实现上有些差异，激活函数输出结果会不同。

torch原生代码示例如下：

```python
import torch
input_data = torch.rand(64, 32).cuda()
result = torch.nn.functional.gelu(input_data)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

input_data = torch.rand(64, 32).cuda()
result = torch_npu.fast_gelu(input_data)
```

**示例二**

继承torch.nn.GELU，基于torch_npu.fast_gelu重写forward方法。

torch原生代码示例如下：

```python
import torch
input_data = torch.rand(64, 32).cuda()
gelu_module = torch.nn.GELU().cuda()
result3 = gelu_module(input_data)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

# 继承torch.nn.GELU，基于torch_npu.fast_gelu重写forward方法
class FastGelu(torch.nn.GELU):
    def forward(self, input_data):
        return torch_npu.fast_gelu(input_data)

input_data = torch.rand(64, 32).cuda()
fast_gelu_module = FastGelu().cuda()
result = fast_gelu_module(input_data)
```

### torch_npu.npu_rms_norm

输入数据dtype仅支持float16、bfloat16、float。

torch原生代码示例如下：

```python
import torch

class TorchRMSNorm(torch.nn.Module):
    def __init__(self, dim: int, eps = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim)).cuda()

    def _norm(self, x):
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)

    def forward(self, x):
        output = self._norm(x.float()).type_as(x)
        return output * self.weight

input_data = torch.randn(128, 256).cuda()
torch_rms_norm = TorchRMSNorm((128, 256))
result = torch_rms_norm(input_data)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

class NpuRMSNorm(torch.nn.Module):
    def __init__(self, dim: int, eps = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim)).cuda()

    def forward(self, x):
        return torch_npu.npu_rms_norm(x, self.weight, epsilon=self.eps)[0]

input_data = torch.randn(128, 256).cuda()
npu_rms_norm = NpuRMSNorm((128, 256))
result = npu_rms_norm(input_data)
```

### torch_npu.npu_swiglu

输入数据dtype仅支持float16、bfloat16、float。

torch原生代码示例如下：

```python
import torch
class TorchSwiGlu(torch.nn.Module):
    def __init__(self, dim = -1):
        super().__init__()
        self.dim = dim

    def _swiglu(self, x):
        x = torch.chunk(x, 2, -1)
        return torch.nn.functional.silu(x[0]) * x[1]

    def forward(self, x):
        output = self._swiglu(x)
        return output

input_data = torch.randn(128, 256).cuda()
torch_swiglu = TorchSwiGlu()
result = torch_swiglu(input_data)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

class NpuSwiGlu(torch.nn.Module):
    def __init__(self, dim = -1):
        super().__init__()
        self.dim = dim

    def forward(self, x):
        dim = -1
        return torch_npu.npu_swiglu(x, dim=dim)

input_data = torch.randn(128, 256).cuda()
npu_swiglu = NpuSwiGlu()
result = npu_swiglu(input_data)
```

### torch_npu.npu_rotary_mul

torch原生代码示例如下：

```python
import torch

x = torch.rand([2, 8192, 5, 128]).cuda()
r1 = torch.rand([1, 8192, 1, 128]).cuda()
r2 = torch.rand([1, 8192, 1, 128]).cuda()

def torch_func(x, r1, r2):
   x1, x2 = x[..., : x.shape[-1] // 2], x[..., x.shape[-1] // 2:]
   # x1, x2 = torch.chunk(x, 2, -1)
   x_new = torch.cat((-x2, x1), dim=-1)
   output = r1 * x + r2 * x_new
   return output

result = torch_func(x, r1, r2)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

x = torch.rand([2, 8192, 5, 128]).cuda()
r1 = torch.rand([1, 8192, 1, 128]).cuda()
r2 = torch.rand([1, 8192, 1, 128]).cuda()

result = torch_npu.npu_rotary_mul(x, r1, r2)
```

### torch_npu.npu_fusion_attention

torch原生代码示例如下：

```python
import torch

class TorchFlashAttention():
    def supported_op_exec(self, query, key, value, atten_mask=None):
        scale = 0.099
        qk = torch.matmul(query, key.transpose(2, 3)).mul(scale)

        if atten_mask is not None:
            qk.masked_fill_(atten_mask.npu(), torch.tensor(-float('inf')).npu())
        softmax_res = torch.nn.functional.softmax(qk, dim=-1, dtype=torch.float32).to(torch.float16)
        output = torch.matmul(softmax_res, value)
        output = output.transpose(1, 2)
        output = output.reshape(output.shape[0], output.shape[1], -1)
        return output

    def custom_op_exec(self, query, key, value, atten_mask=None):
        scale = 0.099
        return torch_npu.npu_fusion_attention(
            query, key, value, head_num=32, input_layout="BSH", scale=scale, atten_mask=atten_mask)

    def trans_BNSD2BSH(self, tensor: torch.Tensor):
        tensor = torch.transpose(tensor, 1, 2)
        tensor = torch.reshape(tensor, (tensor.shape[0], tensor.shape[1], -1))
        return tensor

    def test_torch_flash_attention(self, device="npu"):
        query = torch.randn(1, 32, 128, 128, dtype=torch.float16)
        key = torch.randn(1, 32, 128, 128, dtype=torch.float16)
        value = torch.randn(1, 32, 128, 128, dtype=torch.float16)
        atten_mask = torch.randn(1, 1, 128, 128, dtype=torch.float16).npu() >= 0

        q_npu = self.trans_BNSD2BSH(query).npu()
        k_npu = self.trans_BNSD2BSH(key).npu()
        v_npu = self.trans_BNSD2BSH(value).npu()

        result = self.supported_op_exec(query.npu(), key.npu(), value.npu(), atten_mask=atten_mask)
        # result shape (1, 128, 4096)
```

torch_npu代码示例如下：

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu


class NPUFlashAttention():

    def npu_exec(self, query, key, value, atten_mask=None):
        scale = 0.099
        return torch_npu.npu_fusion_attention(
            query, key, value, head_num=32, input_layout="BSH", scale=scale, atten_mask=atten_mask)

    def trans_BNSD2BSH(self, tensor: torch.Tensor):
        tensor = torch.transpose(tensor, 1, 2)
        tensor = torch.reshape(tensor, (tensor.shape[0], tensor.shape[1], -1))
        return tensor

    def test_npu_flash_attention(self, device="npu"):
        query = torch.randn(1, 32, 128, 128, dtype=torch.float16)
        key = torch.randn(1, 32, 128, 128, dtype=torch.float16)
        value = torch.randn(1, 32, 128, 128, dtype=torch.float16)
        atten_mask = torch.randn(1, 1, 128, 128, dtype=torch.float16).npu() >= 0

        q_npu = self.trans_BNSD2BSH(query).npu()
        k_npu = self.trans_BNSD2BSH(key).npu()
        v_npu = self.trans_BNSD2BSH(value).npu()

        result, softmax_max, softmax_sum, softmax_out, seed, offset, numels = self.npu_exec(q_npu, k_npu, v_npu, atten_mask)
        # result shape (1, 128, 4096)
```