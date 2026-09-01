import cogs.server_monitor as server_monitor


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
