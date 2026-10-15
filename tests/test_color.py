from loglens.color import colorize


def test_colorize_returns_ansi_string():
    line = "test message"
    service = "myservice"
    colored = colorize(line, service)
    # Should start with ESC [
    assert colored.startswith("\x1b[")
    # Should end with reset
    assert colored.endswith("\x1b[0m")
    # The line itself should be in between
    assert line in colored


def test_colorize_consistent_for_service():
    line = "same line"
    s1 = colorize(line, "service-a")
    s2 = colorize(line, "service-a")
    assert s1 == s2


def test_colorize_different_services_get_different_codes():
    line = "same line"
    # Test a few different service names to ensure we get different color codes.
    services = ["service-a", "service-b", "service-c", "service-d"]
    colored = [colorize(line, s) for s in services]
    # Extract the color code numbers (the part after \x1b[ and before m)
    import re
    codes = []
    for c in colored:
        match = re.search(r'\x1b\[(\d+)m', c)
        assert match, f"Could not find color code in {c!r}"
        codes.append(int(match.group(1)))
    # We expect at least two different codes among the services.
    # With 6 colors and 4 services, it's very likely, but we can still have a collision.
    # To avoid flakiness, we check that not all codes are the same.
    assert len(set(codes)) > 1, f"All services got the same color code: {codes}"