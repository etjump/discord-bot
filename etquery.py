import socket
import sys
from dataclasses import dataclass
from typing import Self

DEFAULT_PORT = 27960
GETSTATUS_QUERY = b"\xff\xff\xff\xffgetstatus\n"
GETSTATUS_RESPONSE_HEADER = b"\xff\xff\xff\xffstatusResponse\n"


@dataclass
class Status:
    host: str
    port: int
    info: dict[str, str]
    players: list[tuple[int, int, str]]
    location: str | None = None
    is_online: bool = True
    name: str | None = None  # 'sv_hostname', cached on query

    @classmethod
    def offline(cls, host: str, port: int) -> Self:
        return cls(host, port, {}, [], location=None, is_online=False)


class QueryError(Exception):
    pass


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) == 0:
        print("No server address given.")
        sys.exit(1)

    try:
        host, port = parse_address(argv[0])
        print(f"Server: {host}")
        print(f"Port: {port}")
    except ValueError as e:
        print(f"Invalid address: {e}")
        sys.exit(1)

    try:
        payload = query_status(host, port)
        status = parse_status(payload, host, port)
    except QueryError as e:
        print(f"Query failed: {e}")
        status = Status.offline(host, port)
        print(status)
        sys.exit(1)

    print(status)


def parse_address(addr: str) -> tuple[str, int]:
    parts = addr.strip().rsplit(":", 1)
    host = parts[0]

    if not host:
        raise ValueError("No address given.")

    if len(parts) == 2:
        if not parts[1]:
            raise ValueError("No port given.")

        port = int(parts[1])
    else:
        port = DEFAULT_PORT

    if port < 1 or port > 65535:
        raise ValueError("Port out of range.")

    return host, port


def query_status(addr: str, port: int) -> bytes:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3.0)

        try:
            sock.sendto(GETSTATUS_QUERY, (addr, port))
            data, _ = sock.recvfrom(65507)
        except TimeoutError:
            raise QueryError("Timed out while waiting for a response.") from None
        except OSError as e:
            raise QueryError(f"Network error: {e}") from None

    return data


def parse_status(payload: bytes, host: str, port: int) -> Status:
    if not payload.startswith(GETSTATUS_RESPONSE_HEADER):
        raise QueryError(f"Malformed status response from server: {host}:{port}")

    rest = payload[len(GETSTATUS_RESPONSE_HEADER) :]

    tokens = rest.split(b"\n")[0].split(b"\\")
    # info string starts with a separator, so drop the empty one at the beginning
    tokens = [t for t in tokens if t]

    info: dict[str, str] = {}
    for i in range(0, len(tokens), 2):
        key = tokens[i].decode("utf-8", errors="replace")
        value = tokens[i + 1].decode("utf-8", errors="replace")
        info[key] = value

    players: list[tuple[int, int, str]] = []
    for line in rest.split(b"\n")[1:]:
        # we have an empty entry at the end, as there's an extra separator
        if not line:
            continue

        raw_score, raw_ping, raw_name = line.split(b" ", 2)
        score, ping = int(raw_score), int(raw_ping)
        name = raw_name.strip(b'"').decode("utf-8", errors="replace")  # name is quoted
        players.append((score, ping, name))

    return Status(host, port, info, players)


if __name__ == "__main__":
    main()
