import asyncio
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional
from dataclasses import dataclass

@dataclass
class MCPServerConfig:
    """MCP server 配置"""
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None

class MCPClient:
    """基于 stdio 的 MCP client 实现"""
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
    
    async def start(self):
        """启动 MCP server 子进程"""
        self.process = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.config.env or os.environ.copy()
        )
        # 启动监听任务
        asyncio.create_task(self._read_messages())
    
    async def _send_jsonrpc(self, method: str, params: Any = None) -> Dict:
        """发送 JSON-RPC 请求并等待响应"""
        request_id = self._request_id
        self._request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        message = json.dumps(request) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()
        
        future = asyncio.Future()
        self._pending_requests[request_id] = future
        return await future
    
    async def _read_messages(self):
        """持续读取 MCP server 的响应"""
        while self.process and self.process.returncode is None:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                response = json.loads(line.decode())
                
                if "id" in response and response["id"] in self._pending_requests:
                    future = self._pending_requests.pop(response["id"])
                    if "error" in response:
                        future.set_exception(Exception(response["error"]))
                    else:
                        future.set_result(response)
            except Exception as e:
                print(f"MCP read error: {e}")
    
    async def list_tools(self) -> List[Dict]:
        """获取 MCP server 提供的工具列表"""
        response = await self._send_jsonrpc("tools/list")
        return response.get("result", {}).get("tools", [])
    
    async def call_tool(self, tool_name: str, arguments: Dict) -> Any:
        """调用 MCP server 的工具"""
        response = await self._send_jsonrpc("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        return response.get("result", {})
    
    async def close(self):
        """关闭 MCP server"""
        if self.process:
            self.process.terminate()
            await self.process.wait()
