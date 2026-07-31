# msprof-analyze 安装指南

## 1. 安装说明

本工具支持[在线安装](#21-在线安装)、[离线安装](#22-离线安装)、[源码安装](#23-源码安装)三种安装方式，请根据您的实际环境选择最合适的方案。

> [!NOTE]
>
> 工具支持 Python 3.7.5 及以上版本，建议使用 Python 3.9 及以上版本。

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

      若两个校验码一致，则表示下载了正确的软件包；若不一致，请不要使用该软件包，需要支持与服务，请在论坛求助或提交技术工单。

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

如需使用最新代码的功能，或对源码进行修改以增强功能，可下载本仓库代码，自行编译、打包工具并完成安装。

#### 2.3.1 环境准备

源码编译统一使用 MindStudio 标准构建环境。

- 日常开发或使用已发布镜像，请参考《[MindStudio工具开发环境安装指导](https://gitcode.com/Ascend/msot/blob/master/docs/zh/common/dev_env_setup.md)》。
- 需要从基础操作系统复现环境、执行源码构建验证或单元测试验证时，必须参考《[MindStudio统一构建镜像制作指南](https://gitcode.com/Ascend/msot/blob/master/docs/zh/common/docker_image_build_guide.md)》，从openEuler基础镜像现场构建环境镜像。

本文档后续的源码编译和单元测试命令，均在上述指定镜像容器或现场构建的环境镜像的容器中执行，CANN 软件包版本、GCC 版本和 Python 版本以统一镜像制作指南为准，本仓库不重复维护。

镜像构建完成后，必须使用统一镜像制作指南第 7 章给出的 `ctr_in.py` 命令，在交互式终端中启动并进入容器。不得使用普通 `docker run` 创建容器，也不得使用 `docker exec <容器名> bash -c '<命令>'` 替代交互式环境；否则可能跳过 Python、GCC 和 CANN 环境初始化。

进入 `ctr_in.py` 打开的交互式容器 Shell 后，执行如下命令克隆本仓库：

```bash
cd ~
git clone https://gitcode.com/Ascend/msprof-analyze.git
```

#### 2.3.2 执行编译

保持在 `ctr_in.py` 打开的同一个交互式容器 Shell 中，在仓库根目录执行以下命令，自动完成依赖下载与构建：

```bash
cd ~/msprof-analyze
python3 build.py
```

构建成功后，安装包将生成在 `artifacts/` 目录下。

#### 2.3.3 执行单元测试（可选）

此步骤非安装必需。如需验证代码基本功能，可执行单元测试：

```bash
cd ~/msprof-analyze
python3 build.py test
```

命令返回码为 0，且测试用例均无失败，表示单元测试通过。

#### 2.3.4 安装

执行如下命令进行性能工具安装。

```bash
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

可通过`msprof-analyze --version`命令查看当前环境的版本信息，再选择需要升级的版本。升级版本时需要关注版本配套关系，请参见《[版本说明](https://gitcode.com/Ascend/release-management/blob/master/MindStudio/26.1.0/release_notes.md)》。
