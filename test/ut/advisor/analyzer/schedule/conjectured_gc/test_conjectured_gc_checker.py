# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------

import unittest
from unittest.mock import MagicMock, patch

from msprof_analyze.advisor.analyzer.schedule.conjectured_gc.conjectured_gc_checker import AbnormalGcStatistic, \
    ConjecturedGcChecker


class TestAbnormalGcStatistic(unittest.TestCase):
    def setUp(self):
        self.gc_statistic = AbnormalGcStatistic()

    def test_initialization(self):
        """测试初始化是否正确设置默认值"""
        self.assertEqual(self.gc_statistic.count, 0)
        self.assertEqual(self.gc_statistic.duration, 0)
        self.assertEqual(self.gc_statistic.events, [])

    def test_count_property(self):
        """测试count属性的getter和setter"""
        self.gc_statistic.count = 5
        self.assertEqual(self.gc_statistic.count, 5)

    def test_duration_property(self):
        """测试duration属性的getter和setter"""
        self.gc_statistic.duration = 100.5
        self.assertEqual(self.gc_statistic.duration, 100.5)

    def test_events_property(self):
        """测试events属性"""
        events = [{"ts": 100, "free time": 50.5}]
        self.gc_statistic.events.extend(events)
        self.assertEqual(len(self.gc_statistic.events), 1)
        self.assertEqual(self.gc_statistic.events[0], events[0])

    def test_export(self):
        """测试export方法是否正确导出事件数据"""
        self.gc_statistic._events = [
            {"ts": 100.123, "free time": 50.6789},
            {"ts": 200.456, "free time": 100.1234}
        ]
        result = self.gc_statistic.export()
        expected = [[100.12, 50.6789], [200.46, 100.1234]]
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result[0][0], expected[0][0], places=2)
        self.assertAlmostEqual(result[0][1], expected[0][1], places=4)
        self.assertAlmostEqual(result[1][0], expected[1][0], places=2)
        self.assertAlmostEqual(result[1][1], expected[1][1], places=4)


class TestConjecturedGcChecker(unittest.TestCase):
    def setUp(self):
        self.checker = ConjecturedGcChecker()

    def test_initialization(self):
        """测试初始化是否正确设置默认值"""
        self.assertIsNone(self.checker.stage)
        self.assertIsNone(self.checker.rank)
        self.assertEqual(self.checker.optimization_item, [])
        self.assertIsInstance(self.checker.gc_statistic, AbnormalGcStatistic)

    def test_check_gc_with_gc_events(self):
        """测试当event_dataset包含gc_events时的行为"""
        mock_dataset = MagicMock()
        mock_dataset.gc_events = ["gc_event"]  # 非空列表
        self.checker.check_gc(mock_dataset, rank=0, stage=1)
        self.assertEqual(self.checker.gc_statistic.count, 0)

    def test_check_gc_without_acl_events(self):
        """测试当没有acl_events时的行为"""
        mock_dataset = MagicMock()
        mock_dataset.gc_events = []
        mock_dataset.acl_events = []  # 空列表
        mock_dataset.large_free_events = [{"ts": 100, "dur": 50}]

        self.checker.check_gc(mock_dataset)
        self.assertEqual(self.checker.gc_statistic.count, 0)

    def test_check_gc_without_large_free_events(self):
        """测试当没有large_free_events时的行为"""
        mock_dataset = MagicMock()
        mock_dataset.gc_events = []
        mock_dataset.acl_events = [{"ts": 100, "dur": 10}]
        mock_dataset.large_free_events = []  # 空列表

        self.checker.check_gc(mock_dataset)
        self.assertEqual(self.checker.gc_statistic.count, 0)

    @patch('msprof_analyze.advisor.analyzer.schedule.conjectured_gc.conjectured_gc_checker.'
           'ConjecturedGcChecker._init_rule')
    def test_get_free_events_include_gc(self, mock_init_rule):
        """测试get_free_events_include_gc方法"""
        self.checker.max_acl_event_time_ratio = 0.1
        self.checker.max_acl_event_num_ratio = 0.1
        large_free_events = [
            type('obj', (), {'ts': 100, 'dur': 50}),
            type('obj', (), {'ts': 200, 'dur': 30})
        ]

        acl_events = [
            type('obj', (), {'ts': 101, 'dur': 1}),
            type('obj', (), {'ts': 105, 'dur': 2}),
            type('obj', (), {'ts': 205, 'dur': 1})
        ]
        self.checker.get_free_events_include_gc(large_free_events, acl_events)
        self.assertEqual(self.checker.gc_statistic.count, 2)
        self.assertEqual(self.checker.gc_statistic.duration, 80)  # 50 + 30
        self.assertEqual(len(self.checker.gc_statistic.events), 2)

    @patch('msprof_analyze.advisor.analyzer.schedule.conjectured_gc.conjectured_gc_checker.'
           'ConjecturedGcChecker._init_rule')
    def test_get_free_events_include_gc_high_ratio(self, mock_init_rule):
        """测试当ACL事件比例较高时不被识别为GC"""
        self.checker.max_acl_event_time_ratio = 0.05
        self.checker.max_acl_event_num_ratio = 0.05
        large_free_events = [type('obj', (), {'ts': 100, 'dur': 10})]
        acl_events = [type('obj', (), {'ts': 101, 'dur': 1})]  # 占比10%
        self.checker.get_free_events_include_gc(large_free_events, acl_events)
        self.assertEqual(self.checker.gc_statistic.count, 0)

    def test_make_record_no_gc(self):
        """测试当没有GC问题时make_record的行为"""
        self.checker.gc_statistic.count = 0
        mock_result = MagicMock()
        self.checker.make_record(mock_result)
        mock_result.add.assert_not_called()
        mock_result.add_detail.assert_not_called()

    def test_make_render_no_gc(self):
        """测试当没有GC问题时make_render的行为"""
        self.checker.gc_statistic.count = 0
        mock_render = MagicMock()
        self.checker.make_render(mock_render, priority="high", rank=0)
        mock_render.render_template.assert_not_called()

    @patch('msprof_analyze.advisor.analyzer.schedule.conjectured_gc.conjectured_gc_checker.'
           'ConjecturedGcChecker._init_rule')
    def test_make_render_with_gc(self, mock_init_rule):
        """测试当有GC问题时make_render的行为"""
        self.checker.gc_statistic.count = 5
        self.checker.gc_topk_num = 3
        self.checker.desc = "测试描述"
        self.checker.solutions = [{"解决方案": "详细说明"}]
        self.checker.gc_statistic._events = [
            {"ts": 100, "free time": 50},
            {"ts": 200, "free time": 40},
            {"ts": 300, "free time": 30},
            {"ts": 400, "free time": 20},
            {"ts": 500, "free time": 10}
        ]
        mock_render = MagicMock()
        self.checker.make_render(mock_render, priority="high", rank=0)
        mock_render.render_template.assert_called_once()
        call_args = mock_render.render_template.call_args
        self.assertEqual(call_args[1]['key'], "schedule")
        self.assertEqual(call_args[1]['title'], "Conjectured GC Analysis")
        self.assertEqual(call_args[1]['num'], 3)  # 应该只显示top 3
        self.assertEqual(len(call_args[1]['data_list']), 3)


if __name__ == '__main__':
    unittest.main()
