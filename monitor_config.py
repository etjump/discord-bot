import json
import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from etquery import DEFAULT_PORT

log = logging.getLogger("server_monitor")

_SERVERS_FILE = Path(__file__).parent / "config" / "servers.json"


@dataclass
class MonitoredServer:
    host: str
    port: int
    guild_id: int
    channel_id: int
    message_id: int | None = None
    name: str = ""  # cached from 'sv_hostname'


class MonitorConfigError(Exception):
    pass


def main() -> None:
    print(f"Reading server monitor config {_SERVERS_FILE}\n")

    try:
        servers = load_config(_SERVERS_FILE)
    except MonitorConfigError as e:
        print(f"Failed to load config: {e}")
        sys.exit(1)

    for server in servers:
        print(server)


def _parse_entry(raw: dict[str, object]) -> MonitoredServer | None:
    host = raw.get("host")
    if not isinstance(host, str) or not host:
        return None

    port = raw.get("port")
    if port is None:
        port = DEFAULT_PORT
    elif not isinstance(port, int):
        return None

    guild_id = raw.get("guild_id")
    if not isinstance(guild_id, int):
        return None

    channel_id = raw.get("channel_id")
    if not isinstance(channel_id, int):
        return None

    message_id = raw.get("message_id")
    if message_id is not None and not isinstance(message_id, int):
        return None

    name = raw.get("name")
    if name is None:
        name = ""
    elif not isinstance(name, str):
        return None

    return MonitoredServer(
        host=host,
        port=port,
        guild_id=guild_id,
        channel_id=channel_id,
        message_id=message_id,
        name=name,
    )


def load_config(path: Path) -> list[MonitoredServer]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise MonitorConfigError(f"Server monitor config file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise MonitorConfigError(f"Invalid JSON in {path}: {e}") from e

    if not isinstance(data, dict) or not isinstance(data.get("servers"), list):
        raise MonitorConfigError(f"{path} must be an object containing a server list")

    servers_raw = cast(list[dict[str, object]], data["servers"])
    servers: list[MonitoredServer] = []

    # validate entries, skip invalid ones - we don't want the entire
    # monitoring to go down due to one bad entry
    for i, raw in enumerate(servers_raw):
        if not isinstance(raw, dict):
            log.warning(f"Ignored server #{i} in {path} - invalid entry")
            continue

        entry = _parse_entry(raw)
        if entry is None:
            log.warning(f"Ignored server #{i} in {path} - missing or invalid fields")
            continue

        servers.append(entry)

    return servers


def save_config(path: Path, servers: list[MonitoredServer]) -> None:
    data = {"servers": [asdict(server) for server in servers]}
    _atomic_write(path, data)


def _atomic_write(path: Path, data: Mapping[str, object]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    os.replace(tmp, path)


if __name__ == "__main__":
    main()
