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

import unittest

from msprof_analyze.compare_tools.compare_backend.data_prepare.sequence_pre_matching import SequencePreMatching


class Args:
    def __init__(self, disable_details=False, max_kernel_num=None, op_name_map=None, use_input_shape=False):
        self.disable_details = disable_details
        self.max_kernel_num = max_kernel_num
        self.op_name_map = op_name_map or {}
        self.use_input_shape = use_input_shape


class OpStub:
    def __init__(self, name, start_time=0, tid=0, kernel_num=0, children=None):
        self.name = name
        self.start_time = start_time
        self.end_time = start_time + 1
        self.tid = tid
        self.child_nodes = list(children) if children else []
        self.kernel_num = kernel_num


class ModuleStub:
    def __init__(self, module_name, children=None):
        self.module_name = module_name
        self.child_nodes = list(children) if children else []


class TestSequencePreMatching(unittest.TestCase):
    def setUp(self):
        self.args = Args()

    def tearDown(self):
        pass

    def extract_pair_names(self, pairs):
        return [
            ((a.name if a else None), (b.name if b else None))
            for a, b in pairs
        ]

    def test_match_torch_op_basic_lcs(self):
        args = Args(disable_details=False)
        spm = SequencePreMatching(args)
        base = [OpStub("A"), OpStub("B"), OpStub("C"), OpStub("D")]
        comp = [OpStub("B"), OpStub("X"), OpStub("C"), OpStub("E")]
        pairs = spm._match_torch_op(base, comp)
        names = self.extract_pair_names(pairs)
        # Expected LCS: B, C; others unmatched in order
        self.assertEqual(names, [('A', None), ('B', 'B'), (None, 'X'), ('C', 'C'), ('D', None), (None, 'E')])

    def test_match_torch_op_disable_details_none_subsequence(self):
        args = Args(disable_details=True)
        spm = SequencePreMatching(args)
        base = [OpStub("A"), OpStub("B")]
        comp = [OpStub("C")]
        pairs = spm._match_torch_op(base, comp)
        names = self.extract_pair_names(pairs)
        # When disable_details, just concatenate base then comp as unmatched
        assert names == [("A", None), ("B", None), (None, "C")]

    def test_run_with_backward_tid_splitting(self):
        # base has segments by tid, split around bwd_tid, preserve order by start_time
        args = Args(disable_details=False)
        base_bwd_tid = 2
        comp_bwd_tid = 9
        spm = SequencePreMatching(args, base_bwd_tid=base_bwd_tid, comparison_bwd_tid=comp_bwd_tid)
        base = [
            OpStub("A", start_time=1, tid=1),
            OpStub("B", start_time=2, tid=2),  # bwd
            OpStub("C", start_time=3, tid=2),  # bwd
            OpStub("D", start_time=4, tid=1),
        ]
        comp = [
            OpStub("A", start_time=1, tid=8),
            OpStub("B", start_time=2, tid=9),  # bwd
            OpStub("Y", start_time=3, tid=9),  # bwd extra
            OpStub("D", start_time=4, tid=8),
        ]
        pairs = spm.run(SequencePreMatching.OP_TYPE, base, comp)
        names = self.extract_pair_names(pairs)
        # Expect A match, then split segments: B,C vs B,Y, then D match
        self.assertEqual(names, [('A', 'A'), ('B', 'B'), ('C', None), (None, 'Y'), ('D', 'D')])

    def test_drill_down_by_max_kernel_num(self):
        # Parent nodes exceed kernel threshold; should drill into children for matching
        args = Args(disable_details=False, max_kernel_num=5)
        spm = SequencePreMatching(args)

        # Build children
        base_child1 = OpStub("c1")
        base_child2 = OpStub("c2")
        comp_child1 = OpStub("c1")
        comp_child3 = OpStub("c3")

        # Parents have high kernel_num to trigger drill-down
        base_parent = OpStub("P", kernel_num=10, children=[base_child1, base_child2])
        comp_parent = OpStub("P", kernel_num=10, children=[comp_child1, comp_child3])

        pairs = spm._match_torch_op([base_parent], [comp_parent])
        names = self.extract_pair_names(pairs)
        # After drill-down, should match c1, and mark unmatched c2 and c3
        self.assertEqual(names, [('c1', 'c1'), ('c2', None), (None, 'c3')])

    def test_match_nn_module_sequences(self):
        # Two roots with ordered child modules; only corresponding indexes compared
        args = Args()
        spm = SequencePreMatching(args)

        base_root = [ModuleStub("root1", children=[ModuleStub("A"), ModuleStub("B")])]
        comp_root = [ModuleStub("root1", children=[ModuleStub("B"), ModuleStub("A")])]

        pairs = spm.run(SequencePreMatching.MODULE_TYPE, base_root, comp_root)
        # LCS over children by module_name => match A and B but maintain relative order => one match, two unmatched
        result = [((a.module_name if a else None), (b.module_name if b else None)) for a, b in pairs]
        self.assertEqual(result, [(None, 'B'), ('A', 'A'), ('B', None)])

if __name__ == '__main__':
    unittest.main()
