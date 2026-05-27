# Developer Guide

## 1. Development Software for MindStudio Profiler Analyze

| Software| Purpose|
| --- | --- |
| PyCharm (recommended) or VS Code| Writing and debugging Python code|
| Git | Pulling, managing, and committing code|
| Python virtual environment (venv)| Isolating development dependencies|
| Jupyter Notebook (optional)| Debugging `advisor`-related notebook capabilities|

## 2. Development Environment Settings

| Software| Version Requirement| Purpose|
| --- | --- | --- |
| Python | 3.7 or later| Primary development environment|
| pip | Compatible with Python| Installing dependencies and local packages|
| wheel | Latest stable version| Building .whl packages|
| Git | No specific requirement| Code management|

### 2.1 Development Dependencies

Basic dependencies are defined in `requirements/build.txt`, and test dependencies are defined in `requirements/tests.txt`.

The core runtime dependencies include:

- `click`
- `tabulate`
- `networkx`
- `jinja2`
- `PyYaml`
- `tqdm`
- `prettytable`
- `ijson`
- `xlsxwriter`
- `sqlalchemy`
- `numpy`
- `pandas`
- `psutil`
- `pybind11`

### 2.2 Recommended Environment Setup

You are advised to use a virtual environment in the root directory of the repository for development.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements/build.txt
pip install -r requirements/tests.txt
```

## 3. Development Procedure

### 3.1 Code Download and Local Installation

```bash
git clone https://gitcode.com/Ascend/msprof-analyze
cd msprof-analyze
pip install --editable .
```

The command-line entry point is registered in `setup.py`. Once installation is complete, run the following command to verify the setup:

```bash
msprof-analyze --help
msprof-analyze -V
```

### 3.2 Project Directory Structure

The following table describes the key directories of the current repository.

| Directory| Description|
| --- | --- |
| `msprof_analyze/advisor` | `advisor` module|
| `msprof_analyze/cli` | Command-line entry and subcommand registration module|
| `msprof_analyze/cluster_analyse` | Cluster analysis core module|
| `msprof_analyze/compare_tools` | Performance comparison module|
| `msprof_analyze/prof_common` | Common capabilities module|
| `msprof_analyze/prof_exports` | Analysis result export module|
| `requirements` | Dependency lists|
| `test/ut` | Unit test module|
| `test/st` | System test module|
| `docs/zh` | Chinese documentation|

### 3.3 Command-Line Entry Point Development

The command-line entry point for `msprof-analyze` is defined in `msprof_analyze/cli/entrance.py`. The following table describes the currently registered primary subcommands.

| Subcommand| Description|
| --- | --- |
| `advisor` | Performs expert analysis and provides optimization suggestions.|
| `compare` | Performs performance comparison.|
| `cluster` | Performs cluster analysis.|
| `auto-completion` | Provides auto-completion support.|

Key development notes:

1. If a user provides parameters without explicitly specifying a subcommand, the tool defaults to the `cluster` subcommand.
2. If no parameters are provided, the tool displays `cluster --help` by default.
3. The display order in the help menu is controlled by `COMMAND_PRIORITY`.

When adding a new command-line subcommand, synchronize the following changes:

1. Add the corresponding CLI file to `msprof_analyze/cli`.
2. Register the subcommand in `msprof_analyze/cli/entrance.py`.
3. Add parameter descriptions and command examples to the user guide.

### 3.4 Common Function Development Entry Points

#### 3.4.1 Developing `advisor` Capabilities

When adding `advisor` logic, primarily focus on the following:

- `msprof_analyze/advisor/advisor_backend`
- `msprof_analyze/advisor/analyzer`
- `msprof_analyze/advisor/rules`
- `msprof_analyze/advisor/result`

Application scenarios:

1. Add rule identification logic
2. Adjust suggestion generation policies
3. Extend HTML or XLSX result displays

#### 3.4.2 Developing `compare` Capabilities

When adding `compare` logic, primarily focus on the following:

- `msprof_analyze/compare_tools/compare_backend`
- `msprof_analyze/compare_tools/compare_interface`

Application scenarios:

1. Extend GPU/NPU or NPU/NPU comparison dimensions
2. Adjust operator identification and alignment policies
3. Enhance exported comparison results

#### 3.4.3 Developing `cluster_analyse` Capabilities

When adding `cluster_analyse` capabilities, pay attention to the following:

- `msprof_analyze/cluster_analyse/analysis`
- `msprof_analyze/cluster_analyse/cluster_data_preprocess`
- `msprof_analyze/cluster_analyse/cluster_kernels_analysis`
- `msprof_analyze/cluster_analyse/communication_group`
- `msprof_analyze/cluster_analyse/recipes`

Specifically:

1. Advanced analysis features that users can call independently are typically implemented in `recipes`.
2. When adding export formats or query encapsulations, synchronize the changes with `msprof_analyze/prof_exports`.
3. For database reading or general-purpose tools, prioritize reusing logic in `msprof_analyze/prof_common`.

#### 3.4.4 Developing Custom Recipe Analysis Capabilities

When adding a recipe, comply with the following rules:

1. Create a directory and a Python file with the same name under `msprof_analyze/cluster_analyse/recipes`.
2. Inherit from `BaseRecipeAnalysis` and implement the `run` function.
3. If additional parameters are required, implement `add_parser_argument`.
4. When adding database query encapsulation, add a new export class in `msprof_analyze/prof_exports`.

For details about the development methods, see:

- `docs/en/advanced_features/custom_analysis_guide.md`

### 3.5 Common Commands for Local Execution

```bash
# advisor
msprof-analyze advisor all -d ./prof_data -o ./advisor_output

# compare
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output

# cluster_analyse
msprof-analyze cluster -m all -d ./cluster_data -o ./cluster_output
```

To quickly verify command changes based on the source code, prioritize using the editable mode `pip install --editable`, rather than rebuilding the .whl package for every time.

## 4. Testing and Verification

### 4.1 Unit Tests

The repository provides a unified entry point for unit tests:

```bash
python3 test/run_ut.py
```

Unit tests primarily cover the following:

- `advisor`
- `cluster_analyse`
- `compare_tools`
- `prof_common`

After a test runs successfully, the system generates test results and coverage files in `test/report`.

### 4.2 System Tests

The repository provides an entry point for system tests:

```bash
python3 test/run_st.py
```

Currently, system tests primarily cover the following:

- `advisor`
- `cluster_analyse`
- `compare_tools`

The script starts tests for each module in parallel and includes timeout control.

### 4.3 Coverage Statistics

To generate a Python coverage report, run the following command:

```bash
bash test/ut_coverage.sh
```

After the script is executed, the following files are generated in the `test/ut_coverage` directory:

- `coverage.xml`
- `python_coverage_report.log`
- `final.xml`

To compare incremental branch coverage, run the following command:

```bash
bash test/ut_coverage.sh diff master
```

### 4.4 Installation Package Verification

To verify the release package build process, run the following command:

```bash
python3 setup.py bdist_wheel
```

After the build is complete, the system generates the following file in the `dist` directory:

```text
msprof_analyze-{version}-py3-none-any.whl
```

To verify the installation, run the following commands:

```bash
pip3 install ./dist/msprof_analyze-{version}-py3-none-any.whl
msprof-analyze --help
```

## 5. Document Updates

After feature development is complete, update the related documents if the changes affect user workflows or output results.

| Change Type| Document to Update|
| --- | --- |
| Installation, compilation, and upgrade methods| `docs/en/getting_started/install_guide.md`|
| Quick start process| `docs/en/getting_started/quick_start.md`|
| `advisor` feature| `docs/en/user_guide/advisor_instruct.md`|
| `compare` feature| `docs/en/user_guide/compare_tool_instruct.md`|
| `cluster` feature| `docs/en/user_guide/cluster_analyse_instruct.md`|
| Recipe extension capabilities| `docs/en/advanced_features/README.md`|
| Custom recipe development methods| `docs/en/advanced_features/custom_analysis_guide.md`|
| Release notes| `docs/en/release_notes.md`|

## 6. Submission Process Suggestions

1. After feature development is complete, perform local installation verification first.
2. Complete at least one round of unit tests and add system tests where necessary.
3. If changes affect user-visible behavior, update the documentation and example commands accordingly.
4. When adding new analysis capabilities, describe the input data requirements, output files, and application scenarios.
