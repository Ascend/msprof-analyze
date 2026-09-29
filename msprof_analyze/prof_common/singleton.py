# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2024 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------
import os
import inspect
from functools import wraps


def get_class_absolute_path(cls):
    module = inspect.getmodule(cls)
    if module is not None:
        module_path = module.__name__
        class_name = cls.__name__
        return f"{module_path}.{class_name}"
    else:
        return None


def is_static_func(function_obj):
    return isinstance(function_obj, staticmethod)


def singleton(cls):
    """
    :param cls: any class
    :return: singleton handle

    When using the singleton function, you need to manually specify collection_path='dataSet_path'. Otherwise, the
    singleton function is initialized by class name.
    if cls has 'collection_path' property, _instance map will build by class_name and 'collection_path', the
    default value of collection path is class absolute path.

    _instance = {cls.name: {collection_path: instance}}
    """
    _instance = {}

    @wraps(cls)  # 使用 wraps 装饰器
    def _singleton(*args, **kw):
        # 适配多进程异步调用场景，确保不同子进程的单例类互相隔离
        pid = os.getpid()
        if pid not in _instance:
            _instance[pid] = {}

        collection_path = kw.get("collection_path")
        if not collection_path:
            collection_path = get_class_absolute_path(cls)
        if cls in _instance[pid] and collection_path in _instance[pid][cls]:
            return _instance[pid][cls].get(collection_path)
        if cls not in _instance[pid]:
            _instance[pid][cls] = {collection_path: cls(*args, **kw)}
        else:
            _instance[pid][cls][collection_path] = cls(*args, **kw)
        return _instance[pid][cls].get(collection_path)

    def reset_all_instances():
        """
        用于ut使用，清空单例类，防止ut不同测试用例间相互干扰
        """
        _instance.clear()

    # 保留原始类的属性和方法
    _singleton.__name__ = cls.__name__
    _singleton.__module__ = cls.__module__
    _singleton.__doc__ = cls.__doc__

    # 拷贝原始类的类方法和静态方法
    _singleton.__dict__.update(cls.__dict__)
    for base_class in inspect.getmro(cls)[::-1]:
        # 获取类的所有成员
        members = inspect.getmembers(base_class)

        # 过滤出函数对象
        function_objs = [
            member[1] for member in members if inspect.isfunction(member[1]) or inspect.ismethod(member[1])
        ]
        for function_obj in function_objs:
            if inspect.isfunction(function_obj) and not is_static_func(function_obj):
                continue
            setattr(_singleton, function_obj.__name__, function_obj)

    _singleton.reset_all_instances = reset_all_instances
    singleton.reset_all_instances = reset_all_instances

    return _singleton
