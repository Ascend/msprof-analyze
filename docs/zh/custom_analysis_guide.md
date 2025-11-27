# 自定义分析规则开发指导
## 简介

自定义分析规则是基于对Profiling的analysis.db和ascend_pytorch_profiler_{rank_id}.db文件进行性能数据分析而开发。与cann_api_sum、compute_op_sum、hccl_sum等参数功能实现类似，可自定义一套性能数据的分析规则。

## 自定义分析规则开发操作步骤

步骤如下：

1. 在msprof-analyze工具代码仓msprof_analyze/cluster_analyse/recipes目录下创建xxx目录和xxx.py文件。

   例如：msprof_analyze/cluster_analyse/recipes/cann_api_sum/cann_api_sum.py，其中目录名和文件名要保持一致，该目录名也会作为使用msprof-analyze cluster工具启动该自定义分析的开关参数。

2. 在xxx.py文件进行性能数据分析规则的开发，开发要求继承BaseRecipeAnalysis，实现run函数。

   典型的run函数实现：

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

   1. `mapper_func`函数：多卡数据查询并合并返回结果。由于集群数据每张卡的数据处理是同样的，因此采用context并行处理集群数据并将结果按序拼装返回。开发只需要实现单卡数据处理的函数`self._mapper_fun`。

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

   2. `reducer_func`函数：对多卡结果分析处理。接收`mapper_func`函数的返回值，进行进一步的集群数据的汇总分析，数据结构采用DataFrame。

   3. `save_db`函数：分析结果保存在cluster_analysis.db中。

   4. `save_notebook`函数：分析结果以csv和stats.ipynb的形式保存。

3. `self._mapper_fun`函数依赖单db数据查询，可通过如下两种方式。

   1. 使用DatabaseService可配置单表的查询。

      可参考：[mstx2commop.py](../../msprof_analyze/cluster_analyse/recipes/mstx2commop/mstx2commop.py)

      使用样例：

      ```Python
      service = DatabaseService(profiler_db_path)
      service.add_table_for_query("ENUM_HCCL_DATA_TYPE", ["id", "name"])  # 第一个参数：表名；第二个参数：字段列表，默认为None，当不填写时表明select *
      service.add_table_for_query("STRING_IDS", ["id", "value"])  #可以添加多个表
      df_dict = service.query_data()  # 将配置的所有表按序查询，以dict形式返回，key为表名，value为数据库查询结果dataframe数据类型
      ```

   2. 维护在msprof_analyze/prof_exports目录下，新建一个py文件，需继承自BaseStatsExport（注：新增之前可以看现有的是否可用，避免重复）如下示例：

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
          ON TYPE_IDS.id == COMMUNICATION_OP.opType
      LEFT JOIN
          STRING_IDS AS NAME_IDS
          ON NAME_IDS.id == COMMUNICATION_OP.opName
      LEFT JOIN
          STRING_IDS AS GROUP_NAME_IDS
          ON GROUP_NAME_IDS.id == COMMUNICATION_OP.groupName
          """
      
      
      class HcclSumExport(BaseStatsExport):
          def __init__(self, db_path, recipe_name):
              super().__init__(db_path, recipe_name)
              self._query = QUERY
      ```
      
      使用样例：df = HcclSumExport(profiler_db_path, analysis_class).read_export_db()，返回的数据类型是dataframe。

4. 分析规则增加拓展参数。

   实现函数add_parser_argument，样例如下：

   ```Python
   @classmethod
   def add_parser_argument(cls, parser):
       parser.add_argument("--top_num", type=str, help="Duration cost top count", default=cls.DEFAULT_TOP_NUM)
   ```

   从self._extra_args里获取对应的扩展参数：

   ```Python
   def __init__(self, params):
       super().__init__(params)
       top_num = self._extra_args.get(self.TOP_NUM, self.DEFAULT_TOP_NUM)
       self.top_num = int(top_num) if isinstance(top_num, str) and top_num.isdigit() else self.DEFAULT_TOP_NUM
   ```
   
5. 执行自定义分析规则命令。

   ```bash
   msprof-analyze cluster -d {cluster profiling data path} --mode xxx --top_num 10
   ```

