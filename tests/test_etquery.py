import pytest

import etquery

# Real getstatus response captured from the 999 Trickjump server
# (et.etjump.com:27960), used as a golden fixture for parse_status.
GETSTATUS_RESPONSE = (
    b"\xff\xff\xff\xffstatusResponse\n"
    b"\\g_antilag\\1\\g_friendlyFire\\1\\g_gametype\\2\\g_maxlives\\0"
    b"\\g_minGameClients\\0\\g_needpass\\0\\mapname\\piyo-funjumps_rev"
    b"\\mod_version\\3.6.2\\protocol\\84\\sv_clientPaks\\0 0"
    b"\\sv_currentPak\\-2104709741\\sv_floodProtect\\0"
    b"\\sv_hostname\\^9|^7999^9| Trickjump^7!^9\\sv_maxRate\\100000"
    b"\\sv_maxclients\\40\\sv_minRate\\25000\\sv_privateClients\\4"
    b"\\timelimit\\0\\version\\ET 2.60e linux-x86_64 Apr 20 2026"
    b"\\voteFlags\\0\\P\\-------33-3-3-3\\g_autoRtv\\0"
    b"\\g_bluelimbotime\\2000\\g_ghostPlayers\\1\\g_maxGameClients\\0"
    b"\\g_oss\\399\\g_portalPredict\\1\\g_portalTeam\\0"
    b"\\g_redlimbotime\\2000\\g_spectatorVote\\2\\gamename\\etjump"
    b"\\mod_url\\etjump.com\\Admin\\Zero & Aciz\\Contact\\zero@etjump.com\n"
    b'0 44 "A-BloCk"\n'
    b'0 9 "Horsey!"\n'
    b'0 44 "^7bird^0."\n'
    b'0 17 "apso"\n'
    b'0 170 "^7[^l100^7]^lL^7ag^lS^7pike"\n'
)


def test_parse_address_bare_host() -> None:
    assert etquery.parse_address("et.etjump.com") == ("et.etjump.com", 27960)


def test_parse_address_with_port() -> None:
    assert etquery.parse_address("65.108.82.168:27961") == ("65.108.82.168", 27961)


def test_parse_address_trailing_colon_raises() -> None:
    with pytest.raises(ValueError):
        etquery.parse_address("et.etjump.com:")


def test_parse_address_empty_host_raises() -> None:
    with pytest.raises(ValueError):
        etquery.parse_address(":27960")


def test_parse_address_non_numeric_port_raises() -> None:
    with pytest.raises(ValueError):
        etquery.parse_address("host:notaport")


def test_parse_address_port_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        etquery.parse_address("host:70000")


def test_parse_status_real_payload() -> None:
    status = etquery.parse_status(GETSTATUS_RESPONSE, "et.etjump.com", 27960)

    assert status.host == "et.etjump.com"
    assert status.port == 27960
    assert status.info["mapname"] == "piyo-funjumps_rev"
    assert status.info["gamename"] == "etjump"
    assert status.info["sv_hostname"] == "^9|^7999^9| Trickjump^7!^9"
    assert status.info["sv_maxclients"] == "40"
    assert len(status.players) == 5
    assert status.players[0] == (0, 44, "A-BloCk")
    assert status.players[-1] == (0, 170, "^7[^l100^7]^lL^7ag^lS^7pike")
    assert status.location is None
    assert status.is_online is True


def test_parse_status_malformed_payload_raises() -> None:
    with pytest.raises(etquery.QueryError):
        etquery.parse_status(b"\xff\xff\xff\xffprint\nNo challenge", "host", 27960)


def test_status_offline_builds_stub() -> None:
    status = etquery.Status.offline("et.etjump.com", 27960)

    assert status.host == "et.etjump.com"
    assert status.port == 27960
    assert status.info == {}
    assert status.players == []
    assert status.location is None
    assert status.is_online is False
