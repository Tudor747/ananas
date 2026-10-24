"""Bounded newline-delimited protocol, independent of serial I/O."""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

MAX_FRAME = 4096
ROLES = {"A": {"nrf", "wifi", "ble"}, "B": {"cc1101", "rfid"}, "C": {"ir"}}


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    v: int = Field(ge=1, le=1)
    node: Literal["A", "B", "C"]
    device: str = Field(min_length=1, max_length=64)
    boot: str = Field(min_length=1, max_length=64)
    session: str = Field(min_length=1, max_length=64)
    firmware: str = Field(min_length=1, max_length=80)
    seq: int = Field(ge=1, le=4294967295)
    uptime_ms: int = Field(ge=0, le=4294967295)
    type: Literal["reply", "event"]
    command: Literal["HELLO", "STATUS", "OBSERVE", "STOP", "SET_CONFIG", "TRANSMIT"]
    id: int = Field(ge=0, le=4294967295)
    health: Literal["ready", "busy", "error", "unsupported"]
    payload: dict = Field(default_factory=dict)


class Decoder:
    def __init__(self):
        self.buffer = bytearray()
        self.discarding = False
        self.rejected = 0

    def feed(self, chunk: bytes) -> list[Frame]:
        frames = []
        for byte in chunk:
            if byte == 10:
                if not self.discarding and self.buffer:
                    try:
                        raw = json.loads(self.buffer)
                        frame = Frame.model_validate(raw)
                        json.dumps(frame.payload, allow_nan=False)
                        frames.append(frame)
                    except (ValueError, RecursionError):
                        self.rejected += 1
                self.buffer.clear()
                self.discarding = False
            elif not self.discarding:
                if len(self.buffer) >= MAX_FRAME:
                    self.rejected += 1
                    self.buffer.clear()
                    self.discarding = True
                else:
                    self.buffer.append(byte)
        return frames


class NodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    node: Literal["A", "B", "C"]
    port: str = Field(min_length=1, max_length=256)
    device: str = Field(min_length=1, max_length=64)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command: Literal["STATUS", "OBSERVE", "STOP", "SET_CONFIG", "TRANSMIT"]
    authorized: bool = False
    operator: str = Field(default="", max_length=80)
    purpose: str = Field(default="", max_length=200)
    args: dict[str, StrictInt | StrictStr] = Field(default_factory=dict)

    def check(self, node: str) -> None:
        if node not in ROLES:
            raise ValueError("unknown node")
        if self.command in {"STATUS", "STOP"}:
            if self.args:
                raise ValueError("this command has no arguments")
            return
        if not self.authorized or not self.operator.strip() or not self.purpose.strip():
            raise ValueError("authorization, operator and test purpose are required")
        if self.command == "OBSERVE":
            if set(self.args) != {"sensor", "duration_ms"}:
                raise ValueError("OBSERVE requires sensor and duration_ms")
            if self.args["sensor"] not in ROLES[node]:
                raise ValueError("sensor does not belong to this node")
            duration = self.args["duration_ms"]
            if type(duration) is not int or not 100 <= duration <= 10000:
                raise ValueError("observation must last 100–10000 ms")
        elif self.command == "SET_CONFIG":
            if node != "A" or set(self.args) != {"channel"} or type(self.args["channel"]) is not int or not 0 <= self.args["channel"] <= 125:
                raise ValueError("only node A nRF channel 0–125 is configurable")
        elif node == "A" and self.args == {"test": "nrf_link"}:
            return
        elif node != "C" or set(self.args) != {"code"} or type(self.args["code"]) is not int or not 0 <= self.args["code"] <= 0xFFFFFFFF:
            raise ValueError("only a single nRF peer test or 32-bit NEC IR code is supported")
