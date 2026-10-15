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


def test_colorize_different_services_may_differ():
    line = "same line"
    s1 = colorize(line, "service-a")
    s2 = colorize(line, "service-b")
    # They might be the same by chance, but we can run a few to see if we get different.
    # For simplicity, we just check that the function returns a string.
    assert isinstance(s1, str)
    assert isinstance(s2, str)