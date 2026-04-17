# MindStudio Profiler Analyze Security Statement

## System Security Hardening

Enable **address space layout randomization** (ASLR) (level 2) in the system. Run the following command to enable it:

    echo 2 > /proc/sys/kernel/randomize_va_space

## User Account Recommendations

 1. Adhere to the principle of least privilege (for example, prohibit write access for `others` and avoid setting file permissions to `666` or `777`).

 2. Before installing or using the tools, ensure the user's `umask` is set to `0027` or a more restrictive value. Otherwise, issues may occur, such as source code compilation failures, configuration file read failures, or excessive permissions for generated directories and files.

 3. All tools in this repository are designed to run with minimal permissions. For security reasons, do not use `root` or other privileged accounts. Always install and execute tools as a regular user.

## File Permission Control

 1. When providing input files to the tool, it is recommended that the file owner matches the process owner of the tool and that file permissions restrict write access for `group` and `others`. By default, tool files written to the drive are not writable by others. You can manually control the permissions for the generated files as needed.

 2. Maintain strict permission control during installation and use. For details about the recommended file permission settings, see the following table.

**File Permission Reference**

| Type                              | Maximum Linux Permission|
| ---------------------------------- | ------------------- |
| Home directory                        | 750 (rwxr-x---)   |
| Program files (including scripts and library files)    | 550 (r-xr-x---)   |
| Program file directory                      | 550 (r-xr-x---)   |
| Configuration files                          | 640 (rw-r-----)   |
| Configuration file directory                      | 750 (rwxr-x---)   |
| Log files (recorded or archived)    | 440 (r--r-----)   |
| Log files (being recorded)                | 640 (rw-r-----)   |
| Log file directory                      | 750 (rwxr-x---)   |
| Debug files                         | 640 (rw-r-----)   |
| Debug file directory                     | 750 (rwxr-x---)   |
| Temporary file directory                      | 750 (rwxr-x---)   |
| Maintenance and upgrade file directory                  | 770 (rwxrwx---)   |
| Service data files                      | 640 (rw-r-----)   |
| Service data file directory                  | 750 (rwxr-x---)   |
| Key components, private keys, certificates, and ciphertext file directory| 700 (rwx------)   |
| Key components, private keys, certificates, and ciphertext files    | 600 (rw-------)   |
| APIs and scripts for encryption and decryption            | 500 (r-x------)   |

## Build Security Statement

`msprof-analyze` supports building from source. Temporary files and build directories are generated during the process. To reduce security risks, you can perform permission control on files within the source code directory. During the build process, you can modify build scripts as needed to avoid security risks and ensure the security of the build results.

## Execution Security Statement

1. During data analysis, if the data size exceeds the memory capacity, an error may occur and the process may exit unexpectedly.

2. If an exception occurs during operation, the tool will exit the process and print error messages. This is expected behavior. You are advised to locate the specific cause of the error based on the error prompts, such as by viewing log files or result files generated during the collection and parsing process.

## Public Network Address Statement

| Software Type| Software  | Path | Type | URL | Description |
| -------- | -------------------------------------------------- | ------------------------------------------------------------ | -------- | ------------------------------------------------------------ | ------------------------------------------ |
| Open-source software| msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | Public Network Address| <https://www.hiascend.com/document/detail/zh/canncommercial/80RC2/devaids/auxiliarydevtool/atlasprofiling_16_0038.html> | MindStudio Ascend PyTorch Profiler examples|
| Open-source software| msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | Public Network Address| <https://gitcode.com/Ascend/msprof-analyze/blob/master/docs/zh/fused_operator_api_replacement_example.md> | advisor optimization suggestion examples                   |
| Open-source software| msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | Public Network Address| <https://www.hiascend.com/document/detail/zh/canncommercial/80RC2/devaids/auxiliarydevtool/aoe_16_043.html> | advisor optimization suggestion examples                   |
| Open-source software| msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | Public Network Address| <https://www.mindspore.cn/lite/docs/zh-CN/r2.7.0/mindir/converter_tool_ascend.html#aoe%E8%87%AA%E5%8A%A8%E8%B0%83%E4%BC%98> | advisor optimization suggestion examples                   |
| Open-source software| msprof-analyze advisor | /msprof_analyze/advisor/config/config.ini           | Public Network Address| <https://www.hiascend.com/document/detail/zh/canncommercial/700/modeldevpt/ptmigr/AImpug_000060.html> | advisor optimization suggestion examples                   |
| Open-source software| msprof-analyze         | /config/config.ini                   | Public Network Address| <https://gitcode.com/Ascend/msprof-analyze> | URL of the `msprof-analyze` repository                    |
| Open-source software| msprof-analyze         | /LICENSE                             | Public Network Address| <http://www.apache.org/licenses/LICENSE-2.0>                   | URL of the open-source software protocol                          |
| Open-source software| msprof-analyze advisor | /msprof_analyze/advisor/rules/aicpu_rules.yaml      | Public Network Address| <https://gitcode.com/Ascend/msprof-analyze/blob/master/docs/zh/aicpu_operator_replacement_example.md> | AICPU operator replacement examples                       |
| Open-source software| msprof-analyze advisor | /msprof_analyze/advisor/rules/environment_variable_info.yaml | Public Network Address| <https://www.hiascend.com/document/detail/zh/canncommercial/850/maintenref/envvar/envref_07_0001.html> | Networking guide                                  |
| Open-source software| msprof-analyze         | /config/config.ini                   | Public Network Address| <pmail_mindstudio@huawei.com>                                  | Public email address                                  |

## Public API Statement

This project is developed in Python. You are advised to use the public APIs specified in the documentation and avoid directly calling the source code of APIs that are not explicitly documented.

## Disclaimer

- This tool is intended solely for debugging and development. Users are responsible for any risks and should carefully review the following information:

  - [X] Data processing and deletion: Users are responsible for managing and deleting any data generated while using this tool. Users are advised to delete such data promptly after use to prevent information leakage.
  - [X] Data confidentiality and transmission: Users understand and agree not to share or transmit any data generated by this tool. Neither the tool nor its developers are responsible for any information leaks, data breaches, or other negative consequences.
  - [X] User input security: Users are responsible for the security of any commands they enter and for any risks or losses resulting from improper input. The tool and its developers are not liable for issues caused by incorrect command usage.
- Disclaimer scope: This disclaimer applies to all individuals and entities using this tool. By using the tool, you acknowledge and accept this statement and assume all risks and responsibilities arising from its use. If you do not agree, please stop using the tool immediately.
- Before using this tool, **please read and understand the preceding disclaimer**. If you have any questions, contact the developer.
