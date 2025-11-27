# msprof-analyze安全声明

## 系统安全加固

建议用户在系统中配置开启ASLR（级别2 ），又称**全随机地址空间布局随机化**，可参考以下方式进行配置：

    echo 2 > /proc/sys/kernel/randomize_va_space

## 运行用户建议

 1. 用户须自行保证使用最小权限原则（如禁止other用户可写，常见如禁止666、777）。

 2. 安装或使用工具前请确保执行用户的umask值大于等于0027，否则会导致源码编译失败、读取配置文件失败、生成的目录和文件权限过大等问题。

 3. 本代码仓中的工具均设计为低权限安装使用，出于安全性及权限最小化角度考虑，所有工具均不应使用root等高权限账户使用，建议使用普通用户权限安装执行。

## 文件权限控制

 1. 用户向工具提供输入文件输入时，建议提供的文件属主与工具进程属主一致，且文件权限他人不可修改（包括group、others）。工具落盘文件权限默认他人不可写，用户可根据需要自行对生成后的相关文件进行权限控制。

 2. 用户安装和使用过程需要做好权限控制，建议参考文件权限参考进行设置。


### 文件权限参考

| 类型                               | Linux权限参考最大值 |
| ---------------------------------- | ------------------- |
| 用户主目录                         | 750（rwxr-x---）    |
| 程序文件(含脚本文件、库文件等)     | 550（r-xr-x---）    |
| 程序文件目录                       | 550（r-xr-x---）    |
| 配置文件                           | 640（rw-r-----）    |
| 配置文件目录                       | 750（rwxr-x---）    |
| 日志文件(记录完毕或者已经归档)     | 440（r--r-----）    |
| 日志文件(正在记录)                 | 640（rw-r-----）    |
| 日志文件目录                       | 750（rwxr-x---）    |
| Debug文件                          | 640（rw-r-----）    |
| Debug文件目录                      | 750（rwxr-x---）    |
| 临时文件目录                       | 750（rwxr-x---）    |
| 维护升级文件目录                   | 770（rwxrwx---）    |
| 业务数据文件                       | 640（rw-r-----）    |
| 业务数据文件目录                   | 750（rwxr-x---）    |
| 密钥组件、私钥、证书、密文文件目录 | 700（rwx------）    |
| 密钥组件、私钥、证书、加密密文     | 600（rw-------）    |
| 加解密接口、加解密脚本             | 500（r-x------）    |

## 构建安全声明

​msprof-analyze支持源码编译安装，在编译过程中会产生临时程序文件和编译目录。用户可根据需要自行对源代码目录内的文件进行权限管控降低安全风险，用户在构建过程中可根据需要修改构建脚本以避免相关安全风险，并注意构建结果的安全。

## 运行安全声明

1. 工具分析数据时，如数据内存大小超出内存容量限制，可能引发错误并导致进程意外退出。

2. 工具在运行异常时会退出进程并打印报错信息，属于正常现象。建议用户根据报错提示定位具体错误原因，包括查看打屏日志，采集解析过程中生成的结果文件等方式。


## 公网地址声明

| 软件类型 | 软件名                                             | 路径                                                         | 类型     | 内容                                                         | 用途说明                                   |
| -------- | -------------------------------------------------- | ------------------------------------------------------------ | -------- | ------------------------------------------------------------ | ------------------------------------------ |
| 开源软件 | msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | 公网地址 | https://www.hiascend.com/document/detail/zh/canncommercial/80RC2/devaids/auxiliarydevtool/atlasprofiling_16_0038.html | MindStudio Ascend PyTorch Profiler参考示例 |
| 开源软件 | msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | 公网地址 | https://gitcode.com/Ascend/msprof-analyze/blob/master/docs/zh/fused_operator_api_replacement_example.md | Advisor优化手段参考示例                    |
| 开源软件 | msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | 公网地址 | https://www.hiascend.com/document/detail/zh/canncommercial/80RC2/devaids/auxiliarydevtool/aoe_16_043.html | Advisor优化手段参考示例                    |
| 开源软件 | msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | 公网地址 | https://www.mindspore.cn/lite/docs/en/master/use/cloud_infer/converter_tool_ascend.html#aoe-auto-tuning | Advisor优化手段参考示例                    |
| 开源软件 | msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | 公网地址 | https://www.hiascend.com/document/detail/zh/canncommercial/700/modeldevpt/ptmigr/AImpug_000060.html | Advisor优化手段参考示例                    |
| 开源软件 | msprof-analyze         | /config/config.ini                   | 公网地址 | https://gitcode.com/Ascend/msprof-analyze | msprof-analyze工具地址                     |
| 开源软件 | msprof-analyze         | /LICENSE                             | 公网地址 | http://www.apache.org/licenses/LICENSE-2.0                   | 开源软件协议地址                           |
| 开源软件 | msprof-analyze advisor | /msprof_analyze/advisor/rules/aicpu_rules.yaml      | 公网地址 | https://gitcode.com/Ascend/msprof-analyze/blob/master/docs/zh/aicpu_operator_replacement_example.md | AI CPU 算子替换样例                        |
| 开源软件 | msprof-analyze advisor | /msprof_analyze/advisor/rules/environment_variable_info.yaml | 公网地址 | https://support.huawei.com/enterprise/zh/doc/EDOC1100371278/5eeeed85?idPath=23710424 | 组网指南                                   |
| 开源软件 | msprof-analyze         | /config/config.ini                   | 公网地址 | pmail_mindstudio@huawei.com                                  | 公网邮箱                                   |

## 公开接口声明

本项目采用Python开发，建议直接使用资料说明的公开接口，不建议直接调用未明确公开的接口源码。

## 免责声明

- 本工具仅供调试和开发之用，使用者需自行承担使用风险，并理解以下内容：

  - [X] 数据处理及删除：用户在使用本工具过程中产生的数据属于用户责任范畴。建议用户在使用完毕后及时删除相关数据，以防泄露或不必要的信息泄露。
  - [X] 数据保密与传播：使用者了解并同意不得将通过本工具产生的数据随意外发或传播。对于由此产生的信息泄露、数据泄露或其他不良后果，本工具及其开发者概不负责。
  - [X] 用户输入安全性：用户需自行保证输入的命令行的安全性，并承担因输入不当而导致的任何安全风险或损失。对于由于输入命令行不当所导致的问题，本工具及其开发者概不负责。
- 免责声明范围：本免责声明适用于所有使用本工具的个人或实体。使用本工具即表示您同意并接受本声明的内容，并愿意承担因使用该功能而产生的风险和责任，如有异议请停止使用本工具。
- 在使用本工具之前，请**谨慎阅读并理解以上免责声明的内容**。对于使用本工具所产生的任何问题或疑问，请及时联系开发者。
