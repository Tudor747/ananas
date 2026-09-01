"""Hardware-independent 16x2 LCD interface and terminal implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
import sys
from typing import TextIO


class LCD(ABC):
    columns: int = 16
    rows: int = 2

    @abstractmethod
    def display(self, line1: str, line2: str = "") -> str:
        """Display two lines and return the rendered frame."""
        raise NotImplementedError


class MockLCD(LCD):
    """Terminal LCD used on development machines and in simulation."""

    def __init__(self, output: TextIO | None = None) -> None:
        self.output = output or sys.stdout
        self.last_frame = ""

    def _fit(self, value: str) -> str:
        return value[: self.columns].ljust(self.columns)

    def display(self, line1: str, line2: str = "") -> str:
        border = "+" + ("-" * self.columns) + "+"
        frame = "\n".join((border, f"|{self._fit(line1)}|", f"|{self._fit(line2)}|", border))
        self.last_frame = frame
        print(frame, file=self.output, flush=True)
        return frame

