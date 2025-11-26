# Copyright (C) 2025. Huawei Technologies Co., Ltd. All rights
# reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
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

import os
import shutil
import tempfile
import unittest
from unittest import mock

from msprof_analyze.advisor.common.enum_params_parser import EnumParamsParser

from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.advisor.common.timeline.fusion_ops_db import (
    FusionOperatorDB,
    get_timeline_fusion_ops_yaml_path,
    init_timeline_ops_db
)


class TestFusionOperatorDB(unittest.TestCase):

    def test_get_timeline_fusion_ops_yaml_path_when_env_points_to_file_then_return_env_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_path = os.path.join(tmp_dir, Constant.TIMELINE_FUSION_OPS_YAML_NAME)
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write("[]\n")

            with mock.patch.dict(os.environ, {Constant.ADVISOR_RULE_PATH: tmp_dir}, clear=False):
                result = get_timeline_fusion_ops_yaml_path()
            self.assertEqual(os.path.normpath(yaml_path), os.path.normpath(result))

    def test_get_timeline_fusion_ops_yaml_path_when_env_invalid_and_cloud_file_exists_then_return_cloud_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cloud_dir = os.path.join(tmp_dir, Constant.CLOUD_RULE_PATH)
            os.makedirs(cloud_dir, exist_ok=True)
            cloud_yaml = os.path.join(cloud_dir, Constant.TIMELINE_FUSION_OPS_YAML_NAME)
            with open(cloud_yaml, "w", encoding="utf-8") as f:
                f.write("[]\n")

            with mock.patch.dict(os.environ, {Constant.ADVISOR_RULE_PATH: os.path.join(tmp_dir, "not_exist")},
                                 clear=False):
                with mock.patch("os.path.expanduser", return_value=tmp_dir):
                    result = get_timeline_fusion_ops_yaml_path()

            self.assertEqual(os.path.normpath(cloud_yaml), os.path.normpath(result))

    def test_init_when_profiling_type_not_pytorch_then_no_rules_loaded(self):
        db = FusionOperatorDB(profiling_type=Constant.MINDSPORE)
        self.assertFalse(db.is_empty)
        self.assertEqual([], db.aten_op_names)
        self.assertEqual([], db.dequeue_op_names)
        self.assertEqual([], db.optimizer_op_names)
        self.assertEqual({}, db.aten_op_api_map)
        self.assertEqual({}, db.dequeue_op_api_map)
        self.assertEqual({}, db.optimizer_op_api_map)

    def test_init_when_yaml_returns_rules_then_parse_maps_and_names(self):
        fake_rules = {
            Constant.ATEN: [
                {"torch_npu.contrib.module.SiLU": ["aten::silu"]},
                {"torch_npu.npu_gelu": ["aten::gelu"]},
            ],
            Constant.DEQUEUE: [
                {"acl.dequeue": ["op1-op2"]},
            ],
            Constant.OPTIMIZER: [
                {"torch.optim.Adam#step": ["aten::adam_step"]},
            ],
        }

        with mock.patch.object(FusionOperatorDB, "_load_yaml", return_value=fake_rules):
            db = FusionOperatorDB(profiling_type=Constant.PYTORCH)

        # names
        self.assertCountEqual(db.aten_op_names, ["aten::silu", "aten::gelu"])
        self.assertCountEqual(db.dequeue_op_names, ["op1", "op2"])  # split by '-'
        self.assertCountEqual(db.optimizer_op_names, ["aten::adam_step"])
        # api maps
        self.assertEqual(db.aten_op_api_map.get("aten::silu"), "torch_npu.contrib.module.SiLU")
        self.assertEqual(db.aten_op_api_map.get("aten::gelu"), "torch_npu.npu_gelu")
        self.assertEqual(db.dequeue_op_api_map.get("op1-op2"), "acl.dequeue")
        self.assertEqual(db.optimizer_op_api_map.get("aten::adam_step"), "torch.optim.Adam#step")

    def test_regenerate_op_api_map_and_op_names_when_called_then_rebuild_from_fusion_operator(self):
        first_rules = {
            Constant.ATEN: [{"torch_npu.npu_add": ["aten::add"]}],
        }
        second_rules = {
            Constant.ATEN: [{"torch_npu.npu_mul": ["aten::mul"]}],
        }
        with mock.patch.object(FusionOperatorDB, "_load_yaml", return_value=first_rules):
            db = FusionOperatorDB(profiling_type=Constant.PYTORCH)

        # mutate fusion_operator then regenerate
        db.fusion_operator = second_rules
        db.regenerate_op_api_map_and_op_names()

        self.assertEqual(["aten::mul"], db.aten_op_names)
        self.assertEqual("torch_npu.npu_mul", db.aten_op_api_map.get("aten::mul"))

    def test_init_timeline_ops_db_when_use_speific_params_then_get_correct_rules(self):
        db = init_timeline_ops_db(profiling_type=Constant.PYTORCH,
                                  cann_version='8.0.0',
                                  profiling_version='2.1.0')
        default_cann_version = EnumParamsParser().get_default(Constant.CANN_VERSION)
        self.assertEqual(db.cann_version, default_cann_version)
        self.assertEqual(len(db.aten_op_api_map), 38)

    def test_is_version_supported_when_db_content_none_then_false(self):
        db = FusionOperatorDB(profiling_type=Constant.MINDSPORE)
        self.assertFalse(db._is_version_supported(None))


if __name__ == "__main__":
    unittest.main()


