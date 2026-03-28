from .models import AgentCard, A2ARequest, A2AResponse, TaskState


class EchoA2AAgent:
    card = AgentCard(
        name="echo",  # ← 这个 name 很重要，runtime 会用它来查找 agent
        description="Echoes back the received message for testing A2A protocol.",
        capabilities=["echo_message"],
    )

    async def handle(self, request: A2ARequest) -> A2AResponse:
        """Echo back the received message in standard A2A response format."""
        
        # 检查 action 是否支持
        if request.action != "echo_message":
            return A2AResponse(
                request_id=request.request_id,
                task_id=request.task_id,
                from_agent=self.card.name,
                state=TaskState.FAILED,
                error={
                    "code": "unsupported_action",
                    "message": f"Action '{request.action}' is not supported by agent 'echo'.",
                    "retriable": False,
                },
                state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.FAILED],
            )
        
        # 获取原始消息
        original_message = request.payload.get("message", "")
        
        # 构造 Echo 响应
        echo_result = f"Echo: {original_message}"
        
        # 返回标准 A2A 响应
        return A2AResponse(
            request_id=request.request_id,
            task_id=request.task_id,
            from_agent=self.card.name,
            state=TaskState.COMPLETED,
            artifacts={"echo_result": echo_result},  # 将结果放在 artifacts 中
            state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.COMPLETED],
        )
