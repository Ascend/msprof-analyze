# msprof-analyze Installation Guide

## 1. Installation Description

This tool supports three installation methods: [online installation](#21-online-installation), [offline installation](#22-offline-installation), and [source installation](#23-source-installation). Select the method that best suits your environment.

> [!NOTE]
>
> The tool supports Python 3.7.5 and later. Python 3.9 or later is recommended.

## 2. Installation Methods

### 2.1 Online Installation

```shell
pip install msprof-analyze
```

Use `pip install msprof-analyze==version_number` to install a specific version of the package. Use the CANN version corresponding to the tool used to collect the profile data.

If the version number is unknown, omit the version specification to install the latest package.

The `pip` command automatically installs the latest package and its required dependencies.

If the following information is displayed, the tool is installed successfully:

```bash
Successfully installed msprof-analyze-{version}
```

### 2.2 Offline Installation

1. Refer to [msprof-analyze Release](https://gitcode.com/Ascend/msprof-analyze/releases) to download the `msprof-analyze` WHL package and its corresponding digital signature file (`.sha256`).

   By downloading this software, you agree to the terms and conditions of the [Huawei Enterprise End User License Agreement (EULA)](https://e.huawei.com/en/about/eula).

2. Verify the integrity of the WHL package.

   1. Run the following command in the directory containing the WHL package to obtain its SHA-256 checksum.

      ```bash
      sha256sum {name}.whl
      ```

      The following is an example of the command output:

      ```ColdFusion
      {sha256} {name}.whl
      ```

   2. Open the digital signature file with a text editor to view the SHA-256 checksum.

   3. Compare the SHA-256 checksums of the two files.

      If the two checksums match, the correct package has been downloaded. If they do not match, do not use the package. For support and services, seek assistance on the forum or submit a technical support ticket.

3. Install the WHL package.

   Run the following command to install the package:

   ```bash
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

   If the following information is displayed, the installation is successful:

   ```ColdFusion
   Successfully installed msprof_analyze-{version}
   ```

### 2.3 Source Installation

To use the latest code features or modify the source code to enhance functions, download the repository source code, compile and package the tool, and complete the installation.

#### 2.3.1 Environment Setup

Source code compilation uniformly uses the MindStudio standard build environment.

- For daily development or use of released images, see [MindStudio Tool Development Environment Installation Guide](https://gitcode.com/Ascend/msot/blob/26.2.0/docs/en/common/dev_env_setup.md).
- When reproducing the environment from a base OS or performing source build verification or unit test verification, see [MindStudio Unified Build Image Creation Guide](https://gitcode.com/Ascend/msot/blob/26.2.0/docs/en/common/docker_image_build_guide.md), and build the environment image on site from the openEuler base image.

The subsequent source compilation and unit test commands in this document must be executed in the container of the specified image or the on-site built environment image. The CANN package version, GCC version, and Python version are defined by the unified image creation guide; this repository does not maintain them separately.

After the image is built, use the `ctr_in.py` command provided in Chapter 7 of the unified image creation guide to start and enter the container in an interactive terminal. Do not create a container using the ordinary `docker run` command, and do not use `docker exec <container_name> bash -c '<command>'` as a substitute for the interactive environment; otherwise, Python, GCC, and CANN environment initialization may be skipped.

After entering the interactive container shell opened by `ctr_in.py`, run the following command to clone this repository:

```bash
cd ~
git clone https://gitcode.com/Ascend/msprof-analyze.git -b 26.2.0
```

#### 2.3.2 Build

In the same interactive container shell opened by `ctr_in.py`, run the following command in the repository root directory to automatically download dependencies and build:

```bash
cd ~/msprof-analyze
python3 build.py
```

After a successful build, the installation package is generated in the `artifacts/` directory.

#### 2.3.3 Run Unit Tests (Optional)

This step is not required for installation. To verify basic code functionality, run unit tests:

```bash
cd ~/msprof-analyze
python3 build.py test
```

If the command returns 0 and all test cases pass, the unit tests pass.

#### 2.3.4 Installation

Run the following command to install the profiling tool:

```bash
pip3 install ./msprof_analyze-{version}-py3-none-any.whl
```

## 3. Verifying the Installation

After the installation is complete, run the following command to verify that the tool is installed successfully:

```bash
msprof-analyze --help
```

If the command runs without errors and displays the help information, the installation is successful.

If `msprof-analyze --help` indicates that the command does not exist, verify that the current terminal is using the Python environment in which `msprof-analyze` was installed.

## 4. Uninstallation

Run the following command to uninstall the `msprof-analyze` tool:

```bash
pip uninstall msprof-analyze
```

If the following information is displayed, `msprof-analyze` has been uninstalled successfully:

```ColdFusion
Successfully uninstalled msprof-analyze-{version}
```

## 5. Upgrade

The `msprof-analyze` tool does not support direct upgrades. You must first complete [uninstallation](#4-uninstallation) and then [reinstall](#2-installation-methods) it.

You can run the `msprof-analyze --version` command to view the version information in the current environment and then select the version to upgrade to. When upgrading, pay attention to version compatibility. For details, see [Release Notes](https://gitcode.com/Ascend/release-management/blob/master/MindStudio/26.2.0/release_notes_en.md).
