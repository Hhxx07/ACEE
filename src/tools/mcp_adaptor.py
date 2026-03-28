"""MCP Adapter - 将 MCP tools 转换为 OpenAI Function Calling 格式"""
import asyncio
import json
import subprocess
from typing import List, Dict, Any, Optional

# 导入工具模块以触发注册
from . import file_tools
from . import network_tools
from . import system_tools

class MCPAdapter:
    """管理 MCP servers 连接和工具转换"""
    
    def __init__(self):
        self._clients: Dict[str, subprocess.Popen] = {}
        self._tools_cache: Dict[str, List[Dict]] = {}
    
    async def initialize(self, servers_config: List[Dict[str, Any]]):
        """初始化 MCP servers"""
        import platform
        is_windows = platform.system() == "Windows"

        for config in servers_config:
            cmd = [config['command']] + config['args']

            if is_windows:
                # Windows 下使用 shell=True 来支持 npx 命令
                client = subprocess.Popen(
                    ' '.join(cmd),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    shell=True
                )
            else:
                client = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8'
                )

            self._clients[config['name']] = client
            # 获取工具列表（通过 initialize 请求）
            self._tools_cache[config['name']] = await self._fetch_tools(client)
    
    async def _fetch_tools(self, client: subprocess.Popen) -> List[Dict]:
        """从 MCP server 获取工具列表"""
        # 发送 JSON-RPC initialize 请求
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "acee", "version": "1.0.0"}
            }
        }

        client.stdin.write(json.dumps(request) + "\n")
        client.stdin.flush()

        # 读取响应（跳过非 JSON 行）
        response = None
        while True:
            line = client.stdout.readline()
            if not line:
                raise Exception("MCP server closed connection")
            line = line.strip()
            if line:
                try:
                    response = json.loads(line)
                    break
                except json.JSONDecodeError:
                    # 跳过非 JSON 行（日志等）
                    continue

        # 发送 initialized 通知
        initialized = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        client.stdin.write(json.dumps(initialized) + "\n")
        client.stdin.flush()

        # 获取工具列表
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        client.stdin.write(json.dumps(tools_request) + "\n")
        client.stdin.flush()

        tools_response = None
        while True:
            line = client.stdout.readline()
            if not line:
                raise Exception("MCP server closed connection")
            line = line.strip()
            if line:
                try:
                    tools_response = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        return tools_response.get('result', {}).get('tools', [])
    
    def list_all_tools(self) -> List[Dict]:
        """合并本地工具和 MCP 工具，返回 OpenAI Function Calling 格式"""
        from .registry import _TOOLS
        
        all_tools = []
        
        # 本地工具
        for name, tool in _TOOLS.items():
            all_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {})
                }
            })
        
        # MCP 工具
        for server_name, tools in self._tools_cache.items():
            for mcp_tool in tools:
                all_tools.append({
                    "type": "function",
                    "function": {
                        "name": f"{server_name}__{mcp_tool['name']}",
                        "description": mcp_tool.get('description', ''),
                        "parameters": mcp_tool.get('inputSchema', {})
                    }
                })
        
        return all_tools
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具（本地或 MCP）"""
        # 判断是否为 MCP 工具
        if "__" in tool_name:
            server_name, mcp_tool_name = tool_name.split("__", 1)
            if server_name in self._clients:
                return await self._execute_mcp_tool(
                    self._clients[server_name], 
                    mcp_tool_name, 
                    arguments
                )
        
        # 本地工具
        from .registry import execute_tool as execute_local_tool
        return await execute_local_tool(tool_name, arguments)
    
    async def _execute_mcp_tool(self, client: subprocess.Popen, tool_name: str, arguments: Dict):
        """执行 MCP 工具"""
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        client.stdin.write(json.dumps(request) + "\n")
        client.stdin.flush()
        
        response_line = client.stdout.readline()
        response = json.loads(response_line)
        
        if "error" in response:
            raise Exception(f"MCP Error: {response['error']}")
        
        return response.get('result', {})
    
    async def close(self):
        """关闭所有 MCP servers"""
        for client in self._clients.values():
            client.terminate()
            client.wait()
        self._clients.clear()
        self._tools_cache.clear()
