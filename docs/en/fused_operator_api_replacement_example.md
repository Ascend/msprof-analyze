# Examples for Fused Operator API Replacement During Migration to Ascend

Some native `torch` APIs involve multiple small operators during delivery and execution, resulting in long durations. You can replace these APIs with NPU APIs to enable fused operators and improve training performance.

For details about the functions and parameters of torch_npu APIs, see the [torch_npu APIs](<>).

## Optimizer Replacement

Replacing an optimizer generally provides significant performance benefits. Prioritize replacing native torch optimizers with [Ascend affinity optimizers](<>). The following example uses the `AdamW` optimizer. The replacement method also applies to other optimizers.

### torch_npu.optim.NpuFusedAdamW

Native `torch` code example:

```python
import torch
optimizer = torch.optim.AdamW(
  model.parameters(),
  learning_rate,
  momentum=momentum,
  weight_decay=weight_decay
)
```

`torch_npu` code example:

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

## Affinity API Replacement

### optimizer.clip_grad_norm_fused_

Before replacing the API with the NPU affinity gradient clipping API, ensure that an NPU affinity optimizer is already used in the code.

Native `torch` code example:

```python
import torch
optimizer = torch.optim.AdamW(model.parameters(), lr = lr)
torch.nn.utils.clip_grad_norm_(parameters=model.parameters(), max_norm=10, norm_type=2)
```

`torch_npu` code example:

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

optimizer = torch_npu.optim.NpuFusedAdamW(model.parameters(), lr = lr)
optimizer.clip_grad_norm_fused_(max_norm=10, norm_type=2)
```

### torch_npu.npu_confusion_transpose

**Example 1**

Native `torch` code example:

```python
import torch

data = torch.rand(64, 3, 64, 128).cuda()
batch, channel, height, width = data.shape
result = torch.permute(data, (0, 2, 1, 3)).reshape(height, batch, channel*width)
```

`torch_npu` code example:

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

data = torch.rand(64, 3, 64, 128).cuda()
batch, channel, height, width = data.shape
result = torch_npu.npu_confusion_transpose(data, (0, 2, 1, 3), (height, batch, channel*width), transpose_first=True)
```

**Example 2**

Native `torch` code example:

```python
import torch

data = torch.rand(64, 3, 64, 128).cuda()
batch, channel, height, width = data.shape
result = data.view(batch, height*channel*width).transpose(1, 0)
```

`torch_npu` code example:

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

data = torch.rand(64, 3, 64, 128).cuda()
batch, channel, height, width = data.shape
result = torch_npu.npu_confusion_transpose(data, (1, 0), (batch, height*channel*width), transpose_first=False)
```

### torch_npu.npu_scaled_masked_softmax

Note that the value of the last dimension for the `atten_mask` and `atten_scores` tensors must be within the range of [32, 8192] and must be a multiple of 32.

Native `torch` code example:

```python
import torch
x = torch.randn([64, 8, 128, 256]).cuda()
mask = torch.randn([1, 1, 128, 256]).cuda() >= 1
scale = 0.8

output = torch.softmax((x * scale).masked_fill(mask, -1*torch.inf), dim=-1)
# shape is (64, 8, 128, 256)
```

`torch_npu` code example:

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

**Example 1**

Replace the `torch.nn.functional.gelu` method. There are implementation differences, and the output of the activation function is different.

Native `torch` code example:

```python
import torch
input_data = torch.rand(64, 32).cuda()
result = torch.nn.functional.gelu(input_data)
```

`torch_npu` code example:

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

input_data = torch.rand(64, 32).cuda()
result = torch_npu.fast_gelu(input_data)
```

**Example 2**

Inherit from `torch.nn.GELU` and rewrite the `forward` method based on `torch_npu.fast_gelu`.

Native `torch` code example:

```python
import torch
input_data = torch.rand(64, 32).cuda()
gelu_module = torch.nn.GELU().cuda()
result3 = gelu_module(input_data)
```

`torch_npu` code example:

```python
import torch
import torch_npu
from torch_npu.contrib import transfer_to_npu

# Inherit from torch.nn.GELU and rewrite the forward method based on torch_npu.fast_gelu
class FastGelu(torch.nn.GELU):
    def forward(self, input_data):
        return torch_npu.fast_gelu(input_data)

input_data = torch.rand(64, 32).cuda()
fast_gelu_module = FastGelu().cuda()
result = fast_gelu_module(input_data)
```

### torch_npu.npu_rms_norm

The input `dtype` supports only `float16`, `bfloat16`, or `float`.

Native `torch` code example:

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

`torch_npu` code example:

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

The input `dtype` supports only `float16`, `bfloat16`, or `float`.

Native `torch` code example:

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

`torch_npu` code example:

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

Native `torch` code example:

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

`torch_npu` code example:

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

Native `torch` code example:

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

`torch_npu` code example:

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
