# msprof-analyze Installation Guide

## 1. Installation Description

This tool supports three installation methods: [online installation](#21-online-installation), [offline installation](#22-offline-installation), and [source installation](#23-source-installation). Select the method that best suits your environment.

> [!NOTE]
>
> The tool supports Python 3.7.5 and later. Python 3.9 or later is recommended.

## 2. Installation Methods

### 2.1 Online Installation

```shell
pip install msprof-analyze==26.1.0
```

Use `pip install msprof-analyze==version_number` to install a specific version of the package. Use the CANN version corresponding to the tool used to collect the profile data.

If the version number is unknown, omit the version specification to install the latest package.

The `pip` command automatically installs the latest package and its required dependencies.

If the following information is displayed, the tool is installed successfully:

```bash
Successfully installed msprof-analyze-26.1.0
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

1. Install the dependencies.

   Install `wheel` before building from source.

   ```bash
   pip3 install wheel
   ```

2. Download the source code.

   ```bash
   git clone https://gitcode.com/Ascend/msprof-analyze -b master
   ```

3. Build the WHL package.

   > [!NOTE]
   >
   > When installing the following dependencies, use newer software package versions that meet the requirements. Monitor and patch existing vulnerabilities, especially disclosed high-risk vulnerabilities with a CVSS score greater than 7.

   ```bash
   cd msprof-analyze
   pip3 install -r requirements.txt && python3 setup.py bdist_wheel
   ```

   After the command is executed, the profiling tool WHL package `msprof_analyze-{version}-py3-none-any.whl` is generated in the `dist` directory.

4. Install the tool.

   Run the following command to install the profiling tool:

   ```bash
   cd dist
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

Run the following command to uninstall `msprof-analyze`:

```bash
pip uninstall msprof-analyze
```

If the following information is displayed, `msprof-analyze` has been uninstalled successfully:

```ColdFusion
Successfully uninstalled msprof-analyze-{version}
```

## 5. Upgrade

The `msprof-analyze` tool does not support direct upgrades. You must first [uninstall](#4-uninstallation) the tool and then [reinstall](#2-installation-methods) it.

You can run the `msprof-analyze --version` command to view the version information in the current environment and then select the version to upgrade to. When upgrading the version, pay attention to the version compatibility requirements. For details, see the [Release Notes](https://gitcode.com/Ascend/release-management/blob/master/MindStudio/master/release_notes_en.md).
