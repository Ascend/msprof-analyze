# Custom Analysis Rule Development Guide

## Overview

Custom analysis rules are developed based on the analysis of profile data within `analysis.db` and `ascend_pytorch_profiler_{rank_id}.db` files. Similar to the implementation of parameters such as `cann_api_sum`, `compute_op_sum`, and `hccl_sum`, these rules allow you to define custom logic for profile data analysis.

## Procedure for Developing Custom Analysis Rules

Perform the following steps:

1. Create an `xxx` directory and an `xxx.py` file in `msprof_analyze/cluster_analyse/recipes` of the `msprof-analyze` code repository.

   Here is an example: `msprof_analyze/cluster_analyse/recipes/cann_api_sum/cann_api_sum.py`. The directory name must match the file name. This directory name also serves as the command-line flag to enable the custom analysis rule when you run the `msprof-analyze` cluster tool.

2. Develop profile data analysis rules in the `xxx.py` file by inheriting from the `BaseRecipeAnalysis` class and implementing the `run` function.

   The typical implementation of the `run` function is as follows:

   ```python
   def run(self, context):
       mapper_res = self.mapper_func(context)
       self.reducer_func(mapper_res)
       if self._export_type == "db":
           self.save_db()
       elif self._export_type == "notebook":
           self.save_notebook()
       else:
           logger.error("Unknown export type.")
   ```

   1. `mapper_func` function: queries multi-rank data and merges the results. Since data processing for each rank in a cluster is identical, the context is used to process profile data in parallel and assemble the results in sequence. You only need to implement the `self._mapper_func` function for single-rank data data processing.

      ```python
      def mapper_func(self, context):
          return context.wait(
              context.map(
                  self._mapper_func,
                  self._get_rank_db(),
                  analysis_class=self._recipe_name
              )
          )
      ```

      ```python
      def _mapper_func(self, data_map, analysis_class):
          """
          Extract the profiling data required for cluster analysis from each device, and then aggregate the 
          results from each device to be processed by a reduce function.
          Params:
              data_map: eg. {"RANK_ID": 1, "profiler_db_path": "xxxx/ascend_pytorch_profiler_1.db"}
              analysis_class: hccl_sum, compute_op_sum, cann_api_sum, mstx_sum......
          """
          pass
      ```

   2. `reducer_func`: analyzes and processes multi-rank results. This function receives the return values from `mapper_func` and summarizes the cluster data into a `DataFrame`.

   3. `save_db`: saves analysis results in `cluster_analysis.db`.

   4. `save_notebook`: saves analysis results in CSV and `stats.ipynb` formats.

3. The `self._mapper_func` function relies on querying data from a single database. You can use either of the following two methods:

   1. Use `DatabaseService` to configure single-table queries.

      For details, see [mstx2commop.py](../../../msprof_analyze/cluster_analyse/recipes/mstx2commop/mstx2commop.py).

      Example:

      ```Python
      service = DatabaseService(profiler_db_path)
      service.add_table_for_query("ENUM_HCCL_DATA_TYPE", ["id", "name"])  # First argument: table name; second argument: field list. By default, no field is specified and SELECT * is executed to query all fields.
      service.add_table_for_query("STRING_IDS", ["id", "value"])  # Multiple tables can be added.
      df_dict = service.query_data() # Queries all specified tables in sequence and returns a dict (key: table name; value: DataFrame-type query result).
      ```

   2. Create a new .py file in the `msprof_analyze/prof_exports` directory. The class must inherit from `BaseStatsExport`. To avoid duplication, check if an existing file meets your needs before creating a new one. The sample code is as follows:

      ```Python
      from msprof_analyze.prof_exports.base_stats_export import BaseStatsExport
      
      QUERY = """
      SELECT
          NAME_IDS.value AS "OpName",
          TYPE_IDS.value AS "OpType",
          round(endNs - startNs) AS "Duration",
          GROUP_NAME_IDS.value AS "GroupName"
      FROM
          COMMUNICATION_OP
      LEFT JOIN
          STRING_IDS AS TYPE_IDS
          ON TYPE_IDS.id = COMMUNICATION_OP.opType
      LEFT JOIN
          STRING_IDS AS NAME_IDS
          ON NAME_IDS.id = COMMUNICATION_OP.opName
      LEFT JOIN
          STRING_IDS AS GROUP_NAME_IDS
          ON GROUP_NAME_IDS.id = COMMUNICATION_OP.groupName
          """
      
      
      class HcclSumExport(BaseStatsExport):
          def __init__(self, db_path, recipe_name):
              super().__init__(db_path, recipe_name)
              self._query = QUERY
      ```
      
      Example: `df = HcclSumExport(profiler_db_path, analysis_class).read_export_db()`. The returned data type is `DataFrame`.

4. Add extended parameters to analysis rules.

   Implement the `add_parser_argument` function. Example:

   ```Python
   @classmethod
   def add_parser_argument(cls, parser):
       parser.add_argument("--top_num", type=str, help="Duration cost top count", default=cls.DEFAULT_TOP_NUM)
   ```

   Obtain the corresponding extended parameters from `self._extra_args`:

   ```Python
   def __init__(self, params):
       super().__init__(params)
       top_num = self._extra_args.get(self.TOP_NUM, self.DEFAULT_TOP_NUM)
       self.top_num = int(top_num) if isinstance(top_num, str) and top_num.isdigit() else self.DEFAULT_TOP_NUM
   ```
   
5. Run the custom analysis rule command.

   ```bash
   msprof-analyze cluster -d {cluster profiling data path} --mode xxx --top_num 10
   ```
