# Communication Statistics for Ultra-Large Clusters

## 1. Overview

Use `cluster_statistic` to analyze communication in ultra-large clusters. It summarizes communication time, transmission metrics, and operator durations across ranks so you can compare rank performance and identify slow ranks.

## 2. Data Preparation

Collect the PyTorch DB-format profile data for all ranks in one directory. Keep the original directory structure and the files that identify each rank. The data must include the communication analysis database `analysis.db`. For the expected directory structure, see the [Cluster Analysis Guide](../user_guide/cluster_analyse_instruct.md).

## 3. Usage

```bash
msprof-analyze cluster -m cluster_statistic -d ./cluster_data -o ./statistic_output
```

By default, the command analyzes all discoverable ranks. Add `--rank_list 0,2` to select specific ranks or `--agent` to get the execution result as JSON.

## 4. Output

The example writes results to `./statistic_output/cluster_analysis_output/cluster_analysis.db`. If you omit `-o`, `cluster_analysis_output` is created under the directory specified by `-d`. The available data determines which tables are generated. A rerun replaces each table it writes if a table with that name already exists.

| Table | Purpose |
| --- | --- |
| `CommTimeStatistic` | Summarizes total communication, transfer, wait, synchronization, and idle times by step, rank, and communication domain. |
| `TransitStatistic` | Summarizes transfer size, transfer time, bandwidth, and packet size distribution by step, rank, communication domain, and transport type. |
| `CommOpStatistic` | Summarizes total, minimum, and maximum durations across ranks by step, communication domain, and full operator name. It also records the ranks with the minimum and maximum durations and the number of ranks with valid durations. |
| `CommunicationGroupMapping` | Records communication domains, communication types, rank sets, and parallel group information. Join this table to the statistics tables on `group_name`. |
| `ClusterBaseInfo` | Records basic cluster information, such as parallel strategy parameters, when cluster configuration is available. |

If a source table lacks a `step` column, the command uses the string `step` as the default value. Unavailable statistics are recorded as `NULL`.

## 5. Statistics Table Fields

### 5.1 `CommTimeStatistic`

| Field | Description |
| --- | --- |
| `step` | Step identifier. |
| `rank_id` | Global rank ID. |
| `group_name` | Communication domain identifier. |
| `comm_total_time` | Sum of communication operator durations, in ms. |
| `comm_transit_time` | Sum of communication operator transfer times, in ms. |
| `comm_wait_time` | Sum of communication operator wait times, in ms. |
| `comm_sync_time` | Sum of communication operator synchronization times, in ms. |
| `comm_free_time` | Sum of idle time within communication operators, in ms. |

### 5.2 `TransitStatistic`

| Field | Description |
| --- | --- |
| `step` | Step identifier. |
| `rank_id` | Global rank ID. |
| `group_name` | Communication domain identifier. |
| `band_type` | Transport type, such as `RDMA`. |
| `transit_size` | Total amount of data transferred, in MB. |
| `transit_time` | Total transfer time, in ms. |
| `bandwidth` | Aggregate bandwidth, in GB/s. When transfer time is greater than zero, this is `transit_size / transit_time`. |
| `package_distribution` | JSON array sorted by packet size in ascending order. Each element contains `package_size` in MB and `count`, the number of transfers for that size. |

### 5.3 `CommOpStatistic`

| Field | Description |
| --- | --- |
| `step` | Step identifier. |
| `group_name` | Communication domain identifier. |
| `op_name` | Full communication operator name, including any original suffix. |
| `total_time` | Sum of valid durations for this operator across ranks, in ms. |
| `min_time` | Minimum valid duration for this operator across ranks, in ms. |
| `min_time_rank` | Global rank ID with the minimum duration. |
| `max_time` | Maximum valid duration for this operator across ranks, in ms. |
| `max_time_rank` | Global rank ID with the maximum duration. |
| `rank_count` | Number of ranks with a valid duration for this operator. |

When ranks tie for the minimum or maximum duration, the smallest rank ID is recorded.
