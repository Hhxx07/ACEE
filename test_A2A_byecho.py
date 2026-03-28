"""Test script for A2A Echo Agent protocol."""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.a2a.runtime import A2ARuntime


async def main():
    """Test the Echo Agent."""
    print("=" * 50)
    print("Testing A2A Echo Agent Protocol")
    print("=" * 50)
    
    # 创建 Runtime 实例（会自动注册 Echo Agent）
    runtime = A2ARuntime()
    
    # 测试消息
    test_messages = [
        "Hello A2A!",
        "Testing protocol",
        "Multi-agent architecture works!",
    ]
    
    for msg in test_messages:
        print(f"\n[TEST] Sending: '{msg}'")
        
        try:
            # 调用 test_echo 方法
            result = await runtime.test_echo(msg)
            
            print(f"[SUCCESS] Received: {result}")
            print(f"[INFO] Echo Agent successfully responded!")
            
        except AssertionError as e:
            print(f"[FAILED] Assertion error: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 50)
    print("Test completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
