"""测试 MCP Adapter 连接和功能"""
import asyncio
import json
import sys
import os

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from src.tools.mcp_adaptor import MCPAdapter
# 先导入 tools 包以触发本地工具注册
import src.tools



async def test_mcp_connection():
    """测试 MCP 服务器连接"""
    print("=" * 60)
    print("🧪 MCP 连接测试")
    print("=" * 60)

    # 从环境变量读取配置
    config_str = os.getenv("MCP_SERVERS", "[]")
    try:
        servers_config = json.loads(config_str)
    except json.JSONDecodeError:
        print("❌ MCP_SERVERS 配置格式错误")
        return

    if not servers_config:
        print("⚠️  未配置 MCP_SERVERS，跳过测试")
        print("\n💡 提示：在 .env 中设置 MCP_SERVERS='[...]'")
        print("示例：")
        print('MCP_SERVERS=\'[{"name":"filesystem","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/tmp"]}]\'')
        return

    print(f"\n📋 配置的 MCP 服务器: {len(servers_config)} 个")
    for cfg in servers_config:
        print(f"   - {cfg['name']}: {cfg['command']} {' '.join(cfg['args'])}")

    # 创建 Adapter
    adapter = MCPAdapter()

    try:
        print("\n🚀 正在初始化 MCP 服务器...")
        await adapter.initialize(servers_config)
        print("✅ MCP 服务器初始化成功")

        # 列出所有工具
        print("\n📦 可用工具列表:")
        print("-" * 60)
        tools = adapter.list_all_tools()

        mcp_tools = [t for t in tools if "__" in t["function"]["name"]]
        local_tools = [t for t in tools if "__" not in t["function"]["name"]]

        print(f"\n🏠 本地工具 ({len(local_tools)}):")
        for tool in local_tools:
            print(f"   • {tool['function']['name']}: {tool['function']['description'][:50]}...")

        print(f"\n🌐 MCP 工具 ({len(mcp_tools)}):")
        for tool in mcp_tools:
            print(f"   • {tool['function']['name']}: {tool['function']['description'][:50]}...")

        # 如果有 filesystem 工具，尝试执行一个测试
        print("\n🧪 测试工具执行:")
        print("-" * 60)

        filesystem_tools = [t for t in mcp_tools if "filesystem" in t["function"]["name"]]
        if filesystem_tools:
            # 尝试读取一个文件
            test_tool = filesystem_tools[0]
            tool_name = test_tool["function"]["name"]
            print(f"\n尝试执行: {tool_name}")

            # 创建一个测试文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
                f.write("Hello from MCP test!")
                test_file = f.name

            try:
                # 假设第一个 filesystem 工具是 read_file
                if "read" in tool_name.lower():
                    result = await adapter.execute_tool(tool_name, {"path": test_file})
                    print(f"✅ 执行成功: {result}")
                else:
                    print(f"ℹ️  工具 {tool_name} 不是读取操作，跳过执行测试")
            finally:
                # 清理测试文件
                os.unlink(test_file)
        else:
            print("⚠️  未找到 filesystem 工具进行执行测试")

        print("\n" + "=" * 60)
        print("✅ MCP 测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        print("\n🧹 清理资源...")
        await adapter.close()
        print("✅ 已关闭所有 MCP 连接")


if __name__ == "__main__":
    # 加载 .env
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(env_path)

    # 运行测试
    asyncio.run(test_mcp_connection())
