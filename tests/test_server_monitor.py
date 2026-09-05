import cogs.server_monitor as server_monitor
import etquery


def test_strip_color_codes_simple() -> None:
    assert server_monitor._strip_color_codes("^zfoo ^7bar") == "foo bar"


def test_strip_color_codes_no_colors() -> None:
    assert server_monitor._strip_color_codes("plain text") == "plain text"


def test_strip_color_codes_escaped_caret() -> None:
    # "^^" is the escape for a literal caret, not a color code
    assert server_monitor._strip_color_codes("^^") == "^^"
    assert server_monitor._strip_color_codes("^^1foo ^2bar") == "^foo bar"


def test_strip_color_codes_trailing_caret() -> None:
    assert server_monitor._strip_color_codes("foo bar^") == "foo bar^"
    assert server_monitor._strip_color_codes("foo bar^^") == "foo bar^^"


def test_strip_color_codes_trailing_color_code() -> None:
    assert server_monitor._strip_color_codes("foo bar^1") == "foo bar"


def test_build_location_field_finland() -> None:
    assert server_monitor._build_location_field("FI") == "🇫🇮 Finland"


def test_build_location_field_none() -> None:
    assert (
        server_monitor._build_location_field(None) == server_monitor._UNKNOWN_LOCATION
    )


def test_build_location_field_short_code() -> None:
    assert server_monitor._build_location_field("F") == server_monitor._UNKNOWN_LOCATION


def test_build_location_field_too_long() -> None:
    assert (
        server_monitor._build_location_field("XXX") == server_monitor._UNKNOWN_LOCATION
    )


def test_build_location_field_unknown_code() -> None:
    assert (
        server_monitor._build_location_field("ZZ") == server_monitor._UNKNOWN_LOCATION
    )


# status stub to test player bucketing
_BUCKET_STATUS = etquery.Status(
    "127.0.0.1",
    27960,
    {},
    [
        (0, 0, "^1player^11"),
        (0, 0, "^2player^22"),
        (0, 0, "^3player^33"),
        (0, 0, "^4player^44"),
        (0, 0, "^5player^55"),
        (0, 0, "^6player^66"),
        (0, 0, "^7player^77"),
        (0, 0, "^8player^88"),
    ],
)


def test_bucket_players_splits_teams_properly() -> None:
    player_teams = "---13---2--12--32----3-"
    bucket = server_monitor._bucket_players(player_teams, _BUCKET_STATUS)

    assert len(bucket[server_monitor._TEAM_AXIS]) == 2
    assert len(bucket[server_monitor._TEAM_ALLIES]) == 3
    assert len(bucket[server_monitor._TEAM_SPECTATORS]) == 3

    assert bucket[server_monitor._TEAM_AXIS] == ["player1", "player4"]
    assert bucket[server_monitor._TEAM_ALLIES] == ["player3", "player5", "player7"]
    assert bucket[server_monitor._TEAM_SPECTATORS] == ["player2", "player6", "player8"]


def test_bucket_players_strips_colors() -> None:
    player_teams = "---33---3--33--33----3-"
    bucket = server_monitor._bucket_players(player_teams, _BUCKET_STATUS)

    for i, player in enumerate(bucket[server_monitor._TEAM_SPECTATORS]):
        assert player == f"player{i + 1}"


def test_bucket_players_all_spectators() -> None:
    player_teams = "---33---3--33--33----3-"
    bucket = server_monitor._bucket_players(player_teams, _BUCKET_STATUS)
    assert len(bucket[server_monitor._TEAM_AXIS]) == 0
    assert len(bucket[server_monitor._TEAM_ALLIES]) == 0


def test_bucket_players_short_player_string_truncates() -> None:
    player_teams = "---33---3--33--33-----"
    bucket = server_monitor._bucket_players(player_teams, _BUCKET_STATUS)
    assert len(bucket[server_monitor._TEAM_SPECTATORS]) == 7
    assert bucket[server_monitor._TEAM_SPECTATORS][-1] == "player7"


def test_bucket_players_long_player_string_truncates() -> None:
    player_teams = "---33---3--33--33----3-3"
    bucket = server_monitor._bucket_players(player_teams, _BUCKET_STATUS)
    assert len(bucket[server_monitor._TEAM_SPECTATORS]) == 8
    assert bucket[server_monitor._TEAM_SPECTATORS][-1] == "player8"
