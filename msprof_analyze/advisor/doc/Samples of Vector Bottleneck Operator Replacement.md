# 瓶颈算子API替换样例
特定场景下，部分AI_VECTOR_CORE/CUBE类型的算子下发和执行效率较低，单算子耗时通常占单步任务的10%甚至更多。当这类算子成为运行瓶颈，可根据如下样例进行替换。

## IndexPutV2
当调用索引进行赋值的时候算子触发调用。由于昇腾SIMD（Single Instruction, Multiple Data, 单指令， 多数据）架构特点，我们希望每个指令能够融合更多数据，避免多次进行小数据的随机访问。因此遇到矩阵索引等操作时，可以对其进行替换，如替换成乘法操作。

例如：
```python
target_mask = (target < vocab_start_index) | (target >= vocab_end_index)
masked_target = target.clone() - vocab_start_index
masked_target[target_mask] = 0
```

替换代码如下：

```python
target_mask = (target < vocab_start_index) | (target >= vocab_end_index)
masked_target = target.clone() - vocab_start_index
masked_target *= ~target_mask
```
将索引操作转换成矩阵的加乘操作，从而避免大量随机访问带来的性能劣化。

## RepeatInterleave
当调用`torch.repeat_interleave`触发算子。该算子仅针对在张量0维上repeat操作进行了优化，针对该算子优化方案是改变shape切换到高性能维度上进行计算，将需要repeat操作的张量维度reshape到0维进行repeat操作，之后再一次按原来的reshape操作还原数据。

例如：
```python
if valid_lens.dim() == 1:
    valid_lens = torch.repeat_interleave(valid_lens, shape[1])
else:
    valid_lens = valid_lens.reshape(-1)
```

替换代码如下：
```python
if valid_lens.dim() == 1:
    valid_lens = valid_lens.unsqueeze(-1).expand(-1, shape[1]).reshape(-1)
else:
    valid_lens = valid_lens.reshape(-1)
```

## Nonzero
`Nozero`一般和index操作相关。将mask转换成index对于所有值为0的张量在某些计算中可以利用乘法进行替代，比如要对mask的tensor求和，`tensor_a[mask].sum()`就相当于`(tensor_a * mask).sum()`。

例如：
```python
shape = (1024, )
mask = torch.randint(-1, 2, shape).npu()
tensor_a = torch.ones(shape).float().npu()
mask_inds = torch.nonzero(gt_inds > 0, as_tuple=False).squeeze(1)
tensor_sum = tensor_a[mask_inds].sum()
```

替换代码如下：
```python
shape = (1024, )
mask = torch.randint(-1, 2, shape).npu()
tensor_a = torch.ones(shape).float().npu()
mask_inds = torch.nonzero(gt_inds > 0, as_tuple=False).squeeze(1)
tensor_sum = (tensor_a * mask_inds).sum()
```

## where
调用`torch.where`算子时候触发。该API是一种条件选择的API，在使用过程中会产生大量的随机访问内存。而`torch.lerp`是一种线性插值API，算子逻辑更为简单。
通过将`where`中的二元条件选择（True/False）转换为`lerp`的连续权重（0/1），利用线性插值公式 (1 - weight) * x + weight * y 来模拟条件选择过程。即当condition的本身为input与other的比较，可以根据condition去选择input或other时，可等价适用`lerp`替换。该替换的优化原理为，相比较`where`，`lerp`采用更简单的逻辑算子实现，能够极大减少反向算子的耗时。

例如：

```python
out = torch.where(x < y, y, x)
```

替换代码如下：
```python
out = torch.lerp(x, y, (x < y).float())
```

## BatchMatmalV2
基于`torch.matmul`进行矩阵乘计算时，如果输入的shape中存在特定轴的维度为1且不参与矩阵运算，会导致使能昇腾`BatchMatMulV2`算子，造成性能劣化。如输入shape为`[b, 1, n]`和`[n, 1] `或者输入shape为`[1, m, n]`和`[1, n, k]`，可以通过消除维度为1的轴来规避`BatchMutMulV2`算子。

例如：
```python
output = torch.matmul(a,b) # a[bs,1,n], b[n,1]
```

替换代码如下：
```python
a_ = a.permute(0, 2, 1)
a_ = a_.reshape(-1, a.shape[2])
output = torch.matmul(a.t(), b) # a[bs, n], b[n,1]
```

## Gatherelement
调用torch.gather的时候触发。当前NPU调用`Gatherelement`算子会导致性能劣化，使用`torch.index_select`替换`torch.gather`函数，修改时需要注意修改索引。

例如：
```python
alpha = self.alpha.to(logpt.device)
alpha_class = a.gather(0, target.view(-1))
```

替换代码如下：
```python
alpha = self.alpha.to(logpt.device)
alpha_class = a.gather(alpha, 0, target.view(-1))
```