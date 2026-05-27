# Cluster Operator Duration Analysis

## Overview

The cluster operator duration analysis feature uses `cluster_prof_info_analysis.py` to collect and display statistics for the top N operators in cluster scenarios. It identifies operators with the fastest, slowest, and average duration, as well as the highest variance, on each rank based on the `op_summary` information of the multi-rank profile data.

Currently, operator information for multiple ranks can be obtained only by viewing the profile data of each rank individually. Compute performance differences between operators across different ranks cannot be compared directly.

## Preparations

**Environment Setup**

Copy [cluster_prof_info_analysis.py](../../../msprof_analyze/cluster_analyse/cluster_kernels_analysis/cluster_prof_info_analysis.py) to a directory and install the required Python libraries.

```bash
pip install pandas
pip install plotly
```

**Data Preparation**

Copy the profile data of all nodes to an environment. The profile data must be placed under `node*` directories. For example, in a cluster scenario with 2 nodes and 16 ranks, where each node has 8 ranks, copy the profile data to a directory structure as follows:

```bash
├── node0             # It can be node0 or node0_xxx, indicating a node.
│   ├── PROF_XXXXX    # Profile data of a single rank. msProf profile data parsing must be completed.
│       ├── SUMMARY
│           ├── op_summary_XX.csv
|   ......               # Aggregated profile data of all eight ranks under the node
├── node1             # It can be node1 or node1_xxx, indicating a node.
│   ├── PROF_XXXXX    # Profile data of a single rank.
│       ├── SUMMARY
│           ├── op_summary_XX.csv   # op_summary table used for parsing.
|   ......             
```

## Cluster Operator Duration Analysis

**Function**

Collects and displays statistics for the top N operators with the fastest, slowest, and average duration, as well as the highest variance, on each rank.

**Precautions**

None

**Syntax**

```bash
python3 cluster_prof_info_analysis.py -d <data_path> -t <type> [-n <top_n>]
```

**Command-line Options**

| Option| Mandatory (Yes/No)| Description                                             |
| ---- | -------- | ------------------------------------------------- |
| -d   | Yes     | Specifies the profile data directory for cluster scenarios. Enter the parent directory of the `node*` directories.<br>&#8226; If `op_summary` does not exist in some directories, no information is displayed and no error is reported.<br>&#8226; If no `op_summary` data exists in the specified directory, an error is reported indicating that the data files cannot be found.<br>&#8226; If data in the `op_summary` column of a file is incorrect or cannot be read, the specific faulty file is identified.|
| -t   | Yes     | Specifies the output file type for the analysis results. The values can be: `html` (default), `csv`, or `all`.<br>If the configuration is incorrect, an error message is displayed along with the correct configuration format.|
| -n   | No     | (HTML only) Specifies the number of top N (default: `10`) operators to be displayed based on average duration. Values exceeding 30 may increase processing time.<br>&#8226; The value must be greater than 0. If a value less than or equal to 0 is entered, data for only one operator is exported by default.<br>&#8226; If the value specified exceeds the total number of operators, the total number of operators is used.|

**Example**

```bash
python3 cluster_prof_info_analysis.py –d ./cluster_data -t csv -n 5
```

## Output File Description

### `cluster_op_time_analysis.csv`

Classifies operators by `op_name`, `input_shape`, `input_size`, and `output_shape`. Statistics, such as the maximum, minimum, variance, average, and range of the duration, are collected and displayed for each operator category across different ranks and nodes.

### `xxx_info.html`

HTML files for various features (`time` and `ratio`), displaying the box plots of the top N operators.

`time` and `ratio` indicate the duration and proportion fields in the performance metrics of AI Core and AI Vector Core operators.

The execution duration and proportion of top N operators are displayed as box plots in the HTML file.

One coordinate system is generated for each of the top N operators. Each system represents one operator feature. Coordinates are sorted from left to right and then downward based on the average value of `total_time`.

- Horizontal coordinate: `node_device` represents the specific rank on a node, sorted in ascending order.
- Vertical coordinate: indicates the duration.
- Coordinate name: displayed below the coordinate system in the format of `op_name-input_shape`.
