"""Adapter-neutral Wi-Fi interface contract."""

from abc import ABC, abstractmethod

from pi_ot_probe.core.models import WifiAccessPoint


class WifiInterface(ABC):
    @abstractmethod
    async def access_points(self) -> list[WifiAccessPoint]:
        raise NotImplementedError

