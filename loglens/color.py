"""ANSI colorization utilities for loglens."""

def colorize(line: str, service: str) -> str:
    """Wrap line with ANSI color based on service name.

    Args:
        line: The log line to colorize.
        service: The service name used to determine the color.

    Returns:
        The line wrapped with ANSI color codes.
    """
    # Simple hash-based color selection from a fixed palette
    # Using 6 colors (excluding white/black) for good contrast
    colors = [31, 32, 33, 34, 35, 36]  # red, green, yellow, blue, magenta, cyan
    # Compute a deterministic index from the service name
    # Using built-in hash (consistent within a Python process) and modulo
    idx = hash(service) % len(colors)
    color_code = colors[idx]
    return f"\x1b[{color_code}m{line}\x1b[0m"