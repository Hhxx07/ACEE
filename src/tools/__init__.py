"""工具包 - 导入所有工具模块并触发注册"""
from . import file_tools
from . import network_tools
from . import system_tools

# 调用注册函数以注册工具
file_tools.register_all()
network_tools.register_all()
system_tools.register_all()
