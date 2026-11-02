# msprof-analyze Developer Guide

## 1. Development Software for msprof-analyze

| Software | Purpose |
| --- | --- |
| PyCharm (recommended) or VS Code | Writing and debugging Python code |
| Git | Pulling, managing, and committing code |
| Python virtual environment (venv) | Isolating development dependencies |
| Jupyter Notebook (optional) | Debugging Advisor-related notebook capabilities |

## 2. Development Environment Configuration

### 2.1 Method 1: One-Click devcontainer Development Environment (Recommended)

msprof-analyze includes a [devcontainer](https://containers.dev/) development environment configuration. After opening the repository in VS Code, you can enter a standardized container with one click without manually installing any dependencies. The container automatically completes the following preparations:

- Python 3 environment
- Preinstalled pip dependencies (wheel, pre-commit, and bandit)
- Automatic pre-commit activation
- Git identity synchronization

**Prerequisites:**

| Environment | Requirement |
| --- | --- |
| PC | VS Code with the Dev Containers and Remote-SSH extensions installed |
| Linux server | Docker service running |

**Usage steps:**

1. Clone the msprof-analyze repository to the Linux server.
2. Connect VS Code to the server through Remote-SSH and open the repository directory.
3. VS Code automatically detects the `.devcontainer` configuration. Click **Reopen in Container** in the lower-left corner.
4. After the container starts, `post-create.sh` runs automatically to complete initialization.
5. Press `Ctrl+Shift+P`, select `Tasks: Run Task`, and choose a build or test task.

**VS Code built-in tasks:**

| Task | Shortcut | Description |
| --- | --- | --- |
| `Build: Release Mode` | `Ctrl+Shift+B` | Builds the WHL package with one click |
| `Test: Run Unit Tests` | - | Runs all unit tests |
| `Clean: All Workspace` | - | Cleans build artifacts |

**Code navigation and debugging:** Python provides semantic navigation (F12) and type inference through Pylance. Press `F5` and select `Python: Debug Active File` to start debugpy debugging.

### 2.2 Method 2: Manual Environment Configuration

Follow the [msprof-analyze Installation Guide - Source Installation](../install_guide/msprof-analyze_install_guide.md#231-environment-setup) section to set up the build and test environment.

> **Note:** The build method of the environment image and the associated software versions are maintained in the MindStudio unified image creation guide. This repository does not define them again.

After entering the build container environment, run the following steps to install dependencies:

```bash
pip install -U pip wheel
pip install -r requirements/build.txt
pip install -r requirements/tests.txt
```

## 3. Development Procedure

### 3.1 Code Download and Local Installation

After entering the build container environment, run the following steps to download the code and install it locally:

```bash
git clone https://gitcode.com/Ascend/msprof-analyze
cd msprof-analyze
pip install --editable .
```

The command-line entry point is registered in `setup.py`. After installation, use the following commands to verify:

```bash
msprof-analyze --help
msprof-analyze -V
```

### 3.2 Project Directory Description

The key directories in the current repository are as follows:

| Directory | Description |
| --- | --- |
| `msprof_analyze/advisor` | Expert suggestion module |
| `msprof_analyze/cli` | Command-line entry and subcommand registration |
| `msprof_analyze/cluster_analyse` | Main cluster analysis module |
| `msprof_analyze/compare_tools` | Performance comparison module |
| `msprof_analyze/prof_common` | Common capability module |
| `msprof_analyze/prof_exports` | Analysis result export modules |
| `requirements` | Dependency manifests |
| `test/ut` | Unit tests |
| `test/st` | System tests |
| `docs/zh` | Chinese documentation |

### 3.3 Command-Line Entry Development

The command entry of `msprof-analyze` is defined in `msprof_analyze/cli/entrance.py`. The main subcommands currently registered are as follows:

| Subcommand | Description |
| --- | --- |
| `advisor` | Expert suggestion analysis |
| `compare` | Performance comparison |
| `cluster` | Cluster analysis |
| `auto-completion` | Automatic completion |

During development, note the following:

1. If the user does not explicitly enter a subcommand but provides parameters, the tool automatically adds the `cluster` subcommand.
2. If the user provides no parameters, the tool displays `cluster --help` by default.
3. The display order of command help is controlled by `COMMAND_PRIORITY`.

When adding a command-line subcommand, you usually need to modify:

1. Add the corresponding CLI file under `msprof_analyze/cli`.
2. Register the subcommand in `msprof_analyze/cli/entrance.py`.
3. Add parameter and example descriptions to user documentation.

### 3.4 Common Feature Development Entries

#### 3.4.1 Developing Advisor Capabilities

When adding expert suggestion analysis logic, focus on:

- `msprof_analyze/advisor/advisor_backend`
- `msprof_analyze/advisor/analyzer`
- `msprof_analyze/advisor/rules`
- `msprof_analyze/advisor/result`

Applicable scenarios:

1. Add rule identification logic.
2. Adjust the suggestion generation policy.
3. Extend HTML/XLSX result presentation.

#### 3.4.2 Developing Compare Capabilities

When adding performance comparison logic, focus on:

- `msprof_analyze/compare_tools/compare_backend`
- `msprof_analyze/compare_tools/compare_interface`

Applicable scenarios:

1. Extend GPU/NPU or NPU/NPU comparison dimensions.
2. Adjust operator identification and alignment policies.
3. Enhance comparison result export content.

#### 3.4.3 Developing Cluster Analyze Capabilities

When adding cluster analysis capabilities, focus on:

- `msprof_analyze/cluster_analyse/analysis`
- `msprof_analyze/cluster_analyse/cluster_data_preprocess`
- `msprof_analyze/cluster_analyse/cluster_kernels_analysis`
- `msprof_analyze/cluster_analyse/communication_group`
- `msprof_analyze/cluster_analyse/recipes`

Notes:

1. Advanced analysis capabilities that users can call independently usually reside in `recipes`.
2. To add an export format or query wrapper, you usually need to modify `msprof_analyze/prof_exports` accordingly.
3. For database reads and common utilities, reuse `msprof_analyze/prof_common` first.

#### 3.4.4 Developing Custom Recipe Analysis Capabilities

When adding a Recipe, follow the existing rules:

1. Create a directory and Python file with the same name under `msprof_analyze/cluster_analyse/recipes`.
2. Inherit `BaseRecipeAnalysis` and implement the `run` function.
3. Implement `add_parser_argument` when additional parameters are required.
4. If a new database query wrapper is required, add an export class under `msprof_analyze/prof_exports`.

For detailed development instructions, see:

- `docs/en/advanced_features/custom_analysis_guide.md`

### 3.5 Common Local Run Commands

```bash
# Expert suggestions
msprof-analyze advisor all -d ./prof_data -o ./advisor_output

# Performance comparison
msprof-analyze compare -d ./ascend_pt -bp ./gpu_trace.json -o ./compare_output

# Cluster analysis
msprof-analyze cluster -m all -d ./cluster_data -o ./cluster_output
```

To quickly verify command changes from source code, use `pip install --editable .` instead of rebuilding the WHL package each time.

## 4. Testing and Verification

### 4.1 Unit Tests

The repository provides a unified unit test entry:

```bash
python3 test/run_ut.py
```

Unit tests mainly cover:

- `advisor`
- `cluster_analyse`
- `compare_tools`
- `prof_common`

After a successful run, test results and coverage files are generated in `test/report`.

### 4.2 System Tests

The repository provides a system test entry:

```bash
python3 test/run_st.py
```

Current system tests mainly cover:

- `advisor`
- `cluster_analyse`
- `compare_tools`

The script runs module tests in parallel and sets timeout control.

### 4.3 Coverage Statistics

To generate a Python coverage report, run:

```bash
bash test/ut_coverage.sh
```

After execution, the following files are generated in the `test/ut_coverage` directory:

- `coverage.xml`
- `python_coverage_report.log`
- `final.xml`

To compare branch incremental coverage, run:

```bash
bash test/ut_coverage.sh diff master
```

### 4.4 Installation Package Verification

To verify the release package build process, run:

```bash
python3 setup.py bdist_wheel
```

After the build is complete, the following file is generated in the `dist` directory:

```text
msprof_analyze-{version}-py3-none-any.whl
```

Then use the following commands to verify the installation:

```bash
pip3 install ./dist/msprof_analyze-{version}-py3-none-any.whl
msprof-analyze --help
```

## 5. Documentation Updates

After feature development is complete, if the change affects user operations or output results, update the relevant documentation.

| Change Type | Document to Update |
| --- | --- |
| Installation, compilation, or upgrade method | `docs/en/install_guide/msprof-analyze_install_guide.md` |
| Quick start workflow | `docs/en/quick_start/msprof-analyze_quick_start.md` |
| Advisor features | `docs/en/user_guide/advisor_instruct.md` |
| Compare features | `docs/en/user_guide/compare_tool_instruct.md` |
| Cluster features | `docs/en/user_guide/cluster_analyse_instruct.md` |
| Recipe extension capabilities | `docs/en/advanced_features/README.md` |
| Custom Recipe development method | `docs/en/advanced_features/custom_analysis_guide.md` |
| Release information | `https://gitcode.com/Ascend/msprof-analyze/releases` |

## 6. Submission Process Recommendations

1. After feature development is complete, perform local installation verification first.
2. Run at least one round of unit tests, and add system tests when necessary.
3. If user-visible behavior changes, update documentation and example commands accordingly.
4. If a new analysis capability is added, describe its input data requirements, output files, and applicable scenarios.
