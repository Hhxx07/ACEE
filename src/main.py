"""Entry point for the Multi-Agent CLI system."""

import json
import os
import atexit
from dotenv import load_dotenv

from .tools.mcp_adaptor import MCPAdapter

# Global MCP adapter instance
mcp_adapter = MCPAdapter()

# Load .env from project root
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path)


def main():
    """Entry point - runs TUI with MCP initialization."""
    from .tui import AgentCLI
    
    # Parse MCP config
    servers_config = _parse_mcp_config()
    
    # Register cleanup on exit
    atexit.register(_cleanup_mcp) #注册程序退出时自动执行的清理函数
    
    # Set MCP adapter for tool_agent
    from .tool_agent import set_mcp_adapter
    set_mcp_adapter(mcp_adapter)
    
    # Create TUI app
    app = AgentCLI()
    
    # Inject MCP initialization into on_mount
    if servers_config:
        _inject_mcp_init(app, servers_config)
    
    # Run TUI app (保持原样)
    app.run()


def _parse_mcp_config() -> list[dict] | None: 
    """Parse MCP servers config from env."""
    config_str = os.getenv("MCP_SERVERS", "[]") # 这里返回的是一个字典（json转字典）
    if not config_str or config_str.strip() == "[]":
        return None
    
    try:
        config = json.loads(config_str)
        if isinstance(config, list) and config:
            return config
    except json.JSONDecodeError:
        print("⚠️  Failed to parse MCP_SERVERS config")
    return None


def _inject_mcp_init(app, servers_config: list[dict]):
    """Inject async MCP initialization into app.on_mount."""
    original_on_mount = app.on_mount
    
    async def patched_on_mount():
        # Initialize MCP servers async
        try:
            await mcp_adapter.initialize(servers_config)
            print(f"✅ Initialized {len(servers_config)} MCP server(s)")
        except Exception as e:
            print(f"⚠️  MCP initialization failed: {e}")
        
        # Call original on_mount
        await original_on_mount()
    
    app.on_mount = patched_on_mount


def _cleanup_mcp():
    """Cleanup MCP servers on exit."""
    try:
        # Import here to avoid circular dependency
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(mcp_adapter.close())
            else:
                loop.run_until_complete(mcp_adapter.close())
        except RuntimeError:
            asyncio.run(mcp_adapter.close())
    except Exception:
        pass


if __name__ == "__main__":
    main()

