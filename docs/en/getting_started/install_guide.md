# MindStudio Profiler Analyze Installation Guide

## 1. Installation Description

This tool supports three installation methods: [Online Installation](#21-online-installation), [Offline Installation](#22-offline-installation), and [Installation from Source](#23-installation-from-source). Choose the method that best fits your environment.

## 2. Installation Methods

### 2.1 Online Installation

```shell
pip install msprof-analyze
```

To install a specific version, run the `pip install msprof-analyze==version_number` command. Use the CANN version number corresponding to the profiling tool used for data collection.

If the version number is unknown, omit the version specification to use the latest program package.

The `pip` command automatically installs the latest package and the required dependencies.

If the following information is displayed, the installation is successful:

```ColdFusion
Successfully installed msprof-analyze-{version}
```

### 2.2 Offline Installation

1. Download the msprof-analyze `.whl` package and the corresponding digital signature file (`.sha256`) by referring to [msprof-analyze Release](https://gitcode.com/Ascend/msprof-analyze/releases).

   Once you download this software, you agree to the terms and conditions of the [Huawei Enterprise End User License Agreement (EULA)](https://e.huawei.com/en/about/eula).

2. Verify the integrity of the `.whl` package.

   1. Run the following command in the directory where the `.whl` package is located to obtain the SHA256 verification code of the package.

      ```bash
      sha256sum {name}.whl
      ```

      The following information is displayed:

      ```ColdFusion
      {sha256} {name}.whl
      ```

   2. Open the digital signature file in Notepad to view the SHA256 checksum.

   3. Check whether the SHA256 checksums of the two files are the same.

      If they are the same, the downloaded software package is correct. If they are different, do not use the software package. For support and services, seek help in the forum or submit a technical service ticket.

3. Install the `.whl` package.

   Run the following command for installation:

   ```bash
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

   If the following information is displayed, the installation is successful:

   ```bash
   Successfully installed msprof_analyze-{version}
   ```

### 2.3 Installation from Source

1. Install dependencies.

   Before building from source, install `wheel`.

   ```bash
   pip3 install wheel
   ```

2. Download the source code.

   ```bash
   git clone https://gitcode.com/Ascend/msprof-analyze
   ```

3. Build the `.whl` package.

   > [!NOTE]
   >
   > When installing the following dependencies, use a newer software package version that meets the requirements. Monitor and patch existing vulnerabilities, especially disclosed high-risk vulnerabilities with a CVSS score greater than 7.

   ```bash
   cd msprof-analyze
   pip3 install -r requirements.txt && python3 setup.py bdist_wheel
   ```

   After the command execution is complete, the `msprof-analyze` installation package `msprof_analyze-{version}-py3-none-any.whl` is generated in the `dist` directory.

4. Install the tool.

   Run the following command to install `msprof-analyze`:

   ```bash
   cd dist
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

## 3. Uninstallation

Run the following command to uninstall msprof-analyze:

```bash
pip uninstall msprof-analyze
```

If the following information is displayed, msprof-analyze is successfully uninstalled:

```ColdFusion
Successfully uninstalled msprof-analyze-{version}
```

## 4. Upgrade

msprof-analyze does not support direct upgrades. You must [uninstall the tool](#3-uninstallation) and then [reinstall it](#2-installation-methods).

You can use the `msprof-analyze --version` command to view the version information of the current environment, and then select the version to upgrade to. When upgrading the version, you need to pay attention to the version compatibility relationship. Please refer to the [Release Notes](https://gitcode.com/Ascend/release-management/blob/master/MindStudio/26.0.0/release_notes_en.md).
