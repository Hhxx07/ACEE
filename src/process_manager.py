"""Task 1.2: Async subprocess management with streaming output."""

import asyncio
import os
import locale
from typing import Callable, Awaitable

#为了正常显示中文，首先读取系统的编码方式
SYSTEM_ENCODING = locale.getpreferredencoding()


async def run_command(
    command: str,
    on_output: Callable[[str], Awaitable[None]],
    on_done: Callable[[int], Awaitable[None]] | None = None,
    cwd: str | None = None,
) -> int:
    """Execute a shell command asynchronously, streaming stdout/stderr to on_output.

    Returns the exit code.
    """
    #onoutput是一个异步回调函数，就是可以把心的输出直接接到这里处理
    cwd = cwd or os.getcwd()
    try:
        # Use shell=True so pipes, redirections etc. work
        #创建操作环境shell子进程
        #把输入和输出用两个虚拟管道接受
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except Exception as e:
        await on_output(f"[Process Error] Failed to start: {e}\n")
        if on_done:
            await on_done(-1)
        return -1

    async def _read_stream(stream, prefix=""):
        while True:
            line = await stream.readline()
            if not line:
                break
            #为了可以正常显示汉字字符，这里不能用utf-8解码格式
            #如果没有办法读取的字符用占位符替代掉

            #先读取更严苛的英文编码，然后在报错的时候尝试中文编码。

            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError:
                text = line.decode(SYSTEM_ENCODING, errors="replace")

            await on_output(prefix + text)

    #同时读取正常输出和错误输出连个出口的东西，不会卡死
    await asyncio.gather(
        _read_stream(proc.stdout, prefix="[OUT]"),
        _read_stream(proc.stderr, prefix="[ERR]"),
    )

    exit_code = await proc.wait()
    if on_done:
        await on_done(exit_code)
    return exit_code

#管道处理 信息读取 异步显示
