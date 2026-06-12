# msprof-analyze工具安装指南

## 1. 安装说明

本工具支持[在线安装](#21-在线安装)、[离线安装](#22-离线安装)、[源码安装](#23-源码安装)三种安装方式，请根据您的实际环境选择最合适的方案。

## 2. 安装方式

### 2.1 在线安装

```shell
pip install msprof-analyze
```

使用`pip install msprof-analyze==版本号`可安装指定版本的包，使用采集性能数据对应的CANN版本号即可。

如不清楚版本号可不指定，使用最新程序包。

**pip**命令会自动安装最新的包及其配套依赖。

提示如下信息则表示安装成功。

```bash
Successfully installed msprof-analyze-{version}
```

### 2.2 离线安装

1. 请参考[msprof-analyze Release](https://gitcode.com/Ascend/msprof-analyze/releases)下载msprof-analyze的whl软件包和对应数字签名文件（.sha256）。

   下载本软件即表示您同意《[华为企业业务最终用户许可协议（EULA）](https://e.huawei.com/cn/about/eula)》的条款和条件。

2. 验证whl包的完整性。

   1. 在whl包所在目录执行如下命令获取whl软件包的sha256校验码。

      ```bash
      sha256sum {name}.whl
      ```

      打印如下示例信息。

      ```ColdFusion
      {sha256} {name}.whl
      ```

   2. 用记事本打开数字签名文件查看sha256校验码。

   3. 比对两个文件的sha256校验码是否一致。

      若两个校验码一致，则表示下载了正确的软件包；若不一致，请不要使用该软件包，需要支持与服务请在论坛求助或提交技术工单。

3. whl包安装。

   执行如下命令进行安装。

   ```bash
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

   提示如下信息则表示安装成功。

   ```ColdFusion
   Successfully installed msprof_analyze-{version}
   ```

### 2.3 源码安装

1. 安装依赖。

   源码编译前需要安装wheel。

   ```bash
   pip3 install wheel
   ```

2. 下载源码。

   ```bash
   git clone https://gitcode.com/Ascend/msprof-analyze
   ```

3. 编译whl包。

   > [!NOTE]
   >
   > 在安装如下依赖时，请注意使用满足条件的较新版本软件包，关注并修补存在的漏洞，尤其是已公开的CVSS打分大于7分的高危漏洞。

   ```bash
   cd msprof-analyze
   pip3 install -r requirements.txt && python3 setup.py bdist_wheel
   ```

   以上命令执行完成后在dist目录下生成性能工具whl安装包`msprof_analyze-{version}-py3-none-any.whl`。

4. 安装。

   执行如下命令进行性能工具安装。

   ```bash
   cd dist
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

## 3. 验证安装

安装完成后，执行以下命令验证工具是否安装成功：

```bash
msprof-analyze --help
```

若输出不报错，且能显示帮助信息，则表明安装成功。

若 `msprof-analyze --help` 提示命令不存在，请确认当前终端使用的是安装 `msprof-analyze` 的 Python 环境。

## 4. 卸载

执行如下命令卸载msprof-analyze工具。

```bash
pip uninstall msprof-analyze
```

打印如下信息时，表示msprof-analyze卸载成功。

```ColdFusion
Successfully uninstalled msprof-analyze-{version}
```

## 5. 升级

msprof-analyze工具不支持直接升级，需要先完成[卸载](#4-卸载)后再重新[安装](#2-安装方式)。

可通过`msprof-analyze --version`命令查看当前环境的版本信息，再选择需要升级的版本。升级版本时需要关注版本配套关系，请参见《[版本说明](https://gitcode.com/Ascend/release-management/blob/master/MindStudio/26.0.0/release_notes.md)》。
