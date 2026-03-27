"""Task 1.2: Async subprocess management with streaming output."""

import asyncio
import os
from typing import Callable, Awaitable


async def run_command(
    command: str,
    on_output: Callable[[str], Awaitable[None]],
    on_done: Callable[[int], Awaitable[None]] | None = None,
    cwd: str | None = None,
) -> int:
    """Execute a shell command asynchronously, streaming stdout/stderr to on_output.

    Returns the exit code.
    """
    cwd = cwd or os.getcwd()
    try:
        # Use shell=True so pipes, redirections etc. work
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
            text = line.decode("utf-8", errors="replace")
            await on_output(prefix + text)

    # Read stdout and stderr concurrently
    await asyncio.gather(
        _read_stream(proc.stdout),
        _read_stream(proc.stderr, prefix=""),
    )

    exit_code = await proc.wait()
    if on_done:
        await on_done(exit_code)
    return exit_code
