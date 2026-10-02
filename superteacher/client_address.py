"""Rate-limit identity for an explicitly verified proxy append policy.

This does not authenticate clients or alter Uvicorn's scheme/origin handling.
The ingress owner must verify the trusted suffix length and exclude direct access
before enabling it. Never infer a hop count from a platform name.
"""

from ipaddress import IPv6Address, ip_address

from starlette.requests import HTTPConnection

UNVERIFIED_CLIENT = "unverified-forwarded-client"
MAX_FORWARDED_LENGTH = 4096


def rate_limit_client(connection: HTTPConnection, *, trusted_hops: int = 0) -> str:
    if trusted_hops == 0:
        return connection.client.host if connection.client else "unknown"
    if not 1 <= trusted_hops <= 8:
        return UNVERIFIED_CLIENT
    values = connection.headers.getlist("x-forwarded-for")
    if len(values) != 1 or len(values[0]) > MAX_FORWARDED_LENGTH:
        return UNVERIFIED_CLIENT
    # Ignore the unverified prefix, including arbitrary non-address text there.
    suffix = values[0].rsplit(",", trusted_hops)[-trusted_hops:]
    if len(suffix) < trusted_hops:
        return UNVERIFIED_CLIENT
    try:
        addresses = []
        for item in suffix:
            item = item.strip()
            if "%" in item:  # IPv6 scope IDs have no meaning across this HTTP proxy boundary.
                return UNVERIFIED_CLIENT
            address = ip_address(item)
            if isinstance(address, IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            addresses.append(address)
    except ValueError:
        return UNVERIFIED_CLIENT
    return str(addresses[0])
