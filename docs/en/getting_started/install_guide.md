# MindStudio Profiler Analyze Installation Guide

You can install MindStudio Profiler Analyze (`msprof-analyze`) by using **`pip`**, installing a **WHL package**, or **building from source**.

## Installation Using `pip`

```shell
pip install msprof-analyze
```

To install a specific version, run the `pip install msprof-analyze==version_number` command. Use the CANN version number corresponding to the profiling tool used for data collection.

If the version number is unknown, omit the version specification to use the latest program package.

The `pip` command automatically installs the latest package and the required dependencies.

If the following information is displayed, the installation is successful:

```bash
Successfully installed msprof-analyze-{version}
```

## Installation Using a WHL Package

1. Obtain the WHL package. Download the WHL package from the [Release Package Download Links](../release_notes.md#release-package-download-links) section in *Release Notes*.

2. Verify the WHL package.

   Go to the directory containing the WHL package and run the following command:

   ```bash
   sha256sum {name}.whl
   ```

   *{name}* indicates the name of the WHL package.

   If the command output displays a **checksum** that matches the corresponding WHL package version, the correct `msprof-analyze` installation package has been downloaded. The following is an example:

   ```bash
   sha256sum msprof_analyze-1.0-py3-none-any.whl
   xx *msprof_analyze-1.0-py3-none-any.whl
   ```

3. Install the WHL package.

   Run the following command for installation:

   ```bash
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

   If the following information is displayed, the installation is successful:

   ```bash
   Successfully installed msprof_analyze-{version}
   ```

## Building from Source

1. Install the dependencies.

   Before building from source, install `wheel`.

   ```bash
   pip3 install wheel
   ```

2. Download the source code.

   ```bash
   git clone https://gitcode.com/Ascend/msprof-analyze
   ```

3. Build the WHL package.

   > [!NOTE]NOTE
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

## Uninstallation and Upgrade

To upgrade the tool, uninstall the earlier version before installing the new version. The procedure is as follows:

```bash
# Uninstall the earlier version
pip3 uninstall msprof-analyze
# Install the new version
pip3 install ./msprof_analyze-{version}-py3-none-any.whl
```
