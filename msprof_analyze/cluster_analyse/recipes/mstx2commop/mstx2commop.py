# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
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

import json
import os
import shutil

import pandas as pd
from msprof_analyze.prof_common.path_manager import PathManager

from msprof_analyze.cluster_analyse.recipes.base_recipe_analysis import BaseRecipeAnalysis
from msprof_analyze.prof_common.db_manager import DBManager
from msprof_analyze.prof_common.constant import Constant
from msprof_analyze.prof_common.logger import get_logger
from msprof_analyze.prof_exports.mstx2commop_export import Mstx2CommopExport
from msprof_analyze.prof_common.database_service import DatabaseService

logger = get_logger()

TABLE_COMMUNICATION_OP = "COMMUNICATION_OP"
TABLE_STRING_IDS = "STRING_IDS"


def double_hash(data):
    uint32_bits = 32
    uint32_max = 0xFFFFFFFF  # 32 位无符号整数的最大值
    prime = [29, 131]
    hash_values = [0, 0]

    for d in data:
        hash_values[0] = (hash_values[0] * prime[0] + ord(d)) & uint32_max
        hash_values[1] = (hash_values[1] * prime[1] + ord(d)) & uint32_max

    return (hash_values[0] << uint32_bits) | hash_values[1]


class Mstx2Commop(BaseRecipeAnalysis):
    def __init__(self, params):
        super().__init__(params)
        logger.info("Mstx2Commop init.")
        self.copy_db = True
        self.communication_op = None
        self.string_ids_insert = None
        self.set_output = Constant.CLUSTER_ANALYSIS_OUTPUT_PATH in params  # 是否设置了output_path参数

    @property
    def base_dir(self):
        return os.path.basename(os.path.dirname(__file__))

    def run(self, context, copy_db=True):
        self.copy_db = copy_db
        self.mapper_func(context)

    def _mapper_func(self, data_map, analysis_class):
        profiler_db_path = data_map.get(Constant.PROFILER_DB_PATH)
        if DBManager.check_tables_in_db(profiler_db_path, TABLE_COMMUNICATION_OP):
            return None
        step_range = data_map.get(Constant.STEP_RANGE)
        data_service = DatabaseService(profiler_db_path, step_range)
        data_service.add_table_for_query("ENUM_HCCL_DATA_TYPE", ["id", "name"])
        data_service.add_table_for_query("STRING_IDS", ["id", "value"])
        df_dict = data_service.query_data()

        df = Mstx2CommopExport(profiler_db_path, analysis_class, step_range).read_export_db()

        if df is None or df.empty:
            logger.warning("There is no stats data in %s.", profiler_db_path)
            return None

        df_hccl_dt = df_dict.get("ENUM_HCCL_DATA_TYPE")

        if df_hccl_dt is None or df_hccl_dt.empty:
            logger.warning("There is no stats data in %s.", profiler_db_path)
            return None

        df_string_ids = df_dict.get("STRING_IDS")

        if df_string_ids is None or df_string_ids.empty:
            logger.warning("There is no stats data in %s.", profiler_db_path)
            return None

        value_len = 4
        optype_index, op_start_index = 0, 9
        groupname_index, datatype_index, count_index = 1, 2, 3

        # json格式数据转化
        if df.loc[0, 'value'][0] == '{':
            df['value'] = df['value'].apply(json.loads)
            df['opType_primal'] = df['value'].apply(lambda x: x['opName'] + '_')
            df['groupName_primal'] = df['value'].apply(lambda x: x['groupName'])
            df['dataType'] = df['value'].apply(lambda x: x['dataType'])
            df['count'] = df['value'].apply(lambda x: x['count'])
        # 非json格式数据转化
        else:
            df['value_list'] = df['value'].apply(lambda x: x.split(','))
            df['value_list_len'] = df['value_list'].apply(len)
            df = df[df['value_list_len'] == value_len]
            df['opType_primal'] = df['value_list'].apply(lambda x: 'hcom_' + x[optype_index][op_start_index:] + '_')
            df['groupName_primal'] = df['value_list'].apply(lambda x: x[groupname_index])
            df['dataType'] = df['value_list'].apply(lambda x: x[datatype_index])
            df['count'] = df['value_list'].apply(lambda x: x[count_index])

        df['groupName_hash'] = df['groupName_primal'].apply(double_hash).apply(str)

        df['gN_oT'] = df['groupName_primal'] + df['opType_primal']

        gnot_set = set(list(df['gN_oT']))

        df_concat = pd.DataFrame()
        for g_o in gnot_set:
            df_split = df[df['gN_oT'] == g_o]
            df_split = df_split.copy()
            df_split['queue'] = list(range(len(df_split)))
            df_concat = pd.concat([df_concat, df_split], axis=0)

        df_concat['queue'] = df_concat['queue'].apply(str)

        df_concat['groupId'] = df_concat['groupName_hash'].apply(lambda x: "_" + x[-3:])

        df_concat['opName_primal'] = df_concat['opType_primal'] + df_concat['groupId'] + '_' + df_concat['queue'] + '_1'

        df_concat['opId'] = list(range(len(df_concat)))
        df_concat['relay'] = None
        df_concat['retry'] = None
        df_concat['algType'] = None

        df_hccl_dt['name'] = df_hccl_dt['name'].apply(lambda x: x.lower())
        hccl_data_type_dict = dict(zip(df_hccl_dt['name'], df_hccl_dt['id']))

        string_ids_dict = dict(zip(df_string_ids['value'], df_string_ids['id']))

        string_ids_max = df_string_ids['id'].max()

        df_concat['dataType'] = df_concat['dataType'].apply(lambda x: hccl_data_type_dict[x])

        df_concat['string_id_opType_primal'] = df_concat['opType_primal'].apply(
            lambda x: 1 if x in string_ids_dict else 0
        )
        df_concat['string_id_opName_primal'] = df_concat['opName_primal'].apply(
            lambda x: 1 if x in string_ids_dict else 0
        )
        df_concat['string_id_groupName_primal'] = df_concat['groupName_primal'].apply(
            lambda x: 1 if x in string_ids_dict else 0
        )
        optype_primal_list = list(set(df_concat[df_concat['string_id_opType_primal'] == 0]['opType_primal']))
        opname_primal_list = list(set(df_concat[df_concat['string_id_opName_primal'] == 0]['opName_primal']))
        groupname_primal_list = list(set(df_concat[df_concat['string_id_groupName_primal'] == 0]['groupName_primal']))

        special_primal_list = optype_primal_list + opname_primal_list + groupname_primal_list
        special_id_list = list(range(string_ids_max + 1, string_ids_max + len(special_primal_list) + 1))

        special_id_dict = dict(zip(special_primal_list, special_id_list))

        df_concat['opType'] = df_concat['opType_primal'].apply(
            lambda x: string_ids_dict[x] if x in string_ids_dict else special_id_dict[x]
        )
        df_concat['opName'] = df_concat['opName_primal'].apply(
            lambda x: string_ids_dict[x] if x in string_ids_dict else special_id_dict[x]
        )
        df_concat['groupName'] = df_concat['groupName_primal'].apply(
            lambda x: string_ids_dict[x] if x in string_ids_dict else special_id_dict[x]
        )

        communication_op = df_concat[
            [
                'opName',
                'startNs',
                'endNs',
                'connectionId',
                'groupName',
                'opId',
                'relay',
                'retry',
                'dataType',
                'algType',
                'count',
                'opType',
            ]
        ]
        communication_op = communication_op.copy()
        communication_op.sort_values('startNs', ascending=True, inplace=True)
        communication_op.set_index('opId', inplace=True)
        string_ids_insert = list(map(list, zip(special_id_list, special_primal_list)))

        new_profiler_db = (
            self._prepare_output_profiler_db(data_map.get(Constant.PROFILER_DB_PATH))
            if self.copy_db
            else data_map.get(Constant.PROFILER_DB_PATH)
        )

        DBManager.insert_data_into_db(new_profiler_db, TABLE_STRING_IDS, string_ids_insert)

        self.dump_data(
            data=communication_op, file_name="", table_name=TABLE_COMMUNICATION_OP, custom_db_path=new_profiler_db
        )

        return data_map.get(Constant.RANK_ID)

    def _prepare_output_profiler_db(self, profiler_db_path):
        """
        copy profiler_db to output if not exist
        """
        output_dir = os.path.join(self._cluster_analysis_output_path, self._recipe_name)
        relative_db_path = os.path.relpath(profiler_db_path, start=self._collection_dir)
        relative_dir = os.path.dirname(relative_db_path)

        new_path = os.path.join(output_dir, relative_dir)
        new_db_path = os.path.join(output_dir, relative_db_path)
        PathManager.make_dir_safety(new_path)
        shutil.copyfile(profiler_db_path, new_db_path)
        return new_db_path
