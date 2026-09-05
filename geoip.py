import os
import socket
import sys
import urllib.request
from functools import lru_cache

import etquery


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) == 0:
        print("No address provided.")
        sys.exit(1)

    country = country_lookup(argv[0])
    print(country)


def country_lookup(addr: str) -> str | None:
    host, _ = etquery.parse_address(addr)
    ip = socket.gethostbyname(host)
    return _ip_lookup(ip)


@lru_cache(64)
def _ip_lookup(ip: str) -> str | None:
    """you should not call this function directly - instead call 'country_lookup',
    which handles potential DNS -> IP conversion, so the cache only contains IP addresses
    """
    IPINFO_TOKEN = os.environ.get("IPINFO_TOKEN")
    # as of writing, IPInfo lookup still works without a token,
    # but this is subject to change, so wire up a token path as well
    if IPINFO_TOKEN is not None:
        url = f"https://api.ipinfo.io/lite/{ip}/country_code?token={IPINFO_TOKEN}"
    else:
        url = f"https://ipinfo.io/{ip}/country"

    try:
        with urllib.request.urlopen(url, timeout=5.0) as resp:
            cc: str = resp.read().decode("utf-8").strip().upper()

            if len(cc) == 2 and cc.isalpha():
                return cc

            return None
    except OSError:
        return None


if __name__ == "__main__":
    main()
