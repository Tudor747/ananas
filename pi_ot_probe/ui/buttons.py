"""Button abstraction supporting real GPIO and deterministic tests later."""

from __future__ import annotations

import asyncio
from enum import Enum


class Button(str, Enum):
    UP = "up"
    DOWN = "down"
    OK = "ok"
    BACK = "back"
    ACTION = "action"


class MockButtons:
    def __init__(self) -> None:
        self._events: asyncio.Queue[Button] = asyncio.Queue()

    async def next(self) -> Button:
        return await self._events.get()

    def press(self, button: Button) -> None:
        self._events.put_nowait(button)

