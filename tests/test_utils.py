from packs.utils import format_duration, pack_command_name


def test_format_duration_seconds():
    assert format_duration(0) == "0 seconds"
    assert format_duration(1) == "1 second"
    assert format_duration(59) == "59 seconds"


def test_format_duration_minutes_and_hours():
    assert format_duration(60) == "1 minute"
    assert format_duration(61) == "1 minute and 1 second"
    assert format_duration(3661) == "1 hour, 1 minute, and 1 second"


def test_format_duration_days():
    assert format_duration(86400) == "1 day"
    assert format_duration(604800) == "7 days"


def test_pack_command_name():
    assert pack_command_name("daily") == "daily"
    assert pack_command_name("Weekly Pack") == "weekly_pack"
    assert pack_command_name("daily") == "daily"


def test_pack_command_name_rejects_reserved_and_invalid_values():
    assert pack_command_name("list") is None
    assert pack_command_name("open") is None
    assert pack_command_name("shop") is None
    assert pack_command_name("info") is None
    assert pack_command_name("a" * 33) is None
    assert pack_command_name("bad/name") is None
