"""Bounded HTTP/HTTPS metadata collection for one authorized local service."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from hashlib import sha256
import http.client
import ssl
from typing import Any


@dataclass(slots=True)
class WebObservation:
    scheme: str
    host: str
    port: int
    path: str
    status_code: int
    status_reason: str
    http_version: str
    headers: list[dict[str, str]]
    tls: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _http_version(value: int) -> str:
    return {9: "HTTP/0.9", 10: "HTTP/1.0", 11: "HTTP/1.1", 20: "HTTP/2"}.get(
        value, f"unknown ({value})"
    )


def _inspect(host: str, port: int, scheme: str, timeout: float) -> WebObservation:
    tls_data: dict[str, Any] | None = None
    if scheme == "https":
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            host, port, timeout=timeout, context=context
        )
    else:
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("HEAD", "/", headers={
            "User-Agent": "Pi-OT-Probe-Raw-Inspector/1.0",
            "Accept": "*/*",
            "Connection": "close",
        })
        if scheme == "https" and connection.sock:
            certificate = connection.sock.getpeercert(binary_form=True)
            cipher = connection.sock.cipher()
            tls_data = {
                "protocol": connection.sock.version(),
                "cipher": cipher[0] if cipher else None,
                "cipher_protocol": cipher[1] if cipher else None,
                "cipher_bits": cipher[2] if cipher else None,
                "certificate_sha256": sha256(certificate).hexdigest() if certificate else None,
                "certificate_validation": "not performed (local observation by IP address)",
            }
        response = connection.getresponse()
        headers = []
        for name, value in response.getheaders():
            stored_value = (
                "[redacted by data-minimization policy]"
                if name.lower() in {"set-cookie", "set-cookie2"} else value
            )
            headers.append({"name": name, "value": stored_value})
        return WebObservation(
            scheme=scheme,
            host=host,
            port=port,
            path="/",
            status_code=response.status,
            status_reason=response.reason or "",
            http_version=_http_version(response.version),
            headers=headers,
            tls=tls_data,
        )
    finally:
        connection.close()


async def inspect_website(
    host: str, port: int, scheme: str, *, timeout: float = 8.0
) -> WebObservation:
    if scheme not in {"http", "https"}:
        raise ValueError("scheme must be http or https")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return await asyncio.wait_for(
        asyncio.to_thread(_inspect, host, port, scheme, timeout), timeout=timeout + 2
    )
