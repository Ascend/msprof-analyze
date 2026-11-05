# FAQ

## "missing analysis DB file (analysis.db)" is reported during cluster analysis

### Symptom

After running `msprof-analyze cluster -d <profiling_path>`, the message `missing analysis DB file (analysis.db) for N rank(s) [rank_id,...]; these ranks will be skipped` is printed, and these ranks are skipped in analysis items that depend on `analysis.db`. If no rank has `analysis.db`, `CommunicationGroupMap` cannot generate the communication group table, and `CommunicationTimeSum` prints `Create CommunicationGroupMap table failed! Skip CommunicationTimeSum.` and is skipped.

### Cause

`analysis.db` is generated only in multi-device or cluster scenarios where communication exists. If only compute data is collected, no rank directory contains this file, and analysis items that depend on it are skipped. This is expected behavior, not a tool error.

### Resolution

1. Check whether `analysis.db` exists in the `ASCEND_PROFILER_OUTPUT` directory of each rank subdirectory (for MindSpore and msProf data, the file is `communication_analyzer.db`) to determine whether it is missing for all ranks or only some ranks.
2. Check whether communication (HCCL) operator data collection is enabled in the collection command or configuration. If it is not enabled, the absence of communication-related analysis items is expected behavior. To obtain communication domain analysis results, collect the data again.
3. Check whether the directory structure meets the [cluster input directory requirements](../user_guide/cluster_analyse_instruct.md#23-requirements-for-the-cluster-input-directory): `-d` points to the cluster root directory, each device has one profiling subdirectory, and each subdirectory retains `ASCEND_PROFILER_OUTPUT` and `profiler_info_{rank_id}.json`.
4. If communication data collection is enabled, check whether `analysis.db` is missing during data transfer or copy (for example, only `ascend_pytorch_profiler_{rank_id}.db` is copied), and whether the complete set of files with the same name is retained for each rank.

## "Failed to get rank_id for some paths" is reported during cluster analysis

### Symptom

After running `msprof-analyze cluster -d <profiling_path>`, the message `Failed to get rank_id for some paths. Affected paths: [...]` is printed, and the paths listed in the warning are excluded from subsequent analysis.

### Cause

The tool cannot identify the rank from the directory (usually because `profiler_info_{rank_id}.json` is missing or renamed, or the rank identifier in the file name is not a number), so the directory is excluded from the analysis.

### Resolution

1. Go to each path listed in the warning and check that `profiler_info_{rank_id}.json` exists and that the content between `profiler_info_` and `.json` is a numeric rank_id.
2. Check that the root directory specified by `-d` contains only the data of all ranks from the current profiling session, and that the directory structure matches the example in the [cluster input directory requirements](../user_guide/cluster_analyse_instruct.md#23-requirements-for-the-cluster-input-directory).
