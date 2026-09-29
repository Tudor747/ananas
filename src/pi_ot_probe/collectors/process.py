"""Process support for bounded, real local observations."""

from __future__ import annotations

import asyncio


async def run_command(*arguments: str, timeout: float = 15) -> str:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        # Stop the external collector before reporting a bounded timeout.
        process.kill()
        await process.communicate()
        raise RuntimeError(f"command timed out: {arguments[0]}") from None
    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or f"command failed: {arguments[0]}")
    return stdout.decode("utf-8", errors="replace")
