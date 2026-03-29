"""Task 4.4: Tool Agent — uses LLM function calling to select and execute MCP tools."""

import json
from . import llm_client
from .tools.registry import list_tools, execute_tool, get_tool_permission

TOOL_SYSTEM_PROMPT = """You are the Tool Agent. You have access to a set of tools and must use them to fulfill the user's request.

Choose the most appropriate tool(s) and call them. If no tool is suitable, respond directly.
If a task requires multiple steps, you may call tools sequentially.

Always explain what you are doing and show the results clearly."""

MAX_ITERATIONS = 5


async def handle_task(task_description: str, user_input: str, on_output=None) -> str:
    """Handle a task using function calling with available tools.

    Implements a ReAct loop: LLM picks a tool → execute → observe → repeat.
    """
    tools = list_tools()
    if not tools:
        return "[Tool Agent] No tools available."

    messages = [
        {"role": "system", "content": TOOL_SYSTEM_PROMPT},
        {"role": "user", "content": f"User request: {user_input}\n\nTask: {task_description}"},
    ]

    all_output = []

    for _ in range(MAX_ITERATIONS):
        result = await llm_client.chat_function_call(
            messages,
            tools,
            caller="tool_agent",
        )

        if result.get("error"):
            all_output.append(
                f"[Tool Agent Error] {result.get('error')} Please try again with clearer input."
            )
            break

        # If LLM wants to call tools
        if result.get("tool_calls"):
            normalized_tool_calls = []
            for tc in result["tool_calls"]:
                if isinstance(tc, dict):
                    tc = tc.copy()
                    tc["type"] = tc.get("type") or "function"
                normalized_tool_calls.append(tc)

            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": result.get("content") or "",
                "tool_calls": normalized_tool_calls,
            })

            for tc in normalized_tool_calls:
                func_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                # Check permission
                perm = get_tool_permission(func_name)
                if perm == "DENY":
                    tool_result = f"[Permission Denied] Tool '{func_name}' is blocked."
                    if on_output:
                        await on_output(f"🚫 Tool '{func_name}' denied by permission policy.\n")
                elif perm == "ASK":
                    if on_output:
                        await on_output(f"⚠️  Tool '{func_name}' requires confirmation. Auto-allowing for now.\n")
                    tool_result = await execute_tool(func_name, args)
                else:
                    tool_result = await execute_tool(func_name, args)

                tool_result_str = str(tool_result)
                if on_output:
                    await on_output(f"🔧 [{func_name}] {tool_result_str[:200]}\n")
                all_output.append(f"[{func_name}] {tool_result_str}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result_str,
                })
        else:
            # LLM gave a direct response, we're done
            final = result.get("content", "")
            if final:
                all_output.append(final)
            break

    if not all_output:
        return "[Tool Agent] No response generated."
    return "\n".join(all_output)

