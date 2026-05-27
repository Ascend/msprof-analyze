# Copyright (c) 2025, Huawei Technologies Co., Ltd.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0  (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np

from msprof_analyze.cluster_analyse.cluster_kernels_analysis.operator_mfu.npu_flop_registry import register_npu_flop
from msprof_analyze.prof_common.logger import get_logger

logger = get_logger()


@register_npu_flop(target="torch_npu:npu_fusion_attention")
def npu_fusion_attention_flops(query, key, value, *, input_layout, sparse_mode=0,
                               actual_seq_qlen=None, actual_seq_kvlen=None, **kwargs):
    q_shape = query.shape
    k_shape = key.shape
    logger.debug(f"[MFU] npu_fusion_attention_flops: q_shape={q_shape}, k_shape={k_shape}, "
                 f"input_layout={input_layout}, sparse_mode={sparse_mode}")

    if input_layout == "TND":
        flops = _calculate_tnd_layout_flops(q_shape, k_shape, actual_seq_qlen, actual_seq_kvlen)
    else:
        flops = _calculate_common_layout_flops(q_shape, k_shape, input_layout, sparse_mode)

    logger.debug(f"[MFU] npu_fusion_attention_flops: result={flops}")
    return flops


@register_npu_flop(target="torch_npu:npu_fused_infer_attention_score")
def npu_fused_infer_attention_score_flops(query, key, value, *, input_layout, num_heads,
                                           num_key_value_heads=None, actual_seq_lengths=None,
                                           actual_seq_lengths_kv=None, sparse_mode=0,
                                           scale=1.0, **kwargs):
    q_shape = query.shape
    k_shape = key.shape
    logger.debug(f"[MFU] npu_fused_infer_attention_score_flops: q_shape={q_shape}, k_shape={k_shape}, "
                 f"input_layout={input_layout}, num_heads={num_heads}, "
                 f"num_key_value_heads={num_key_value_heads}, sparse_mode={sparse_mode}")

    if input_layout == "TND":
        flops = _calculate_tnd_layout_flops_fia(q_shape, k_shape, actual_seq_lengths, actual_seq_lengths_kv, num_heads, num_key_value_heads)
    else:
        flops = _calculate_common_layout_flops_fia(q_shape, k_shape, input_layout, num_heads, num_key_value_heads, sparse_mode)

    logger.debug(f"[MFU] npu_fused_infer_attention_score_flops: result={flops}")
    return flops


@register_npu_flop(target="torch:mm")
def mm_flops(input, other, **kwargs):
    m, k = input.shape
    k2, n = other.shape
    flops = 2 * m * n * k
    logger.debug(f"[MFU] mm_flops: input={input.shape}, other={other.shape}, flops={flops}")
    return flops


@register_npu_flop(target="torch:bmm")
def bmm_flops(input, other, **kwargs):
    b, m, k = input.shape
    b2, k2, n = other.shape
    flops = 2 * b * m * n * k
    logger.debug(f"[MFU] bmm_flops: input={input.shape}, other={other.shape}, flops={flops}")
    return flops


@register_npu_flop(target="torch:matmul")
def matmul_flops(input, other, **kwargs):
    if input.dim() == 1 and other.dim() == 1:
        flops = 2 * input.shape[0]
    elif input.dim() == 2 and other.dim() == 2:
        m, k = input.shape
        k2, n = other.shape
        flops = 2 * m * n * k
    elif input.dim() == 3 and other.dim() == 3:
        b, m, k = input.shape
        b2, k2, n = other.shape
        flops = 2 * b * m * n * k
    else:
        batch_dims = input.shape[:-2]
        m, k = input.shape[-2], input.shape[-1]
        k2, n = other.shape[-2], other.shape[-1]
        batch_size = 1
        for d in batch_dims:
            batch_size *= d
        flops = 2 * batch_size * m * n * k
    logger.debug(f"[MFU] matmul_flops: input={input.shape}, other={other.shape}, flops={flops}")
    return flops


@register_npu_flop(target="torch.nn.functional:linear")
def linear_flops(input, weight, bias=None, **kwargs):
    n, k = weight.shape
    if input.dim() == 1:
        flops = 2 * n * k
    elif input.dim() == 2:
        m, k2 = input.shape
        flops = 2 * m * n * k
    else:
        batch_dims = input.shape[:-1]
        m = input.shape[-1]
        batch_size = 1
        for d in batch_dims:
            batch_size *= d
        flops = 2 * batch_size * n * k
    logger.debug(f"[MFU] linear_flops: input={input.shape}, weight={weight.shape}, flops={flops}")
    return flops


@register_npu_flop(target="torch:addmm")
def addmm_flops(self, mat1, mat2, beta=1, alpha=1, **kwargs):
    b1, m, k = mat1.shape if mat1.dim() == 3 else (1,) + mat1.shape
    k2, n = mat2.shape[-2], mat2.shape[-1]
    if mat1.dim() == 2:
        m, k = mat1.shape
        flops = 2 * m * n * k
    else:
        b, m, k = mat1.shape
        flops = 2 * b * m * n * k
    logger.debug(f"[MFU] addmm_flops: mat1={mat1.shape}, mat2={mat2.shape}, flops={flops}")
    return flops


def _parse_dims(tensor_shape, input_layout):
    if input_layout == "BNSD":
        b, n, s, d = tensor_shape
        return b, n, s, d
    elif input_layout == "BSND":
        b, s, n, d = tensor_shape
        return b, n, s, d
    elif input_layout == "BSH":
        b, s, d = tensor_shape
        return b, 1, s, d
    elif input_layout == "SBH":
        s, b, d = tensor_shape
        return b, 1, s, d
    else:
        raise ValueError(f"Invalid layout for FlashAttention input tensor: {input_layout}")


def _calculate_common_layout_flops(q_shape, k_shape, input_layout, sparse_mode):
    q_b, q_n, q_s, q_d = _parse_dims(q_shape, input_layout)
    _, k_n, k_s, k_d = _parse_dims(k_shape, input_layout)

    full_attention = 2 * (q_b * q_n * q_s * k_s * (q_d + k_d))

    if sparse_mode == 0:
        return full_attention
    elif q_s == k_s and sparse_mode in [2, 3]:
        return int(full_attention * 0.5)
    elif q_s > k_s and sparse_mode == 2:
        return int(full_attention * (q_s * k_s - k_s * k_s / 2) / (k_s * k_s))
    elif q_d > k_d and sparse_mode == 3:
        return int(full_attention * (k_s * k_s / 2) / (q_s * k_s))
    elif q_d < k_d and sparse_mode == 2:
        return int(full_attention * (q_s * q_s / 2) / (q_s * k_s))
    elif q_d < k_d and sparse_mode == 3:
        return int(full_attention * (q_s * k_s - q_s * q_s / 2) / (q_s * k_s))
    else:
        raise ValueError(f"Unknown flops formula for sparse_mode={sparse_mode}, q_s={q_s}, k_s={k_s}")


def _calculate_tnd_layout_flops(q_shape, k_shape, actual_seq_qlen, actual_seq_kvlen):
    if not actual_seq_qlen or not actual_seq_kvlen:
        raise ValueError("TND layout requires actual_seq_qlen and actual_seq_kvlen")

    q_t, q_n, q_d = q_shape
    _, k_n, k_d = k_shape

    q_lens = _parse_seq_len(actual_seq_qlen)
    kv_lens = _parse_seq_len(actual_seq_kvlen)

    if len(q_lens) != len(kv_lens):
        raise ValueError("actual_seq_qlen and actual_seq_kvlen must have same length")

    acl_seq_workload = np.dot(q_lens, kv_lens)
    return int(2 * q_n * (q_d + k_d) * acl_seq_workload)


def _calculate_common_layout_flops_fia(q_shape, k_shape, input_layout, num_heads, num_kv_heads, sparse_mode):
    if num_kv_heads is None:
        num_kv_heads = num_heads
    q_b, q_n, q_s, q_d = _parse_dims(q_shape, input_layout)
    _, k_n, k_s, k_d = _parse_dims(k_shape, input_layout)
    gqa_ratio = num_heads / num_kv_heads
    full_attention = int(2 * q_b * num_heads * q_s * k_s * (q_d + k_d / gqa_ratio))
    if sparse_mode == 0:
        return full_attention
    elif q_s == k_s and sparse_mode in [2, 3]:
        return int(full_attention * 0.5)
    elif q_s > k_s and sparse_mode == 2:
        return int(full_attention * (q_s * k_s - k_s * k_s / 2) / (k_s * k_s))
    else:
        return full_attention


def _calculate_tnd_layout_flops_fia(q_shape, k_shape, actual_seq_qlen, actual_seq_kvlen, num_heads, num_kv_heads):
    if not actual_seq_qlen or not actual_seq_kvlen:
        raise ValueError("TND layout requires actual_seq_qlen and actual_seq_kvlen")
    if num_kv_heads is None:
        num_kv_heads = num_heads
    q_t, q_n, q_d = q_shape
    _, k_n, k_d = k_shape
    q_lens = _parse_seq_len(actual_seq_qlen)
    kv_lens = _parse_seq_len(actual_seq_kvlen)
    if len(q_lens) != len(kv_lens):
        raise ValueError("actual_seq_qlen and actual_seq_kvlen must have same length")
    gqa_ratio = num_heads / num_kv_heads
    acl_seq_workload = np.dot(q_lens, kv_lens)
    return int(2 * num_heads * (q_d + k_d / gqa_ratio) * acl_seq_workload)


def _parse_seq_len(ori_seq_lens):
    seq_lens = list(ori_seq_lens)
    while seq_lens and seq_lens[-1] == 0:
        seq_lens.pop()
    if not seq_lens:
        return []
    return [seq_lens[0]] + [curr - prev for prev, curr in zip(seq_lens, seq_lens[1:])]
