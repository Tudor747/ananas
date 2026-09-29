"""Explicit plugin registry; remote data can never register executable code."""

from pi_ot_probe.plugins.base import SecurityPlugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, SecurityPlugin] = {}

    def register(self, plugin: SecurityPlugin) -> None:
        name = plugin.metadata.name
        if name in self._plugins:
            raise ValueError(f"plugin already registered: {name}")
        self._plugins[name] = plugin

    def all(self) -> tuple[SecurityPlugin, ...]:
        return tuple(self._plugins.values())

    def get(self, name: str) -> SecurityPlugin:
        return self._plugins[name]
