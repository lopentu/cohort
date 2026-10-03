"""Explicit, validated boundaries for a same-host HTTPS reverse proxy."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


def validate_public_origin(origin: str) -> None:
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or parsed.geturl() != origin
            or any(ord(char) <= 32 or ord(char) == 127 for char in origin)):
        raise ValueError('public origin must be an HTTPS origin without a path or credentials')
    # Accessing port rejects malformed values before server startup.
    if parsed.port == 0:
        raise ValueError('public origin has an invalid port')


@dataclass(frozen=True)
class HostingConfig:
    root_path: str = ''
    public_origin: str | None = None
    trusted_proxy_ips: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)*', self.root_path):
            raise ValueError('root path must be empty or slash-separated plain segments without a trailing slash')
        if self.public_origin is not None:
            validate_public_origin(self.public_origin)
            if not self.trusted_proxy_ips:
                raise ValueError('public hosting requires explicit trusted loopback proxy addresses')
        if self.trusted_proxy_ips is not None:
            if self.public_origin is None:
                raise ValueError('trusted proxies require a public HTTPS origin')
            try:
                addresses = [ipaddress.ip_address(value) for value in self.trusted_proxy_ips.split(',')]
            except ValueError as exc:
                raise ValueError('trusted proxies must be literal loopback addresses, never a wildcard') from exc
            if not all(address.is_loopback for address in addresses):
                raise ValueError('only a same-host loopback proxy is supported')
