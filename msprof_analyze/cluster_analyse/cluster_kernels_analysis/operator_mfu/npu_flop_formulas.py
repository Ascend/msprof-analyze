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


@register_npu_flop("npu_fusion_attention")
def npu_fusion_attention_flops(query, key, value, *, input_layout, sparse_mode=0,
                               actual_seq_qlen=None, actual_seq_kvlen=None, **kwargs):
    q_shape = query.shape
    k_shape = key.shape

    if input_layout == "TND":
        return _calculate_tnd_layout_flops(q_shape, k_shape, actual_seq_qlen, actual_seq_kvlen)
    else:
        return _calculate_common_layout_flops(q_shape, k_shape, input_layout, sparse_mode)


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


def _parse_seq_len(ori_seq_lens):
    seq_lens = list(ori_seq_lens)
    while seq_lens and seq_lens[-1] == 0:
        seq_lens.pop()
    if not seq_lens:
        return []
    return [seq_lens[0]] + [curr - prev for prev, curr in zip(seq_lens, seq_lens[1:])]
