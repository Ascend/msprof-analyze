# msprof-analyze工具安装指南

msprof-analyze的安装方式包括：**pip安装**、**whl包安装**和**编译安装**。

## pip安装

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

## whl包安装

1. whl包获取。 请通过[版本说明-发布程序包下载链接](../release_notes.md#发布程序包下载链接)下载whl包。

2. whl包校验。

   1. 根据以上下载链接下载whl包到Linux安装环境。

   2. 进入whl包所在目录，执行如下命令。

      ```bash
      sha256sum {name}.whl
      ```

      {name}为whl包名称。

      若回显呈现对应版本whl包一致的**校验码**，则表示下载了正确的性能工具whl安装包。示例如下：

      ```bash
      sha256sum msprof_analyze-1.0-py3-none-any.whl
      xx *msprof_analyze-1.0-py3-none-any.whl
      ```

3. whl包安装。

   执行如下命令进行安装。

   ```bash
   pip3 install ./msprof_analyze-{version}-py3-none-any.whl
   ```

   提示如下信息则表示安装成功。

   ```bash
   Successfully installed msprof_analyze-{version}
   ```

## 编译安装

1. 安装依赖。

   编译前需要安装wheel。

   ```bash
   pip3 install wheel
   ```

2. 下载源码。

   ```bash
   git clone https://gitcode.com/Ascend/msprof-analyze
   ```

3. 编译whl包。

   > [!NOTE] 说明
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

## 卸载和升级

若需要升级工具，请先卸载旧版本后再重新安装新版本，操作如下：

```bash
# 卸载旧版本
pip3 uninstall msprof-analyze
# 安装新版本
pip3 install ./msprof_analyze-{version}-py3-none-any.whl
```
