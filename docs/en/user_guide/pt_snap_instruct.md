# Memory Snapshot Analysis

## 1. Overview

The `msprof-analyze pt-snap` subcommand provides offline analysis of PyTorch / TorchNPU memory snapshots. A Python API is also available. No separate snapshot analysis package is required.
The tool replays allocation and release events and converts `.pkl` / `.pickle` snapshots into SQLite databases (SnapshotDB) for repeated queries and reports.

Main capabilities:

- Parse memory snapshots into sharded data that can be opened directly in MindStudio Insight for visual analysis.
- Inspect memory changes and peaks, and locate the corresponding events and callstacks.
- Analyze live memory after a selected event and generate an interactive HTML callstack memory tree.
- Find unreleased allocation candidates and investigate lifetimes and allocator gaps.
- Split large snapshots and query complete sharded datasets.

## 2. Quick Start

The following examples use `snapshot.pkl`, a memory snapshot collected and exported from your workload, and device `0`. The filename is a placeholder; replace it with the path to your exported `.pkl` / `.pickle` file. Replace device and event IDs with values from your data.

If you have not collected a snapshot, follow the guide for your device to record allocation history during the relevant workload phase and export the snapshot:

- GPU / PyTorch: See the [PyTorch memory snapshot collection guide](https://docs.pytorch.org/docs/stable/torch_cuda_memory.html).
- Ascend NPU / TorchNPU: See the [Ascend PyTorch memory snapshot guide](https://gitcode.com/Ascend/pytorch/blob/master/docs/en/developer_notes/memory_management/memory_snapshot.md).

### 2.1 Parse Shards and Open Them in MindStudio Insight

Parse a PyTorch / TorchNPU memory snapshot into sharded data that MindStudio Insight can open directly:

```bash
msprof-analyze pt-snap import snapshot.pkl --events-per-slice 500000 --format msinsight --no-focus
```

Steps:

1. Run the command. It creates `snapshot.pkl.msinsight` beside the source snapshot by default. `--events-per-slice 500000` partitions each device's data into shards of 500000 real events, and `--format msinsight` selects the format readable by MindStudio Insight.
2. Open the complete `snapshot.pkl.msinsight` directory in MindStudio Insight to visually analyze the parsed shards, without parsing the original pickle snapshot again in the GUI.
3. When moving the results or copying them to the visualization environment, preserve `manifest.json`, all shard databases, other files, and the directory structure.

Use `--output-dir analysis-output` to select an output parent directory or `--device 0` to parse only that device. Sharded import still loads the entire original pickle and requires sufficient memory.

Explicitly specify `--format msinsight` for results intended for MindStudio Insight. Without it, sharded import defaults to the native format for CLI analysis. The following sections describe single database import and CLI queries; the complete directory above can also be passed as an analysis target.

### 2.2 Import a Snapshot

```bash
msprof-analyze pt-snap import snapshot.pkl --no-focus
```

The default output is `snapshot.pkl.db` beside the source file. `--no-focus` skips updating the default analysis target; without it, import updates `.pt-snap/focus.json` in the current working directory.

Use `--output-dir analysis-output` to select an output parent directory. Import may rebuild and replace a database with the same name. `--no-focus` does not prevent replacement; use a separate output directory to preserve existing results.

### 2.3 Inspect Devices and Event Bounds

```bash
msprof-analyze pt-snap overview snapshot.pkl.db --json
```

Check `device_id` and event bounds in `devices` before running subsequent commands. Start here if you already have a database or complete dataset.

### 2.4 Inspect Peaks and Generate Attribution Reports

```bash
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use memory_peak --json
msprof-analyze pt-snap report peak-memory snapshot.pkl.db --device 0 --metric active --limit 20
```

The query returns each memory metric's peak and event ID. The report attributes active memory after the selected peak event to callstacks. Supported metrics are `active`, `allocated`, and `reserved`.

### 2.5 Generate an Interactive HTML Memory Tree

Replace `1234` with an actual event ID returned by the preceding query:

```bash
msprof-analyze pt-snap report memory-tree snapshot.pkl.db --device 0 --event-id 1234 --format html > memory-tree.html
```

Open `memory-tree.html` in a browser to explore live memory along the call chains after that event.

### 2.6 Import and Analyze Sharded Datasets with the CLI

Import can create a complete dataset containing `manifest.json` and databases partitioned by the number of real events per device:

```bash
msprof-analyze pt-snap import snapshot.pkl --events-per-slice 500000 --no-focus --json
```

The default output directory is `snapshot.pkl.pt-snap-native-v2`. Each shard contains up to the configured number of real events. Add `--device 0` to import only that device or `--output-dir analysis-output` to choose an output parent directory. Sharding does not avoid loading the entire initial pickle; sufficient memory is still required.

Pass the complete dataset directory or its `manifest.json` to analysis commands:

```bash
# Inspect dataset status, devices, and shards.
msprof-analyze pt-snap overview snapshot.pkl.pt-snap-native-v2 --json
msprof-analyze pt-snap metadata snapshot.pkl.pt-snap-native-v2 --json

# Query the global peak across shards and generate attribution.
msprof-analyze pt-snap query snapshot.pkl.pt-snap-native-v2 --device 0 --template-use memory_peak --json
msprof-analyze pt-snap report peak-memory snapshot.pkl.pt-snap-native-v2 --device 0 --metric active --limit 20

# Inspect events in a selected shard; indices start at 0.
msprof-analyze pt-snap query snapshot.pkl.pt-snap-native-v2 --device 0 --template-use event --slice 1 -n 20 --json
```

`--slice` is for event inspection, not a general option for every query or report. Preserve the entire dataset and directory structure. An individual shard database cannot replace the complete dataset for global analysis. You can also set the complete dataset as the default target using `focus`.

### 2.7 Split Snapshot Files

`split` produces independently replayable snapshot files, rather than an immediately queryable sharded database dataset. The following command splits each device's snapshot into four slices, using pickle output by default:

```bash
msprof-analyze pt-snap split snapshot.pkl --slices 4 --output snapshot-slices

# Import one generated file separately.
msprof-analyze pt-snap import snapshot-slices/snapshot__device-0__slice-0.pkl --no-focus
```

Alternatively, split by the maximum number of original trace entries per slice. Choose exactly one of `--max-entries` and `--slices`:

```bash
msprof-analyze pt-snap split snapshot.pkl --device 0 --max-entries 50000 --output snapshot-slices-by-size
```

The output directory must not exist. Use `--format json` for inspectable JSON files, but these files are not accepted by `import`. Keep the default pickle format if subsequent import is required. One split file covers only its own interval and cannot represent the entire snapshot for global analysis.

### 2.8 Common Queries

```bash
# Discover templates and inspect their parameters.
msprof-analyze pt-snap query --list
msprof-analyze pt-snap query --template-info leak_detection

# Return up to 20 unreleased allocation candidates.
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use leak_detection -n 20 --json

# Inspect allocator gaps at peak events.
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use allocator_gap --json
```

| Template | Purpose |
| --- | --- |
| `memory_peak` | allocated, active, and reserved peaks and event IDs |
| `allocation` | Memory counters along the event sequence |
| `event` / `block` | Event or memory block details |
| `active_blocks_at_event` | Active blocks after a selected event |
| `active_memory_callstack_at_event` | Live memory grouped by callstack after a selected event |
| `leak_detection` | Captured dynamic allocations without a recorded completed release |

Set a default target for repeated analysis:

```bash
msprof-analyze pt-snap focus snapshot.pkl.db --device 0
msprof-analyze pt-snap report peak-memory
```

`focus` writes project configuration. Keep passing explicit target paths when you do not want to change that configuration.

## 3. Preparations

### 3.1 Environment Setup

Install msprof-analyze as described in the [msprof-analyze Installation Guide](../install_guide/msprof-analyze_install_guide.md).

Use a version of msprof-analyze that includes memory snapshot analysis. Python **3.7.5 or later** is required. Offline import and analysis require neither PyTorch, CUDA, CANN, nor a GPU/NPU. Snapshot collection requires the appropriate framework and device environment.

```bash
msprof-analyze pt-snap --help
```

### 3.2 Data Preparation and Constraints

An existing SnapshotDB `.db` can be analyzed directly. For an existing complete dataset, specify its directory or `manifest.json`. Import first if you only have a raw snapshot.

> [!NOTE]
>
> Only process trusted pickle files. Deserialization may execute code; import and split are not sandboxes.

## 4. Feature Introduction

### 4.1 Commands and Common Conventions

| Command | Purpose |
| --- | --- |
| `msprof-analyze pt-snap import` | Parse raw snapshots into a single database or sharded dataset |
| `msprof-analyze pt-snap split` | Split raw snapshots into replayable files |
| `msprof-analyze pt-snap overview` | Inspect devices, event bounds, and dataset overview |
| `msprof-analyze pt-snap metadata` | Inspect import metadata and status |
| `msprof-analyze pt-snap query` | Discover templates, inspect parameters, and execute queries |
| `msprof-analyze pt-snap report memory-tree` | Generate a callstack memory tree after a selected event |
| `msprof-analyze pt-snap report peak-memory` | Generate peak memory attribution |
| `msprof-analyze pt-snap focus` | Inspect or set the default analysis target |
| `msprof-analyze pt-snap config` | Inspect or clear legacy global configuration |
| `msprof-analyze pt-snap capabilities` | Inspect versions, query templates, and capability contracts |

```bash
msprof-analyze pt-snap --help
msprof-analyze pt-snap --version
msprof-analyze pt-snap report --help
msprof-analyze pt-snap query --help
```

`--version` (alias `-v`) shows the snapshot component version. Each subcommand supports `--help`, placed after that command.

All leaf commands in the table support `--json` for machine-readable output; readable text is the default. JSON structures vary by command. Check exit status and error messages, not just whether an output file exists. `report memory-tree --format html` cannot be combined with `--json`.

`TARGET` below means a `.db`, complete dataset directory, or `manifest.json`. Commands with an optional target resolve it in this order: explicit path, `PT_SNAP_DB_PATH`, the nearest `.pt-snap/focus.json` found by searching upward from the working directory, and legacy global configuration. When passing an explicit target, also specify `--device` as appropriate; device settings from another target are not inherited. Select one device for multi-device data; peaks from different devices are not summed.

### 4.2 import: Parse Snapshots

Syntax: `msprof-analyze pt-snap import SNAPSHOT [OPTIONS]`. `SNAPSHOT` is a trusted `.pkl` or `.pickle` file.

| Option | Default and Description |
| --- | --- |
| `--output-dir`, `-o` | Output parent directory; defaults to the source directory |
| `--device`, `-d` | Import only the selected device; otherwise process available devices |
| `--no-focus` | Disabled by default: import updates the project target; enable to skip that update |
| `--force` | Disabled by default; rebuild single/native output, but never replace existing compatibility output |
| `--events-per-slice` | No sharding by default; a positive number of real events per device shard |
| `--format` | Defaults to `single-db` without a slice capacity, or `pt-snap-native-v2` with one; also accepts `msinsight` / `compatibility-v1` |
| `--json` | Structured output paths, format, reuse status, and related information |

`single-db` cannot be combined with `--events-per-slice`. Explicit `pt-snap-native-v2` requires a capacity. Existing results can be reused when cache conditions hold; use `--force` to rebuild explicitly. Compatibility output has separate conflict checks; choose a new output location when it already exists.

The `msinsight` format is intended for opening parsed results in MindStudio Insight. OOM and unknown event types are unsupported and cause an error.

```bash
msprof-analyze pt-snap import snapshot.pkl --device 0 --output-dir analysis-output --no-focus --json
msprof-analyze pt-snap import snapshot.pkl --events-per-slice 500000 --format pt-snap-native-v2 --no-focus
msprof-analyze pt-snap import snapshot.pkl --force --no-focus
```

### 4.3 split: Split Snapshots

Syntax: `msprof-analyze pt-snap split SNAPSHOT --output NEW_DIR [STRATEGY] [OPTIONS]`.

| Option | Default and Description |
| --- | --- |
| `--output`, `-o` | Required; the directory must not exist and its parent must exist |
| `--device`, `-d` | Split only the selected device; otherwise process available devices |
| `--slices`, `-s` | Positive slice count per device; choose this or `--max-entries` |
| `--max-entries`, `-m` | Positive maximum original trace entries per slice; choose this or `--slices` |
| `--format` | `pickle` by default; accepts `pickle` or `json` |
| `--json` | Print the result manifest as JSON; does not change generated file format |

See the quick start for both strategies. File names follow `<source-stem>__device-<device>__slice-<index>.pkl` or `.json`. `--format json` selects file contents; `--json` selects command output.

### 4.4 overview: Inspect Data

Syntax: `msprof-analyze pt-snap overview [TARGET] [--json]`.

Returns devices, event bounds, and import metadata status. Dataset output also describes format, status, and shards. This command does not perform attribution or modify the target.

```bash
msprof-analyze pt-snap overview snapshot.pkl.db --json
msprof-analyze pt-snap overview snapshot.pkl.pt-snap-native-v2/manifest.json --json
```

### 4.5 metadata: Inspect Import Records

Syntax: `msprof-analyze pt-snap metadata [TARGET] [--json]`.

Inspect import status, status reasons, and available metadata to investigate provenance and reuse. Unlike `overview`, this command focuses on import records rather than devices and event bounds.

```bash
msprof-analyze pt-snap metadata snapshot.pkl.db --json
```

### 4.6 query: Query Data

Syntax: `msprof-analyze pt-snap query [TARGET] [OPTIONS]`.

| Option | Default and Description |
| --- | --- |
| `--list` | List query templates; no target required |
| `--category` | Filter by `basic`, `statistical`, or `business`; specifying only a category lists that category |
| `--template-info` | Inspect parameters, defaults, output schema, and dataset support without executing a query |
| `--template-use` | Execute the named template |
| `--params` | Template parameters as a JSON object string; keys are case sensitive |
| `--device` | Select a device, otherwise resolve using target configuration and available devices |
| `--slice` | Dataset shard index for event inspection, not a general cross-shard filter |
| `-n` | Unlimited by default; values <= 0 also mean unlimited; not an execution work budget |
| `--exact-total` | Disabled by default; compute an exact matching-row count at additional query cost |
| `--timeout` | Seconds; defaults to `PT_SNAP_QUERY_TIMEOUT`, or unlimited if unset; <= 0 disables |
| `--max-work-rows` | Dataset work row budget, described below |
| `--max-work-bytes` | Dataset work byte budget, described below |
| `--max-scratch-db-bytes` | Dataset derived database budget, described below |
| `--json` | Structured query results and available completeness information |

```bash
msprof-analyze pt-snap query --list --category basic --json
msprof-analyze pt-snap query --template-info event --json
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use event --params '{"min_id":100,"max_id":700,"limit":20,"offset":20}' --exact-total --timeout 10 --json
msprof-analyze pt-snap query snapshot.pkl.db --device 0 --template-use active_blocks_at_event --params '{"event_id":1234,"min_size":1048576}' -n 20 --json
```

Single-quoted JSON examples work in Bash and PowerShell; use the appropriate escaping for other shells. Replace example event IDs with valid IDs. Template `limit` / `offset` parameters control pagination; `-n` limits caller output and does not replace pagination or work budgets.

#### 4.6.1 All Query Templates

| Template | Purpose and Main Parameters |
| --- | --- |
| `allocation` | Memory timeline; `min_id` / `max_id`, `min_allocated` / `min_active` / `min_reserved`, sorting, and pagination |
| `event` | Event details; `id`, event range, `action`, `address`, `size`, `stream`, memory counter filters, `stack_bytes`, sorting, and pagination |
| `block` | Block details; `id`, `address`, size ranges, `requestedSize`, allocation/release event ranges, sorting, and pagination |
| `event_frames` | Structured event callstack frames; required `event_id`, `frame_order` defaults to `original`, also accepts `root_first`; complete datasets unsupported |
| `memory_peak` | Independent counter peaks and events; optional `start_id` / `end_id` |
| `allocator_gap` | Same-event gaps at peak events; optional `start_id` / `end_id` |
| `active_blocks_at_event` | Active blocks after an event; required `event_id`, optional `include_static`, `min_size`, sorting, and pagination |
| `callstack_analysis` | Real stack-bearing actions grouped by complete callstack; `min_count=5`, `min_size=0`, optional `limit` |
| `active_memory_callstack_at_event` | Live memory grouped by callstack; required `event_id`, `include_static=true`, `min_size=0`, `top_n=20`, `stack_bytes=-1` |
| `active_memory_frame_tree_at_event` | Frame memory tree after an event; required `event_id`, optional `include_static=true`, `min_size=0` |
| `leak_detection` | Captured allocations without completed release; `min_size=0`, optional `limit` |
| `freed_block_lifetime` | Freed blocks bucketed by allocation-to-release event distance, not elapsed time; no template parameters |
| `preexisting_live` | Pre-tracing allocations still live at an event; required `event_id` |

All templates except `event_frames` declare support for complete sharded datasets. Inspect `--template-info` for full fields, sorting choices, and boundary semantics. Dataset support does not make an individual shard a complete snapshot. Missing original structured frame information cannot be recovered from text alone.

### 4.7 report memory-tree: Callstack Memory Trees

Syntax: `msprof-analyze pt-snap report memory-tree [TARGET] --event-id ID [OPTIONS]`.

| Option | Default and Description |
| --- | --- |
| `--event-id` | Required; active memory after the selected event |
| `--device`, `-d` | Select a device |
| `--include-static` / `--exclude-static` | Include static memory by default |
| `--min-size` | Minimum individual block size in bytes; default 0 |
| `--format` | `text` by default; `text` or `html`, both on standard output |
| `--timeout` | Query deadline in seconds; <= 0 disables |
| `--max-work-rows` / `--max-work-bytes` / `--max-scratch-db-bytes` | Shared dataset limits, described below |
| `--json` | Structured report; only compatible with text format |

```bash
msprof-analyze pt-snap report memory-tree snapshot.pkl.db --device 0 --event-id 1234 --exclude-static --min-size 1048576
msprof-analyze pt-snap report memory-tree snapshot.pkl.db --device 0 --event-id 1234 --format html > memory-tree.html
msprof-analyze pt-snap report memory-tree snapshot.pkl.pt-snap-native-v2 --device 0 --event-id 1234 --json
```

Supports single databases and complete datasets. Available tree detail depends on the stored frames. Redirect HTML output to a file and open it in a browser.

### 4.8 report peak-memory: Peak Attribution

Syntax: `msprof-analyze pt-snap report peak-memory [TARGET] [OPTIONS]`.

| Option | Default and Description |
| --- | --- |
| `--device`, `-d` | Select a device |
| `--metric` | `active` by default; `active`, `allocated`, or `reserved` selects the peak event |
| `--include-static` / `--exclude-static` | Include the static memory group by default |
| `--limit`, `-n` | Default 20 dynamic callstack groups; static/preexisting groups are additional |
| `--stack-bytes` | Default -1 for full text; 0 for identity only, positive values limit UTF-8 bytes per callstack text |
| `--start-id` / `--end-id` | Optional real event bounds for peak selection |
| `--timeout` | One deadline for the entire report, in seconds; <= 0 disables |
| `--max-work-rows` / `--max-work-bytes` / `--max-scratch-db-bytes` | Shared dataset limits, described below |
| `--json` | Structured report, including coverage and truncation information |

```bash
msprof-analyze pt-snap report peak-memory snapshot.pkl.db --device 0 --metric reserved --start-id 100 --end-id 700 --limit 20 --stack-bytes 2048 --timeout 10 --json
```

The metric selects the event to attribute. Attribution still describes active memory after that event; callstack totals must not be treated as the full reserved total. `--stack-bytes` is neither an overall JSON size cap nor a token budget.

### 4.9 Shared Query and Report Resource Limits

These options apply to `query`, `report memory-tree`, and `report peak-memory`. They bound intermediate dataset work, not initial pickle loading or process RSS.

| Option | Default | Environment Variable and Constraints |
| --- | --- | --- |
| `--max-work-rows` | 100000 | `PT_SNAP_MAX_WORK_ROWS`; positive cumulative fetched/output work rows |
| `--max-work-bytes` | 67108864 (64 MiB) | `PT_SNAP_MAX_WORK_BYTES`; positive cumulative serialized work bytes |
| `--max-scratch-db-bytes` | 536870912 (512 MiB) | `PT_SNAP_MAX_SCRATCH_DB_BYTES`; 0 disables derived databases; otherwise 4096–4294967296 |

Explicit options override the corresponding environment variables. Adjust the budget identified by an error; increasing `-n` does not increase work budgets. Queries composed within a report share the relevant budgets. Query/report timeout defaults to `PT_SNAP_QUERY_TIMEOUT`, or unlimited when unset.

### 4.10 focus: Default Analysis Target

Syntax: `msprof-analyze pt-snap focus [TARGET] [OPTIONS]`.

| Option | Default and Description |
| --- | --- |
| `TARGET` | Omit with no device option to inspect the current target; provide a path to set it |
| `--device`, `-d` | Set the device; without a path, update the current target's device setting |
| `--session` | Validate the path and print a shell export; does not modify the parent environment; incompatible with `--device` and `--global` |
| `--global` | Save to legacy global configuration instead of project `.pt-snap/focus.json` |
| `--json` | Structured state; session mode returns environment information |

```bash
msprof-analyze pt-snap focus --json
msprof-analyze pt-snap focus snapshot.pkl.db --device 0
msprof-analyze pt-snap focus --device 1
msprof-analyze pt-snap focus snapshot.pkl.pt-snap-native-v2 --session --json
msprof-analyze pt-snap focus snapshot.pkl.db --global --device 0
```

Text output from `--session` uses POSIX shell syntax. PowerShell users can read the path from JSON output and set `$env:PT_SNAP_DB_PATH`. A session path does not carry device configuration; specify the device in subsequent commands.

### 4.11 config: Legacy Global Configuration

Syntax: `msprof-analyze pt-snap config [OPTIONS]`. This manages legacy global configuration, not project focus or environment variables.

| Option | Description |
| --- | --- |
| No options | Show global configuration |
| `--path` | Show the global configuration file path |
| `--clear` | Clear global configuration without deleting analysis databases |
| `--json` | Structured output |

```bash
msprof-analyze pt-snap config --json
msprof-analyze pt-snap config --path
msprof-analyze pt-snap config --clear
```

Run `--path` and `--clear` separately. If both are passed, displaying the path takes precedence and no clearing occurs.

### 4.12 capabilities: Capability Catalog

Syntax: `msprof-analyze pt-snap capabilities [--json]`. No analysis target is required.

Text output lists the component version, template categories, descriptions, and parameter names. JSON additionally exposes parameter contracts, output schemas, field semantics, and dataset support declarations for automation.

```bash
msprof-analyze pt-snap capabilities --json
```

## 5. Output Description

### 5.1 Output Files

| Operation | Default Output | How to Inspect |
| --- | --- | --- |
| Single database import | `snapshot.pkl.db` | Pass to `overview`, `query`, or `report` |
| Native sharded import | `snapshot.pkl.pt-snap-native-v2/` | Preserve all members and pass the directory or `manifest.json` |
| MindStudio Insight format import | `snapshot.pkl.msinsight/` | Open the complete directory in MindStudio Insight; CLI analysis also accepts the directory or `manifest.json` |
| Snapshot split | `.pkl` / `.json` files under `--output` | Import pickle files individually; use JSON for inspection |
| HTML memory tree | Standard output, saved by redirection | Open the saved HTML file in a browser |
| JSON queries and reports | Standard output | Parse automatically and inspect completeness/truncation flags |

### 5.2 Interpretation and Constraints

- Sizes are in bytes: `1 MiB = 1,048,576 bytes`. Event IDs represent sequence order, not timestamps.
- `allocated` counts allocated blocks; `active` also includes blocks awaiting completed release; `reserved` counts allocator-held segments, not all process or device memory.
- Independent metric peaks may occur at different events and must not be subtracted. Use `allocator_gap` or a peak report for same-event comparisons. Large gaps alone do not prove fragmentation or leaks.
- `leak_detection` returns candidates, not confirmed leaks. Filters and limits can make reports incomplete; inspect coverage and fields such as `has_more`, `truncated`, and `total_is_exact` where available.
- Built-in queries and reports read source databases without modifying them. Import, split, and focus write files. Import loads the complete pickle, so large inputs require sufficient memory.

Inspect additional help using `msprof-analyze pt-snap <COMMAND> --help`.

## 6. Python API

```python
from pathlib import Path
from msprof_analyze.pt_snap import SnapshotAnalyzer

with SnapshotAnalyzer(db_path=Path("snapshot.pkl.db"), device_id=0) as analyzer:
    result = analyzer.execute_query("memory_peak")
    print(result["rows"])
```

Use a context manager to release database connections when analysis finishes.
