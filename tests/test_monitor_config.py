import json
from pathlib import Path

import pytest

import monitor_config


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# --- _parse_entry ---


def test_parse_entry_minimal() -> None:
    entry = monitor_config._parse_entry(
        {"host": "et.etjump.com", "guild_id": 1, "channel_id": 2}
    )
    assert entry == monitor_config.MonitoredServer(
        host="et.etjump.com",
        port=monitor_config.DEFAULT_PORT,
        guild_id=1,
        channel_id=2,
    )


def test_parse_entry_full() -> None:
    entry = monitor_config._parse_entry(
        {
            "host": "et.etjump.com",
            "port": 27961,
            "guild_id": 1,
            "channel_id": 2,
            "message_id": 123,
            "name": "|999| Trickjump!",
        }
    )
    assert entry == monitor_config.MonitoredServer(
        host="et.etjump.com",
        port=27961,
        guild_id=1,
        channel_id=2,
        message_id=123,
        name="|999| Trickjump!",
    )


def test_parse_entry_null_port_defaults() -> None:
    entry = monitor_config._parse_entry(
        {"host": "et.etjump.com", "port": None, "guild_id": 1, "channel_id": 2}
    )
    assert entry is not None
    assert entry.port == monitor_config.DEFAULT_PORT


def test_parse_entry_null_message_id() -> None:
    entry = monitor_config._parse_entry(
        {
            "host": "et.etjump.com",
            "guild_id": 1,
            "channel_id": 2,
            "message_id": None,
        }
    )
    assert entry is not None
    assert entry.message_id is None


def test_parse_entry_null_name_defaults() -> None:
    entry = monitor_config._parse_entry(
        {"host": "et.etjump.com", "guild_id": 1, "channel_id": 2, "name": None}
    )
    assert entry is not None
    assert entry.name == ""


@pytest.mark.parametrize(
    "raw",
    [
        {"host": "", "guild_id": 1, "channel_id": 2},
        {"host": 123, "guild_id": 1, "channel_id": 2},
        {"host": "x", "guild_id": "abc", "channel_id": 2},
        {"host": "x", "guild_id": 1, "channel_id": "abc"},
        {"host": "x", "port": "abc", "guild_id": 1, "channel_id": 2},
        {"host": "x", "guild_id": 1, "channel_id": 2, "message_id": "abc"},
        {"host": "x", "guild_id": 1, "channel_id": 2, "name": 42},
    ],
)
def test_parse_entry_rejects_bad_field(raw: dict[str, object]) -> None:
    assert monitor_config._parse_entry(raw) is None


# --- load_config ---


def test_load_config_valid(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    data: dict[str, object] = {
        "servers": [
            {"host": "et.etjump.com", "guild_id": 1, "channel_id": 2},
            {
                "host": "65.108.82.168",
                "port": 27961,
                "guild_id": 3,
                "channel_id": 4,
                "message_id": 99,
                "name": "Other",
            },
        ]
    }
    _write_json(path, data)

    servers = monitor_config.load_config(path)

    assert servers == [
        monitor_config.MonitoredServer(
            host="et.etjump.com",
            port=monitor_config.DEFAULT_PORT,
            guild_id=1,
            channel_id=2,
        ),
        monitor_config.MonitoredServer(
            host="65.108.82.168",
            port=27961,
            guild_id=3,
            channel_id=4,
            message_id=99,
            name="Other",
        ),
    ]


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(monitor_config.MonitorConfigError):
        monitor_config.load_config(tmp_path / "does-not-exist.json")


def test_load_config_broken_json(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    path.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(monitor_config.MonitorConfigError):
        monitor_config.load_config(path)


def test_load_config_servers_not_a_list(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    _write_json(path, {"servers": "nope"})
    with pytest.raises(monitor_config.MonitorConfigError):
        monitor_config.load_config(path)


def test_load_config_skips_invalid_entries(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    data: dict[str, object] = {
        "servers": [
            {"host": "et.etjump.com", "guild_id": 1, "channel_id": 2},
            {"host": "", "guild_id": 1, "channel_id": 2},
            {"host": "other.com", "guild_id": "not-an-int", "channel_id": 3},
            "not a dict",
        ]
    }
    _write_json(path, data)

    servers = monitor_config.load_config(path)

    assert servers == [
        monitor_config.MonitoredServer(
            host="et.etjump.com",
            port=monitor_config.DEFAULT_PORT,
            guild_id=1,
            channel_id=2,
        )
    ]


def test_load_config_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    _write_json(path, {"servers": []})
    assert monitor_config.load_config(path) == []


# --- save_config ---


def test_save_load_roundtrip(tmp_path: Path) -> None:
    servers = [
        monitor_config.MonitoredServer(
            host="et.etjump.com",
            port=27960,
            guild_id=1,
            channel_id=2,
            message_id=123,
            name="Trickjump",
        ),
        monitor_config.MonitoredServer(
            host="65.108.82.168", port=27960, guild_id=1, channel_id=2
        ),
    ]
    path = tmp_path / "servers.json"

    monitor_config.save_config(path, servers)

    assert monitor_config.load_config(path) == servers


def test_save_creates_file_with_content(tmp_path: Path) -> None:
    servers = [
        monitor_config.MonitoredServer(
            host="et.etjump.com", port=27960, guild_id=1, channel_id=2
        )
    ]
    path = tmp_path / "servers.json"

    monitor_config.save_config(path, servers)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "servers": [
            {
                "host": "et.etjump.com",
                "port": 27960,
                "guild_id": 1,
                "channel_id": 2,
                "message_id": None,
                "name": "",
            }
        ]
    }


def test_save_leaves_no_temp_file(tmp_path: Path) -> None:
    servers = [
        monitor_config.MonitoredServer(
            host="et.etjump.com", port=27960, guild_id=1, channel_id=2
        )
    ]
    path = tmp_path / "servers.json"

    monitor_config.save_config(path, servers)

    assert path.exists()
    assert not (tmp_path / "servers.json.tmp").exists()
