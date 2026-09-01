"""Safe local interface-name discovery with no packet transmission."""

import socket


def interface_names() -> list[str]:
    return [name for _, name in socket.if_nameindex()]

