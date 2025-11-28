# 瓶颈算子API替换样例
特定场景下，部分AI_VECTOR_CORE/CUBE类型的算子下发和执行效率较低，单算子耗时通常占单步任务的10%甚至更多。当这类算子成为运行瓶颈，可根据如下样例进行替换。


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


## BatchMatMulV2
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

## GatherElementV2
调用torch.gather的时候触发。当前NPU调用`GatherElementV2`算子会导致性能劣化，使用`torch.index_select`替换`torch.gather`函数，修改时需要注意修改索引。

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

## ReduceSum
对Tensor张量进行求和计算的时候会进行调用，如`tensor_a[mask_inds].sum()`。当前将mask索引通过one_hot和ReduceSum来创建会导致性能劣化，使用zeros+scatter方式替换one_hot+ReduceSum。

例如：
```python
mask = torch.nn.functional.one_hot(indices, num_classes=self.num_experts).sum(dim=1)
```

替换代码如下:
```python
temp_mask = torch.zeros(indices.shape[0], self.num_experts, device='npu', dtype=torch.bfloat16)
mask = temp_mask.scatter_(-1, indices, 1.0)
```